#!/usr/bin/env python3
"""Read-only on-demand repository status. No deployment or application access."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler

REPO = "FawLog/vzn-activity-tracker"
API = "https://api.github.com/repos/" + REPO
TTL = 30
SHA = re.compile(r"[0-9a-f]{40}")

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def get_json(path, token):
    request = Request(API + path, headers={"Authorization":"Bearer "+token,
        "Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28",
        "User-Agent":"VZN-Version-Status/1"})
    with build_opener(NoRedirect()).open(request, timeout=5) as response:
        raw = response.read(2*1024**2+1)
    if len(raw)>2*1024**2:
        raise ValueError("Response too large")
    return json.loads(raw)

def classify(runs, sha):
    matching=[r for r in runs if r.get("head_sha")==sha and r.get("head_branch")=="main"
              and r.get("event")=="push" and r.get("path")==".github/workflows/ci.yml"
              and (r.get("head_repository") or {}).get("full_name")==REPO]
    if not matching:
        return "unknown"
    run=max(matching,key=lambda r:(r["id"],r.get("run_attempt",1)))
    if run.get("status")!="completed":
        return "running"
    if run.get("conclusion")=="success":
        return "success"
    if run.get("conclusion") in ("failure","cancelled","timed_out","action_required","startup_failure"):
        return "failed"
    return "unknown"

def snapshot(token):
    sha=get_json("/branches/main",token)["commit"]["sha"]
    if not isinstance(sha,str) or not SHA.fullmatch(sha):
        raise ValueError("Invalid SHA")
    try:
        runs=get_json("/actions/runs?branch=main&event=push&head_sha="+sha+"&per_page=30",token)
        ci=classify(runs["workflow_runs"],sha)
    except Exception:
        ci="unknown"
    return {"sha":sha,"ci":ci,"checked_at":datetime.now(timezone.utc).isoformat()}

class Cache:
    def __init__(self, token):
        self.token=token
        self.expires=0
        self.value=None
    def get(self):
        if time.monotonic()>=self.expires:
            try:
                self.value=snapshot(self.token)
            except Exception:
                self.value=None
            self.expires=time.monotonic()+TTL
        return self.value

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)
    def do_GET(self):
        if self.path!="/api/v1/repository-version":
            self.send_error(404)
            return
        value=self.server.cache.get()
        body=json.dumps(value if value else {"sha":None,"ci":"unknown","checked_at":None}).encode()
        self.send_response(200 if value else 503)
        self.send_header("Content-Type","application/json")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,fmt,*args):
        pass

def main():
    token=(Path(os.environ["CREDENTIALS_DIRECTORY"])/"github-token").read_text().strip()
    if not token:
        raise SystemExit("Missing credential")
    server=HTTPServer(("127.0.0.1",8092),Handler)
    server.cache=Cache(token)
    server.serve_forever()

if __name__=="__main__":
    main()
