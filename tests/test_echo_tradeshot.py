"""Tests for reading chart screenshots (echo_tradeshot.py) with a fake vision model and fake prices."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_photos  # noqa: E402
import echo_trading  # noqa: E402
import echo_tradeshot as ts  # noqa: E402

ROWS = [(i, 100 + i * .5, 101 + i * .5, 99 + i * .5, 100.5 + i * .5, 1000) for i in range(80)]


class TradeshotTest(unittest.TestCase):
    def setUp(self):
        self.saved = (echo_photos.has_vision, echo_trading.candles, echo_trading.analyse)
        echo_photos.has_vision = lambda: True
        echo_trading.candles = lambda sym, *a, **k: (ROWS, {"regularMarketPrice": 140.0, "currency": "USD"})
        echo_trading.analyse = lambda sym: f"{sym} 140.00 USD\nCall: 🟢 UP\nRisk plan: stop 135, target 150"
        self.seen = '{"symbol": "NVDA", "price": 139.8, "timeframe": "5m", "what_i_see": "A strong uptrend."}'

    def tearDown(self):
        echo_photos.has_vision, echo_trading.candles, echo_trading.analyse = self.saved

    def look(self, image, question):
        return "Here you go: " + self.seen

    def test_when_to_read(self):
        for c in ["what do I do?", "should I buy this", "NVDA", "$tsla", "check this chart"]:
            self.assertTrue(ts.wants_trade_read(c), c)
        self.assertTrue(ts.wants_trade_read("", "Day Trading Desk"))
        for c in ["", "look at my dog", "is this jacket nice"]:
            self.assertFalse(ts.wants_trade_read(c), c)

    def test_ticker_from_caption(self):
        self.assertEqual(ts.ticker_from_caption("should I buy NVDA now?"), "NVDA")
        self.assertEqual(ts.ticker_from_caption("tsla"), "TSLA")
        self.assertEqual(ts.ticker_from_caption("$amd"), "AMD")
        self.assertIsNone(ts.ticker_from_caption("what do I do?"))

    def test_reads_screenshot_and_gives_plan_with_chart(self):
        reply, png = ts.analyse_screenshot(b"img", "what do I do?", look=self.look)
        self.assertIn("A strong uptrend", reply)
        self.assertIn("NVDA 140.00", reply)
        self.assertIn("never place trades", reply)
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_caption_ticker_wins(self):
        reply, _ = ts.analyse_screenshot(b"img", "TSLA what do I do", look=self.look)
        self.assertIn("TSLA 140.00", reply)

    def test_unreadable_screenshot_asks_for_ticker(self):
        self.seen = '{"symbol": null, "what_i_see": "Some candles."}'
        reply, png = ts.analyse_screenshot(b"img", "what do I do?", look=self.look)
        self.assertIsNone(png)
        self.assertIn("ticker as the caption", reply)

    def test_no_vision_but_ticker_still_works(self):
        echo_photos.has_vision = lambda: False
        reply, png = ts.analyse_screenshot(b"img", "NVDA")
        self.assertIn("NVDA 140.00", reply)
        reply, png = ts.analyse_screenshot(b"img", "what do I do?")
        self.assertIn("/getvision", reply)

    def test_bad_ticker_is_reported(self):
        def broken(sym):
            raise RuntimeError("no data for ZZZZ")
        echo_trading.analyse = broken
        reply, png = ts.analyse_screenshot(b"img", "ZZZZ", look=self.look)
        self.assertIsNone(png)
        self.assertIn("couldn't get its live prices", reply)


if __name__ == "__main__":
    unittest.main()
