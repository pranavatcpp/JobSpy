import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from jobspy.career_ops import collect, identity, normalize


class AdapterTests(unittest.TestCase):
    def row(self, **kw):
        return {"title": "Engineer", "job_url": "https://board.example/job?id=1", **kw}

    def test_missing_fields_and_unsafe_urls(self):
        for row in (
            {},
            self.row(job_url="file:///tmp/a"),
            self.row(job_url="http://127.0.0.1/a"),
        ):
            self.assertIsNone(normalize(row, "indeed", "engineer", "CA", "today"))

    def test_date_and_salary_not_invented(self):
        job = normalize(
            self.row(date_posted=None, min_amount=50, interval="hourly"),
            "indeed",
            "engineer",
            "CA",
            "today",
        )
        self.assertNotIn("postedAt", job)
        self.assertNotIn("salary", job)
        self.assertEqual(job["sourceSalary"]["min"], 50)
        self.assertEqual(job["company"], "")
        job = normalize(
            self.row(date_posted="2026-10-27", min_amount=100000, interval="yearly"),
            "indeed",
            "e",
            "CA",
            "today",
        )
        self.assertEqual(job["datePosted"], "2026-10-27")
        self.assertEqual(job["salary"]["min"], 100000)

    def test_dedup_preserves_identity(self):
        self.assertEqual(
            identity("https://a.com/job?id=1&utm_source=x"), "https://a.com/job?id=1"
        )
        self.assertNotEqual(
            identity("https://a.com/job?id=1"), identity("https://a.com/job?id=2")
        )

    def test_duplicate_provenance_and_no_cache(self):
        response = SimpleNamespace(
            returncode=0, stdout=json.dumps({"rows": [self.row()], "errors": {}})
        )
        with patch("subprocess.run", return_value=response) as run, patch("time.sleep"):
            result = collect(["indeed", "linkedin"], ["Engineer"], ["CA"], 5, 48, 3, 0)
            self.assertEqual(len(result["jobs"]), 1)
            self.assertEqual(len(result["jobs"][0]["provenance"]), 2)
            self.assertEqual(run.call_count, 2)
            collect(["indeed"], ["Engineer"], ["CA"], 5, 48, 3, 0)
            self.assertEqual(run.call_count, 3)
            self.assertFalse(result["cacheReused"])

    def test_failure_is_not_empty_success(self):
        for response in [
            SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"rows": [], "errors": {"linkedin": "429"}}),
            ),
            SimpleNamespace(returncode=1, stderr="failed"),
        ]:
            with patch("subprocess.run", return_value=response):
                self.assertEqual(
                    collect(["linkedin"], ["Engineer"], ["CA"], 5, 48, 3, 0)["status"],
                    "error",
                )
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 3)
        ):
            self.assertEqual(
                collect(["linkedin"], ["Engineer"], ["CA"], 5, 48, 3, 0)["status"],
                "error",
            )

    def test_partial_preserves_good_jobs(self):
        ok = SimpleNamespace(returncode=0, stdout=json.dumps({"rows": [self.row()]}))
        bad = SimpleNamespace(
            returncode=0, stdout=json.dumps({"rows": [], "errors": {"linkedin": "429"}})
        )
        with patch("subprocess.run", side_effect=[ok, bad]), patch("time.sleep"):
            result = collect(["indeed", "linkedin"], ["Engineer"], ["CA"], 5, 48, 3, 0)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(len(result["jobs"]), 1)


if __name__ == "__main__":
    unittest.main()
