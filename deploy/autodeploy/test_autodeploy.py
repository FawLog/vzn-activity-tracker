import hashlib
import hmac
import json
import unittest
from listener import valid_event, REPO
from worker import eligible, SHA, merged_pr, verify_merged_history, verify_ci_tree
from unittest.mock import patch
from pathlib import Path
import tempfile

class GateTests(unittest.TestCase):
    def test_webhook(self):
        secret=b"x"*32
        run={"head_branch":"main","event":"push","conclusion":"success","status":"completed","head_repository":{"full_name":REPO},"head_sha":"a"*40}
        data={"repository":{"full_name":REPO},"action":"completed","workflow_run":run}
        def check():
            raw=json.dumps(data).encode()
            sig="sha256="+hmac.new(secret,raw,hashlib.sha256).hexdigest()
            self.assertFalse(valid_event(raw,"sha256=bad","workflow_run",secret))
            return valid_event(raw,sig,"workflow_run",secret)
        self.assertTrue(check())
        for key,value in [("event","pull_request"),("head_branch","dev"),("conclusion","failure"),("head_sha","invalid")]:
            old=run[key];run[key]=value
            self.assertFalse(check());run[key]=old
    def test_api_gate(self):
        sha="a"*40
        run={"head_sha":sha,"head_branch":"main","event":"push","status":"completed","conclusion":"success","path":".github/workflows/ci.yml","head_repository":{"full_name":REPO}}
        self.assertTrue(eligible(run,sha))
        for key,value in [("head_sha","b"*40),("event","pull_request"),("path",".github/workflows/other.yml"),("conclusion","failure")]:
            self.assertFalse(eligible({**run,key:value},sha))
        self.assertFalse(SHA.fullmatch("../bad"))

class ProductionPolicyTests(unittest.TestCase):
    old = "a"*40
    middle = "b"*40
    target = "c"*40
    tree = "d"*40
    approved = "e"*40

    def pr(self, sha):
        return {"state":"closed", "merged_at":"2026-11-26T00:00:00Z", "merge_commit_sha":sha,
                "base":{"ref":"main","repo":{"full_name":REPO}}}

    def history(self, missing=None, nonlinear=False):
        def fake(path, token):
            for sha,parent in ((self.target,self.middle),(self.middle,self.old)):
                if path == "/commits/" + sha:
                    parents=[{"sha":parent}]
                    if nonlinear and sha==self.target:
                        parents.append({"sha":self.old})
                    return {"sha":sha,"commit":{"tree":{"sha":self.tree}},"parents":parents}
                if path == "/commits/" + sha + "/pulls?per_page=100":
                    return [] if sha==missing else [self.pr(sha)]
            raise AssertionError(path)
        return fake

    def test_exact_merged_pr_only(self):
        pr=self.pr(self.target)
        self.assertTrue(merged_pr(pr,self.target))
        for change in ({"merge_commit_sha":self.middle},{"merged_at":None},{"state":"open"},
                       {"base":{"ref":"dev","repo":{"full_name":REPO}}},
                       {"base":{"ref":"main","repo":{"full_name":"other/repo"}}}):
            self.assertFalse(merged_pr({**pr,**change},self.target))

    def test_all_intervening_squash_commits_required(self):
        with patch("worker.api",side_effect=self.history()):
            self.assertEqual(verify_merged_history(self.old,self.target,"test"),self.tree)
        for missing in (self.target,self.middle):
            with patch("worker.api",side_effect=self.history(missing=missing)):
                with self.assertRaisesRegex(RuntimeError,"not an exact merged main PR"):
                    verify_merged_history(self.old,self.target,"test")
        with patch("worker.api",side_effect=self.history(nonlinear=True)):
            with self.assertRaisesRegex(RuntimeError,"Nonlinear"):
                verify_merged_history(self.old,self.target,"test")

    def test_ci_tree_pinned_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            pin=Path(temporary)/"approved-ci-tree"
            pin.write_text(self.approved)
            result={"sha":self.tree,"truncated":False,"tree":[{"path":".github","type":"tree","mode":"040000","sha":self.approved}]}
            with patch("worker.CONFIG",Path(temporary)),patch("worker.root_file",side_effect=lambda p:p):
                with patch("worker.api",return_value=result):
                    verify_ci_tree(self.tree,"test")
                for bad in ({**result,"truncated":True},{**result,"tree":[]},
                            {**result,"tree":[{**result["tree"][0],"sha":self.old}]}):
                    with patch("worker.api",return_value=bad):
                        with self.assertRaises(RuntimeError):
                            verify_ci_tree(self.tree,"test")
                pin.unlink()
                with self.assertRaises(FileNotFoundError):
                    verify_ci_tree(self.tree,"test")

if __name__=="__main__":
    unittest.main()
