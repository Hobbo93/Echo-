"""Tests for the health check (echo_health.py) with every part faked."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_backup  # noqa: E402
import echo_health as h  # noqa: E402


class HealthTest(unittest.TestCase):
    def setUp(self):
        self.saved = list(h.SECTIONS), echo_backup.last_backup

    def tearDown(self):
        h.SECTIONS[:], echo_backup.last_backup = self.saved

    def test_all_good(self):
        h.SECTIONS[:] = [("A", lambda: [(h.OK, "fine")]), ("B", lambda: [(h.OK, "fine too")])]
        self.assertTrue(h.report().startswith("✅"))

    def test_worst_problem_sets_the_headline(self):
        h.SECTIONS[:] = [("A", lambda: [(h.WARN, "meh")]), ("B", lambda: [(h.BAD, "broken. Fix: do X")])]
        text = h.report()
        self.assertIn("something needs fixing", text)
        self.assertIn("Fix: do X", text)

    def test_a_crashing_check_doesnt_stop_the_report(self):
        def boom():
            raise RuntimeError("no Ollama")
        h.SECTIONS[:] = [("A", boom), ("B", lambda: [(h.OK, "fine")])]
        text = h.report()
        self.assertIn("Couldn't check: no Ollama", text)
        self.assertIn("fine", text)

    def test_backup_age(self):
        now = datetime(2026, 11, 10, 12, 0)
        echo_backup.last_backup = lambda: ""
        self.assertEqual(h.backup(now)[0][0], h.WARN)
        echo_backup.last_backup = lambda: (now - timedelta(days=5)).isoformat(timespec="minutes")
        self.assertEqual(h.backup(now)[0][0], h.BAD)
        echo_backup.last_backup = lambda: (now - timedelta(hours=5)).isoformat(timespec="minutes")
        self.assertEqual(h.backup(now)[0][0], h.OK)

    def test_disk_space_reads(self):
        level, text = h.disk("/")[0]
        self.assertIn("GB free", text)


if __name__ == "__main__":
    unittest.main()
