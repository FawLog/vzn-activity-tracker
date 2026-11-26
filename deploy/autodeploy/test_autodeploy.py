import hashlib
import hmac
import json
import unittest
from listener import valid_event, REPO
from worker import eligible, SHA

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

if __name__=="__main__":
    unittest.main()
