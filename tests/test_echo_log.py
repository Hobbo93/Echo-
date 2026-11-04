"""Tests for Echo's error log (echo_log.py)."""
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_log  # noqa: E402


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (echo_log.LOG_DIR, echo_log.MAX_BYTES)
        echo_log.LOG_DIR = Path(self.tmp.name)

    def tearDown(self):
        echo_log.LOG_DIR, echo_log.MAX_BYTES = self.saved
        self.tmp.cleanup()

    def test_write_and_summarise(self):
        echo_log.error("Trade scan failed", RuntimeError("no internet"))
        echo_log.error("Trade scan failed", RuntimeError("still no internet"))
        echo_log.error("echo_phone", note="call dropped")
        text = echo_log.summary()
        self.assertIn("3 problems", text)
        self.assertIn("Trade scan failed", text)
        self.assertIn("×2", text)
        self.assertIn("still no internet", text)

    def test_no_problems_means_empty_summary(self):
        self.assertEqual(echo_log.summary(), "")

    def test_secrets_are_hidden(self):
        echo_log.error("telegram", RuntimeError("bad url 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ token=abc123"))
        echo_log.error("shopify", note="sent shpat_0123456789abcdef")
        written = echo_log.log_file().read_text()
        self.assertNotIn("AAHdqTcv", written)
        self.assertNotIn("abc123", written)
        self.assertNotIn("shpat_0123", written)
        self.assertIn("[hidden]", written)

    def test_old_problems_drop_out(self):
        old = (datetime.now() - timedelta(hours=30)).isoformat(timespec="seconds")
        echo_log.LOG_DIR.mkdir(exist_ok=True)
        echo_log.log_file().write_text(f"{old}\techo\told thing\tbroke\n")
        echo_log.error("new thing", note="broke")
        self.assertEqual([r["where"] for r in echo_log.recent(24)], ["new thing"])

    def test_log_rotates(self):
        echo_log.MAX_BYTES = 200
        for i in range(10):
            echo_log.error("spam", note="x" * 50)
        self.assertTrue((echo_log.LOG_DIR / "errors.1.log").exists())
        self.assertGreater(len(echo_log.recent()), 1)

    def test_morning_report_once_a_day(self):
        echo_log.error("Trade scan failed", RuntimeError("no internet"))
        state = {}
        now = time.time()
        self.assertIn("Trade scan failed", echo_log.since_last_report(state, now))
        self.assertEqual(echo_log.since_last_report(state, now), "")

    def test_never_raises(self):
        echo_log.LOG_DIR = Path(self.tmp.name) / "file_not_dir"
        echo_log.LOG_DIR.write_text("blocking")
        echo_log.error("anything", note="still fine")  # can't write, but doesn't crash


if __name__ == "__main__":
    unittest.main()
