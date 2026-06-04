"""Tests for EmailDedup — runs without any external dependencies."""

import sys
import os
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.dedup import EmailDedup


class TestEmailDedup(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        self.dedup = EmailDedup(self._tmp.name)
        self.dedup.clear()

    def tearDown(self):
        try:
            os.unlink(self._tmp.name)
        except FileNotFoundError:
            pass

    def test_new_email_not_processed(self):
        self.assertFalse(self.dedup.is_processed("email_001"))

    def test_mark_and_check(self):
        self.dedup.mark_processed("email_001")
        self.assertTrue(self.dedup.is_processed("email_001"))

    def test_duplicate_not_returned_twice(self):
        self.dedup.mark_processed("email_002")
        self.dedup.mark_processed("email_002")  # mark again
        self.assertTrue(self.dedup.is_processed("email_002"))
        self.assertEqual(self.dedup.count(), 1)

    def test_persistence_across_instances(self):
        self.dedup.mark_processed("email_003")
        # Create new instance pointing to same file
        dedup2 = EmailDedup(self._tmp.name)
        self.assertTrue(dedup2.is_processed("email_003"))

    def test_mark_many(self):
        ids = ["e1", "e2", "e3"]
        self.dedup.mark_many(ids)
        for eid in ids:
            self.assertTrue(self.dedup.is_processed(eid))
        self.assertEqual(self.dedup.count(), 3)

    def test_clear(self):
        self.dedup.mark_processed("email_x")
        self.dedup.clear()
        self.assertFalse(self.dedup.is_processed("email_x"))
        self.assertEqual(self.dedup.count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
