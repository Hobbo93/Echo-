"""Tests for routing plain-English Telegram requests to the real tools (echo_router.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_router as r  # noqa: E402


class RouterTest(unittest.TestCase):
    def test_connection_questions_use_real_checks(self):
        for t in ["are you connected to shopify?", "Is my Instagram linked", "can you post to tiktok?",
                  "what's connected?", "/connections", "do you have access to my gmail?"]:
            self.assertEqual(r.route(t), ("connections", None), t)
        for t in ["post clip 1 to youtube", "set up a discount code for 10% off", "thanks!"]:
            self.assertNotEqual(r.route(t), ("connections", None), t)

    def test_clip_requests(self):
        self.assertEqual(r.route("can you clip this https://youtu.be/abc123 please"), ("opus", "/clip https://youtu.be/abc123"))
        self.assertEqual(r.route("make clips from my latest video"), ("opus", "/clip latest"))
        self.assertEqual(r.route("post clip 2 to youtube and instagram"), ("opus", "/post 2 youtube instagram"))
        self.assertEqual(r.route("schedule the 1st clip on tiktok tomorrow at 9am"),
                         ("opus", "/post 1 tiktok tomorrow at 9am"))
        self.assertEqual(r.route("upload clip #3 everywhere in 2 hours"), ("opus", "/post 3 everywhere in 2 hours"))
        self.assertEqual(r.route("show me my clips"), ("opus", "/clips"))

    def test_store_requests(self):
        for t in ["change the dog bed price to $49", "add a waterproof dog jacket to my store, $39.95",
                  "make a 15% off discount code SPRING15", "show my latest orders", "what's selling on Furventure?"]:
            self.assertEqual(r.route(t), ("shopify", t), t)
        for t in ["show me NVDA stock", "what's the price of bitcoin", "set the price of my roblox map idea"]:
            self.assertNotEqual(r.route(t)[0] if r.route(t) else None, "shopify", t)

    def test_email_requests(self):
        self.assertEqual(r.route("can you send Joe's Plumbing an email about a new website"),
                         ("email", "/email Joe's Plumbing about a new website"))
        self.assertEqual(r.route("please email bob@example.com saying hi"), ("email", "/email bob@example.com saying hi"))

    def test_chat_and_commands_pass_through(self):
        for t in ["hey echo how are you", "/trade propose", "yes", "tell me a joke"]:
            self.assertIsNone(r.route(t), t)

    def test_honest_answer_lists_only_what_was_asked(self):
        import echo_connections
        real = echo_connections.check_all
        echo_connections.check_all = lambda live=False: [
            {"office": "Shopify Manager", "service": "Your Shopify store", "ok": False, "detail": "",
             "how": "SHOPIFY_SETUP.md, then connect_echo.bat", "does": ""},
            {"office": "Content Creator", "service": "OpusClip", "ok": True, "detail": "Can post to: YouTube",
             "how": "", "does": ""}]
        try:
            text = r.answer_connections("are you connected to shopify?")
        finally:
            echo_connections.check_all = real
        self.assertIn("🔴 Shopify Manager", text)
        self.assertIn("NOT connected", text)
        self.assertNotIn("OpusClip", text)


if __name__ == "__main__":
    unittest.main()
