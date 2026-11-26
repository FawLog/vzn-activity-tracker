#!/usr/bin/env python3
"""Root-owned, fixed-purpose deployment controller. Never trusts webhook contents."""
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
import zipfile

REPO = "FawLog/vzn-activity-tracker"
API = "https://api.github.com/repos/" + REPO
STATE = Path("/var/lib/vzn-autodeploy")
QUEUE = Path("/var/lib/vzn-deploy-inbox/pending")
CONFIG = Path("/etc/vzn-activity-tracker")
APP = Path("/srv/vzn-activity-tracker")
LIB = Path("/usr/local/lib/vzn-autodeploy")
RESERVE = 512 * 1024**2
MAX_ARTIFACT = 512 * 1024**2
JOBS = {"Committed lockfile policy", "Backend tests and migrations", "TypeScript, Vitest, and Vite build",
        "Backend image build and smoke test", "Playwright full-stack browser tests", "Assemble deployment bundle"}
CONTROL_FILES = ("compose.yaml", "scripts/set_image_tag.py", "deploy/root/stage-vzn-artifacts",
                 "deploy/root/update-vzn-activity-tracker", "deploy/root/manage-vzn-sudoers",
                 "deploy/root/healthcheck.sh", "deploy/root/install-vzn-activity-tracker")
SHA = re.compile(r"[0-9a-f]{40}")

class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urlsplit(newurl)
        if url.scheme != "https" or url.username or url.password or url.port not in (None,443):
            raise RuntimeError("Unsafe artifact redirect")
        # GitHub returns a short-lived signed download URL. Never forward PAT.
        return Request(newurl, headers={"User-Agent":"VZN-Autodeploy/1"})

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def root_file(path):
    st = path.lstat()
    require(path.is_file() and not path.is_symlink() and st.st_uid == 0 and not st.st_mode & 0o022,
            "Unsafe root configuration: " + path.name)
    return path

def reserve():
    path = CONFIG / "minimum-reserve-bytes"
    if not path.exists():
        return RESERVE
    value = root_file(path).read_text().strip()
    require(value.isdecimal() and RESERVE <= int(value) <= 1024**4, "Invalid reserve")
    return int(value)

def space(needed=0):
    # The existing updater additionally budgets the uncompressed Docker peak and SQLite backup.
    for path in (STATE, APP, Path("/var/lib/docker"), Path("/var/lib")):
        if path.exists():
            require(shutil.disk_usage(path).free >= reserve() + needed, "Insufficient deployment disk space")

def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def api(path, token):
    request = Request(API + path, headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
                                          "X-GitHub-Api-Version":"2022-11-28","User-Agent":"VZN-Autodeploy/1"})
    with build_opener(SafeRedirect()).open(request, timeout=20) as response:
        raw = response.read(4*1024**2+1)
    require(len(raw)<=4*1024**2, "GitHub response too large")
    return json.loads(raw)

def main_sha(token):
    sha = api("/branches/main",token)["commit"]["sha"]
    require(isinstance(sha,str) and SHA.fullmatch(sha), "Invalid main SHA")
    return sha

def eligible(run, sha):
    return (run.get("head_sha")==sha and run.get("head_branch")=="main" and run.get("event")=="push"
            and run.get("status")=="completed" and run.get("conclusion")=="success"
            and run.get("path")==".github/workflows/ci.yml"
            and run.get("head_repository",{}).get("full_name")==REPO)

def exact_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None

def merged_pr(pr, sha):
    base = pr.get("base") or {}
    return (pr.get("state") == "closed" and bool(pr.get("merged_at"))
            and pr.get("merge_commit_sha") == sha and base.get("ref") == "main"
            and (base.get("repo") or {}).get("full_name") == REPO)

def verify_merged_history(previous, target, token):
    """Our workflow uses squash merges only. Reject direct pushes anywhere in the gap."""
    require(exact_sha(previous) and exact_sha(target), "Invalid deployment history")
    cursor = target
    target_tree = None
    for _ in range(50):
        if cursor == previous:
            return target_tree
        commit = api("/commits/" + cursor, token)
        require(commit.get("sha") == cursor, "Commit identity mismatch")
        if target_tree is None:
            target_tree = commit["commit"]["tree"]["sha"]
            require(exact_sha(target_tree), "Invalid target tree")
        parents = commit.get("parents") or []
        require(len(parents) == 1 and exact_sha(parents[0].get("sha")), "Nonlinear deployment history requires owner review")
        prs = api("/commits/" + cursor + "/pulls?per_page=100", token)
        require(isinstance(prs, list) and any(merged_pr(pr, cursor) for pr in prs),
                "Commit is not an exact merged main PR: " + cursor)
        cursor = parents[0]["sha"]
    require(cursor == previous, "Deployment history exceeds 50 commits; owner review required")
    return target_tree

def verify_ci_tree(tree_sha, token):
    # Pin the complete .github Git tree, including workflows and CI helper scripts.
    approved = root_file(CONFIG / "approved-ci-tree").read_text().strip()
    require(exact_sha(approved) and exact_sha(tree_sha), "Invalid approved CI tree")
    tree = api("/git/trees/" + tree_sha, token)
    require(tree.get("sha") == tree_sha and not tree.get("truncated"), "Invalid target root tree")
    entries = [e for e in tree["tree"] if e.get("path") == ".github"]
    require(len(entries) == 1 and entries[0].get("type") == "tree"
            and entries[0].get("mode") == "040000" and entries[0].get("sha") == approved,
            "CI configuration changed; owner review required")

def current_sha():
    result = subprocess.check_output(["/usr/bin/docker","container","inspect","--format","{{.Config.Image}}",
                                      "vzn-activity-tracker-backend"],text=True).strip()
    prefix="vzn-activity-tracker-backend:ci-"
    require(result.startswith(prefix) and SHA.fullmatch(result[len(prefix):]),"Unexpected current image")
    return result[len(prefix):]

def download(artifact, folder, names, token):
    size=artifact["size_in_bytes"]
    require(isinstance(size,int) and 0<size<=MAX_ARTIFACT,"Artifact size exceeds limit")
    digest=artifact.get("digest","")
    require(isinstance(digest,str) and re.fullmatch(r"sha256:[0-9a-f]{64}",digest),"Missing artifact digest")
    aid=artifact["id"]
    require(type(aid) is int and aid>0,"Invalid artifact ID")
    space(size*2)
    target=folder/"artifact.zip"
    request=Request(API+"/actions/artifacts/"+str(aid)+"/zip",headers={"Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"VZN-Autodeploy/1"})
    with build_opener(SafeRedirect()).open(request,timeout=60) as source,target.open("xb") as out:
        written=0
        while chunk:=source.read(1024*1024):
            written+=len(chunk)
            require(written<=MAX_ARTIFACT and written<=size+1024*1024,"Artifact download exceeds bound")
            space(len(chunk))
            out.write(chunk)
    require("sha256:"+sha256(target)==digest,"Artifact digest mismatch")
    with zipfile.ZipFile(target) as bundle:
        entries=bundle.infolist()
        require(len(entries)==len(names) and {e.filename for e in entries}==names,"Unexpected ZIP contents")
        require(all(not e.is_dir() and 0<=e.file_size<=MAX_ARTIFACT for e in entries),"Invalid ZIP entries")
        space(sum(e.file_size for e in entries))
        for entry in entries:
            with bundle.open(entry) as source,(folder/entry.filename).open("xb") as out:
                shutil.copyfileobj(source,out,1024*1024)
    target.unlink()

def verify_controls(archive, sha):
    approved=json.loads(root_file(CONFIG/"approved-controls.json").read_text())
    require(set(approved)==set(CONTROL_FILES),"Invalid approved controls")
    with tarfile.open(archive,"r:gz") as bundle:
        members=bundle.getmembers()
        require(len(members)<=20000 and sum(m.size for m in members)<=128*1024**2,"Deployment archive exceeds bounds")
        indexed={}
        for member in members:
            name=str(PurePosixPath(member.name))
            require(not name.startswith("/") and ".." not in PurePosixPath(name).parts and (member.isfile() or member.isdir()),"Unsafe deployment archive")
            require(name not in indexed,"Duplicate deployment member")
            indexed[name]=member
        for name in CONTROL_FILES:
            member=indexed.get(name)
            require(member is not None and member.isfile() and member.size<=1024**2,"Missing deployment control")
            require(hashlib.sha256(bundle.extractfile(member).read()).hexdigest()==approved[name],
                    "Privileged control changed; owner review required: "+name)
        rev=indexed.get("REVISION")
        require(rev is not None and rev.isfile() and rev.size<100 and bundle.extractfile(rev).read().decode().strip()==sha,"Wrong deployment revision")

def check_installed_controls():
    approved=json.loads(root_file(CONFIG/"approved-controls.json").read_text())
    for installed,source in (("/usr/local/sbin/vzn-stage-vzn-artifacts","deploy/root/stage-vzn-artifacts"),
                             ("/usr/local/sbin/vzn-update","deploy/root/update-vzn-activity-tracker"),
                             ("/usr/local/lib/vzn-activity-tracker/healthcheck.sh","deploy/root/healthcheck.sh")):
        require(sha256(root_file(Path(installed)))==approved[source],"Installed control differs from reviewed version")

def deploy():
    if (CONFIG/"autodeploy-paused").exists():
        print("Automatic deployment paused")
        return
    require(not (APP/".vzn-updating").exists(),"Interrupted update requires owner review")
    token=root_file(CONFIG/"github-token").read_text().strip()
    require(bool(token),"Missing GitHub token")
    sha=main_sha(token)
    previous=current_sha()
    if sha==previous:
        print("Already deployed "+sha)
        return
    # Protect against force-push/older main and stale webhook deliveries.
    comparison=api("/compare/"+previous+"..."+sha,token)
    require(comparison.get("status")=="ahead","Current main is not a descendant of deployed SHA")
    failed=STATE/"attempted-sha"
    require(not failed.exists() or failed.read_text().strip()!=sha,"Previously attempted SHA; owner review required")
    runs=api("/actions/runs?branch=main&event=push&head_sha="+sha+"&per_page=30",token)["workflow_runs"]
    runs=[r for r in runs if r.get("path")==".github/workflows/ci.yml" and r.get("head_sha")==sha]
    if not runs:
        print("No main CI yet")
        return
    run=max(runs,key=lambda r:(r["id"],r.get("run_attempt",1)))
    if not eligible(run,sha):
        print("Latest main CI not successful")
        return
    run_id=run["id"]
    require(type(run_id) is int and run_id>0,"Invalid run ID")
    jobs=api("/actions/runs/"+str(run_id)+"/jobs?filter=latest&per_page=100",token)
    require(jobs["total_count"]==len(JOBS) and len(jobs["jobs"])==len(JOBS)
            and {j["name"] for j in jobs["jobs"]}==JOBS and all(j["conclusion"]=="success" for j in jobs["jobs"]),"Required CI jobs not successful")
    target_tree = verify_merged_history(previous, sha, token)
    verify_ci_tree(target_tree, token)
    artifacts=api("/actions/runs/"+str(run_id)+"/artifacts?per_page=100",token)["artifacts"]
    check_installed_controls()
    space()
    with tempfile.TemporaryDirectory(prefix="download-",dir=STATE) as temporary:
        root=Path(temporary)
        for kind in ("deployment","frontend","backend"):
            matches=[a for a in artifacts if a["name"]=="production-"+kind+"-"+sha and not a["expired"]]
            require(len(matches)==1,"Missing or duplicate production artifact")
            folder=root/kind
            folder.mkdir()
            prefix="vzn-"+kind+"-"+sha
            names={prefix+".tar.gz",prefix+".tar.gz.sha256"}
            if kind=="backend":
                names|={prefix+".manifest",prefix+".image-id"}
            download(matches[0],folder,names,token)
        verify_controls(root/"deployment"/("vzn-deployment-"+sha+".tar.gz"),sha)
        # Main can advance during downloads. Never deploy a stale candidate.
        require(main_sha(token)==sha and current_sha()==previous,"Deployment target changed")
        require(not (CONFIG/"autodeploy-paused").exists(),"Deployment paused")
        space(sum(p.stat().st_size for p in root.rglob("*") if p.is_file())+128*1024**2)
        # Record before mutating production; a failed SHA is not retried automatically.
        failed.write_text(sha+"\n")
        print("Deploying "+sha+" from CI "+str(run_id),flush=True)
        subprocess.run(["/usr/local/sbin/vzn-stage-vzn-artifacts","--auto-update",str(root)],check=True)
        check_installed_controls()
        subprocess.run(["/usr/local/sbin/vzn-update"],check=True)
        require(current_sha()==sha,"Unexpected deployed image")
        failed.unlink()
        print("Deployment SUCCESS "+sha,flush=True)
        try:
            space()
        except RuntimeError:
            print("WARNING: post-update disk reserve below threshold; further deployments blocked by preflight",flush=True)

def main():
    require(os.geteuid()==0,"Worker must be root")
    with (STATE/"lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        # Remove signal before processing; a new signal during work remains for the next activation.
        QUEUE.unlink(missing_ok=True)
        try:
            deploy()
        except Exception as error:
            # Avoid printing network exception details or signed redirect URLs.
            print("Deployment blocked/failed: "+(str(error) if type(error) is RuntimeError else type(error).__name__),flush=True)
            raise SystemExit(1)

if __name__=="__main__":
    main()
