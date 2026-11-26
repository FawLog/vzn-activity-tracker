import unittest
from unittest.mock import patch
from repository_status import classify, snapshot, Cache, REPO

class RepositoryStatusTests(unittest.TestCase):
    sha="a"*40
    def run_data(self, **changes):
        return {"head_sha":self.sha,"head_branch":"main","event":"push",
                "path":".github/workflows/ci.yml","head_repository":{"full_name":REPO},
                "id":1,"status":"completed","conclusion":"success",**changes}
    def test_exact_main_ci(self):
        self.assertEqual(classify([self.run_data()],self.sha),"success")
        self.assertEqual(classify([self.run_data(event="pull_request")],self.sha),"unknown")
        self.assertEqual(classify([self.run_data(head_sha="b"*40)],self.sha),"unknown")
        self.assertEqual(classify([self.run_data(),self.run_data(id=2,status="in_progress")],self.sha),"running")
        self.assertEqual(classify([self.run_data(conclusion="failure")],self.sha),"failed")
    def test_independent_main_query(self):
        with patch("repository_status.get_json",side_effect=[{"commit":{"sha":self.sha}},{"workflow_runs":[self.run_data()]}]) as api:
            result=snapshot("test")
            self.assertEqual(result["sha"],self.sha)
            self.assertEqual(result["ci"],"success")
            self.assertEqual(api.call_args_list[0].args[0],"/branches/main")
            self.assertEqual(set(result),{"sha","ci","checked_at"})
    def test_cache_and_no_stale_success_on_failure(self):
        value={"sha":self.sha,"ci":"success"}
        with patch("repository_status.snapshot",side_effect=[value,RuntimeError("network")]) as get:
            cache=Cache("test")
            self.assertEqual(cache.get(),value)
            self.assertEqual(cache.get(),value)
            self.assertEqual(get.call_count,1)
            cache.expires=0
            self.assertIsNone(cache.get())
            self.assertIsNone(cache.get())
            self.assertEqual(get.call_count,2)
