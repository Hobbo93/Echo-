"""Tests for the offices' daily jobs (echo_office_jobs.py) with a fake inbox, AI and trends."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_business  # noqa: E402
import echo_email  # noqa: E402
import echo_office_jobs as oj  # noqa: E402

TRENDS = b"<rss><channel><item><title>afl grand final</title></item><item><title>melbourne cup</title></item></channel></rss>"
IDEAS = json.dumps([{"title": "Dogs react to the Melbourne Cup", "hook": "Wait for the end", "outline": "a, b, c",
                     "caption": "Too funny #dogs"}])


def mail(frm, subject, body, extra=""):
    return (f"From: {frm}\r\nSubject: {subject}\r\nMessage-ID: <{subject}@x>\r\n{extra}"
            f"Content-Type: text/plain\r\n\r\n{body}\r\n").encode()


class FakeBox:
    def __init__(self, msgs):
        self.msgs = msgs

    def select(self, *a, **k):
        return "OK", [b""]

    def search(self, *a):
        return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.msgs)))]

    def fetch(self, num, what):
        return "OK", [(b"1 (BODY[] {1}", self.msgs[int(num) - 1])]

    def logout(self):
        pass


class OfficeJobsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (echo_business.DIR, oj.SEEN, echo_email._settings, echo_email.propose)
        echo_business.DIR, oj.SEEN = d / "biz", d / "seen.json"
        echo_email._settings = lambda: ("me@gmail.com", "app-password")
        self.proposed = []
        echo_email.propose = lambda to, subject, body, who="", after=None: self.proposed.append((to, subject)) or ("msg", True)

    def tearDown(self):
        echo_business.DIR, oj.SEEN, echo_email._settings, echo_email.propose = self.saved
        self.tmp.cleanup()

    def test_ideas_use_trends_and_niche(self):
        self.assertIn("funny animals", oj.handle("my channels are about funny animals"))
        prompts = []
        text = oj.content_ideas(ask=lambda p: prompts.append(p) or IDEAS, fetch=lambda url: TRENDS,
                                find=lambda q: "LONG VIDEOS for " + q)
        self.assertIn("afl grand final", text)
        self.assertIn("1. Dogs react to the Melbourne Cup", text)
        self.assertIn("LONG VIDEOS for find long videos about funny animals", text)
        self.assertIn("funny animals", prompts[0])

    def test_ideas_survive_ai_off(self):
        def off(p):
            raise OSError("Ollama off")
        text = oj.content_ideas(ask=off, fetch=lambda url: TRENDS, find=lambda q: "")
        self.assertIn("busy or off", text)

    def test_inbox_makes_tickets_and_skips_newsletters(self):
        box = FakeBox([mail("Jane Smith <jane@example.com>", "Where is my order?", "Ordered a dog bed last week."),
                       mail("Shop News <news@brand.com>", "Big sale", "50% off", "List-Unsubscribe: <x>\r\n"),
                       mail("YouTube <no-reply@youtube.com>", "New comment", "hi")])
        said = []
        self.assertEqual(oj.check_inbox(connect=lambda: box, notify=said.append), 1)
        self.assertIn("Where is my order?", said[0])
        self.assertEqual(echo_business.load("tickets", [])[0]["email"], "jane@example.com")
        self.assertEqual(oj.check_inbox(connect=lambda: box, notify=said.append), 0)  # not twice

    def test_send_reply_needs_yes(self):
        box = FakeBox([mail("Jane Smith <jane@example.com>", "Refund please", "It arrived broken.")])
        oj.check_inbox(connect=lambda: box)
        echo_business.ask_ai, saved = (lambda *a, **k: "Sorry Jane, refund on its way. - Tailen"), echo_business.ask_ai
        try:
            self.assertIn("tap Yes", oj.handle("send reply 1"))
        finally:
            echo_business.ask_ai = saved
        self.assertEqual(self.proposed, [("jane@example.com", "Re: Refund please")])

    def test_store_report_only_when_connected(self):
        import echo_shopify
        saved = echo_shopify.is_configured
        echo_shopify.is_configured = lambda: False
        try:
            self.assertEqual(oj.store_report(), "")
        finally:
            echo_shopify.is_configured = saved


if __name__ == "__main__":
    unittest.main()
