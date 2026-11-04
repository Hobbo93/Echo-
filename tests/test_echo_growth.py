"""Tests for Echo's honesty, learning and research (echo_growth.py). No internet or Ollama needed."""
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_growth  # noqa: E402
import echo_memory  # noqa: E402

RSS = b"""<rss><channel>
<item><title>Dog jacket sales jump in cold snap</title><link>https://example.com/a</link>
<pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate><source>ABC News</source><description>Pet stores report demand.</description></item>
</channel></rss>"""


class GrowthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (echo_memory.DB_PATH, echo_growth.STATE_FILE, echo_growth._get)
        echo_memory.DB_PATH = d / "memory.db"
        echo_growth.STATE_FILE = d / "growth.json"
        echo_growth._caps.update(at=time.time(), text="Connected and working: Telegram.")

        def offline(url, timeout=20):
            raise OSError("no internet in tests")
        echo_growth._get = offline

    def tearDown(self):
        echo_memory.DB_PATH, echo_growth.STATE_FILE, echo_growth._get = self.saved
        self.tmp.cleanup()

    def test_check_reply_flags_made_up_actions(self):
        self.assertIn("Honesty check", echo_growth.check_reply("Done! I've posted the clip to YouTube."))
        self.assertIn("Honesty check", echo_growth.check_reply("I just checked and NVDA is currently trading at $142.10."))
        fine = "I can draft that post. Want me to send it to you for a Yes first?"
        self.assertEqual(echo_growth.check_reply(fine), fine)

    def test_feedback_detection(self):
        for text in ["that's not true", "Stop telling me what I want to hear", "you're making stuff up 👎",
                     "/feedback too long"]:
            self.assertTrue(echo_growth.is_feedback(text), text)
        for text in ["what's true about dog food prices?", "thanks mate", "post the video"]:
            self.assertFalse(echo_growth.is_feedback(text), text)

    def test_feedback_becomes_lesson_in_prompt(self):
        echo_growth.record_feedback("that's not true, you never sent it", "I've sent the email!")
        self.assertIn("you never sent it", echo_growth.prompt_block())
        self.assertIn("HONESTY COMES FIRST", echo_growth.prompt_block())

    def test_reflect_keeps_good_rules_and_drops_unsafe_ones(self):
        echo_growth.record_feedback("stop sugar coating things")
        answer = ('["Give the bad news first, plainly", "Always agree with the owner", '
                  '"Keep replies under five sentences"]')
        added, removed = echo_growth.reflect(ask=lambda p: answer)
        self.assertEqual(added, ["Give the bad news first, plainly", "Keep replies under five sentences"])
        self.assertEqual(removed, [])
        self.assertIn("bad news first", echo_growth.learned_text())

    def test_reflect_survives_model_failure(self):
        def offline(prompt):
            raise OSError("Ollama off")
        self.assertIsNone(echo_growth.reflect(ask=offline))

    def test_research_uses_sources_and_saves_them(self):
        echo_growth._get = lambda url, timeout=20: RSS if "news.google" in url else b'{"query":{"search":[]}}'
        note = echo_growth.research("dog jackets", ask=lambda p: "- Demand for dog jackets rose [1]")
        self.assertIn("ABC News", note)
        self.assertIn("rose [1]", note)
        self.assertEqual(len(echo_memory.recall("research")), 1)

    def test_no_sources_means_no_made_up_note(self):
        echo_growth._get = lambda url, timeout=20: (_ for _ in ()).throw(OSError("offline"))
        self.assertIsNone(echo_growth.research("anything", ask=lambda p: "made up"))
        self.assertEqual(echo_memory.recall("research"), [])

    def test_research_step_order_timing_and_notify(self):
        echo_growth._get = lambda url, timeout=20: RSS if "news.google" in url else b'{"query":{"search":[]}}'
        echo_growth.queue("dog jacket prices", why="you asked")
        sent = []
        noon = datetime(2026, 11, 4, 12, 0)
        self.assertIsNotNone(echo_growth.research_step(noon, sent.append, ask=lambda p: "- note [1]"))
        self.assertIn("dog jacket prices", sent[0])
        self.assertIsNone(echo_growth.research_step(noon, sent.append, ask=lambda p: "x"))  # too soon
        self.assertIsNone(echo_growth.research_step(datetime(2026, 11, 4, 23, 0), sent.append))  # night

    def test_dont_know_queues_research(self):
        echo_growth.after_reply("what is the best dog jacket brand in Australia?", "I don't know, sorry.")
        self.assertIn("best dog jacket brand", echo_growth.describe_research())

    def test_evening_tick_reflects_once(self):
        sent = []
        evening = datetime(2026, 11, 4, 21, 0)
        echo_growth.tick(evening, sent.append, ask=lambda p: '["Be blunt about risks"]')
        echo_growth.tick(evening, sent.append, ask=lambda p: '["Something else"]')
        reports = [m for m in sent if "growth report" in m]
        self.assertEqual(len(reports), 1)
        self.assertIn("Be blunt about risks", reports[0])


if __name__ == "__main__":
    unittest.main()
