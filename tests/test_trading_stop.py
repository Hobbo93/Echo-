"""Tests for "stop trading", "resume trading" and "sell everything" (fake broker and prices)."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_broker  # noqa: E402
import echo_trading as tr  # noqa: E402


class TradingStopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (tr.DIR, tr.JOURNAL, tr.PENDING, tr.SETTINGS, tr.live_price,
                      echo_broker.is_configured, echo_broker.positions, echo_broker.close_all)
        tr.DIR, tr.JOURNAL, tr.PENDING, tr.SETTINGS = d, d / "journal.json", d / "pending.json", d / "settings.json"
        tr.live_price = lambda sym: (100.0, "USD")
        self.closed = []
        echo_broker.is_configured = lambda: True
        echo_broker.positions = lambda: [{"symbol": "NVDA"}]
        echo_broker.close_all = lambda: self.closed.append("all") or []
        tr._save({"cash": 9000.0, "positions": {"AAPL": {"qty": 10, "entry": 90.0, "opened": "x"}}, "closed": []})

    def tearDown(self):
        (tr.DIR, tr.JOURNAL, tr.PENDING, tr.SETTINGS, tr.live_price,
         echo_broker.is_configured, echo_broker.positions, echo_broker.close_all) = self.saved
        self.tmp.cleanup()

    def _idea(self, side="buy"):
        tr.PENDING.write_text(json.dumps({"symbol": "MSFT", "side": side, "qty": 1, "entry": 1, "stop": 0.5,
                                          "target": 2, "created": datetime.now(timezone.utc).isoformat()}))

    def test_phrases(self):
        for t in ["stop trading", "Echo, stop trading", "hey echo stop all trading", "pause trading", "/stoptrading"]:
            self.assertTrue(tr.STOP_RE.match(t), t)
        for t in ["resume trading", "start trading", "/resumetrading"]:
            self.assertTrue(tr.RESUME_RE.match(t), t)
        for t in ["sell everything", "close all", "sell all my positions", "sell everything now", "/sellall"]:
            self.assertTrue(tr.SELL_ALL_RE.match(t), t)
        for t in ["sell AAPL", "stop", "stop the music", "close all the tabs"]:
            self.assertFalse(tr.STOP_RE.match(t) or tr.SELL_ALL_RE.match(t), t)

    def test_stop_pauses_cancels_idea_and_keeps_positions(self):
        self._idea()
        msg = tr.handle("stop trading")
        self.assertIn("Trading stopped", msg)
        self.assertIn("MSFT trade idea was cancelled", msg)
        self.assertIn("NVDA", msg)
        self.assertIn("AAPL", msg)
        self.assertTrue(tr.is_paused())
        self.assertIsNone(tr.pending())
        self.assertEqual(self.closed, [])  # stopping doesn't sell anything

    def test_paused_blocks_new_trades(self):
        tr.handle("stop trading")
        self.assertIn("paused", tr.send_idea_to_phone())
        self.assertIn("paused", tr.amount_trade("AAPL", 500))
        self._idea()  # an old idea approved after the stop
        msg, _ = tr.approve()
        self.assertIn("Nothing was bought", msg)
        self.assertIn("back on", tr.handle("resume trading"))
        self.assertFalse(tr.is_paused())

    def test_sell_everything_needs_yes(self):
        msg = tr.handle("sell everything")
        self.assertIn("Reply Yes", msg)
        self.assertEqual(self.closed, [])
        result, _ = tr.approve()
        self.assertEqual(self.closed, ["all"])
        self.assertIn("NVDA", result)
        self.assertIn("Paper sold 10 AAPL", result)
        self.assertEqual(tr._load()["positions"], {})

    def test_sell_everything_works_while_paused_and_no_cancels(self):
        tr.handle("stop trading")
        tr.handle("sell everything")
        self.assertIn("No trade placed", tr.skip())
        self.assertEqual(self.closed, [])
        tr.handle("sell everything")
        tr.approve()
        self.assertEqual(self.closed, ["all"])

    def test_nothing_open(self):
        echo_broker.positions = lambda: []
        tr._save({"cash": 10000.0, "positions": {}, "closed": []})
        self.assertIn("Nothing to sell", tr.handle("sell everything"))


if __name__ == "__main__":
    unittest.main()
