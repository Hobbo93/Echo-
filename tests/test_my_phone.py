"""Saving the owner's phone number on the PC (echo_phone.set_my_phone). Uses a made-up number."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_phone  # noqa: E402


class MyPhoneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = echo_phone.CONFIG
        echo_phone.CONFIG = Path(self.tmp.name) / "cfg.json"
        echo_phone.CONFIG.write_text(json.dumps({"bot_token": "keep-me"}))

    def tearDown(self):
        echo_phone.CONFIG = self.saved
        self.tmp.cleanup()

    def test_formats(self):
        for raw in ["0412 345 678", "0412345678", "61412345678", "+61 412 345 678", "(04) 1234-5678"]:
            self.assertEqual(echo_phone.normalise_phone(raw), "+61412345678", raw)
        self.assertEqual(echo_phone.normalise_phone("12345"), "")

    def test_saves_without_touching_other_settings(self):
        reply = echo_phone.set_my_phone("0412 345 678")
        data = json.loads(echo_phone.CONFIG.read_text())
        self.assertEqual(data["my_phone"], "+61412345678")
        self.assertEqual(data["bot_token"], "keep-me")
        self.assertIn("Twilio", reply)  # honest: calls still need Twilio

    def test_bad_number(self):
        self.assertIn("doesn't look like", echo_phone.set_my_phone("hello"))


if __name__ == "__main__":
    unittest.main()
