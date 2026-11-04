"""Tests for connecting accounts from the phone (echo_connect.py). All keys are made up."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_connect as c  # noqa: E402


class ConnectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (c.CONFIG, c.STATE, c._test)
        c.CONFIG, c.STATE = d / "cfg.json", d / "state.json"
        c.CONFIG.write_text(json.dumps({"bot_token": "keep"}))
        c._test = lambda svc: (True, "Test passed")

    def tearDown(self):
        c.CONFIG, c.STATE, c._test = self.saved
        self.tmp.cleanup()

    def cfg(self):
        return json.loads(c.CONFIG.read_text())

    def test_menu_shows_status(self):
        text, delete = c.handle("/connect")
        self.assertIn("🔴 1. OpusClip", text)
        self.assertFalse(delete)

    def test_shopify_walkthrough_saves_and_deletes(self):
        text, _ = c.handle("/connect 2")
        self.assertIn("dev.shopify.com", text)
        reply, delete = c.handle("ok")
        self.assertTrue(delete)
        self.assertEqual(self.cfg()["shopify_store"], "thedogden-2.myshopify.com")
        c.handle("abcdef0123456789abcdef0123456789")
        reply, delete = c.handle("fake-secret-value-1234567890")
        self.assertTrue(delete)
        self.assertIn("🟢 Shopify", reply)
        self.assertEqual(self.cfg()["bot_token"], "keep")  # other settings untouched
        self.assertFalse(c.active())
        self.assertIn("🟢 2. Shopify", c.menu())

    def test_wrong_format_asks_again(self):
        c.handle("/connect 3")
        reply, _ = c.handle("not an email")
        self.assertIn("full Gmail address", reply)
        c.handle("me@gmail.com")
        reply, delete = c.handle("abcd efgh ijkl mnop")
        self.assertEqual(self.cfg()["gmail_app_password"], "abcdefghijklmnop")
        self.assertTrue(delete)

    def test_failed_test_is_honest(self):
        c._test = lambda svc: (False, "OpusClip rejected the API key")
        c.handle("/connect opusclip")
        reply, _ = c.handle("x" * 30)
        self.assertIn("🔴", reply)
        self.assertIn("rejected", reply)

    def test_cancel_and_not_mine(self):
        c.handle("/connect 1")
        self.assertIn("Stopped", c.handle("cancel")[0])
        self.assertIsNone(c.handle("how are you"))

    def test_secret_guard(self):
        for t in ["shpat_0123456789", "abcd efgh ijkl mnop", "x" * 32]:
            self.assertTrue(c.looks_like_secret(t), t)
        for t in ["how are you going today mate", "find videos about dogs", "my number is 0412 345 678"]:
            self.assertFalse(c.looks_like_secret(t), t)


if __name__ == "__main__":
    unittest.main()
