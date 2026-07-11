"""Tests for persistent Gmail job store used by /reply_job."""

import tempfile
import unittest

from gmail_agent.job_store import delete_job, get_job, save_job


class TestGmailJobStore(unittest.TestCase):
    def test_save_get_delete_job(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        job = {
            "email_id": "email-123",
            "title": "AI bot",
            "platform": "Freelancehunt",
            "score": 8.5,
            "reason": "Relevant",
            "budget": "5000 UAH",
            "url": "https://example.com/job",
            "urgency": "medium",
            "why_relevant": "AI automation",
        }

        save_job(job, path=path)

        loaded = get_job("email-123", path=path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["title"], "AI bot")

        self.assertTrue(delete_job("email-123", path=path))
        self.assertIsNone(get_job("email-123", path=path))

    def test_invalid_json_is_treated_as_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f:
            f.write("{broken")
            path = f.name

        self.assertIsNone(get_job("missing", path=path))
        self.assertFalse(delete_job("missing", path=path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
