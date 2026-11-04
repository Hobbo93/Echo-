"""Tests for Echo's shared memory. Run: py -m unittest discover tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_memory  # noqa: E402


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        self.saved = (echo_memory.DB_PATH, echo_memory.OLD_PERSONALITY, echo_memory.OLD_JSON_MEMORY)
        echo_memory.DB_PATH = folder / "memory.db"
        echo_memory.OLD_PERSONALITY = folder / "personality.json"
        echo_memory.OLD_JSON_MEMORY = folder / "old.json"

    def tearDown(self):
        echo_memory.DB_PATH, echo_memory.OLD_PERSONALITY, echo_memory.OLD_JSON_MEMORY = self.saved
        self.tmp.cleanup()

    def test_remember_recall_forget(self):
        first = echo_memory.remember("about_you", "I run a dog store called Furventure")
        self.assertEqual(first, echo_memory.remember("about_you", "i run a dog store called furventure"))
        self.assertEqual(echo_memory.count(), 1)
        self.assertEqual(echo_memory.recall("about_you")[0]["id"], first)
        self.assertTrue(echo_memory.forget(first))
        self.assertFalse(echo_memory.forget(first))

    def test_relevant_finds_only_matching(self):
        echo_memory.remember("about_you", "My favourite colour is green")
        echo_memory.remember("business", "Shopify store sells waterproof dog jackets")
        echo_memory.remember("business", "Leads come from southern Adelaide")
        found = [r["content"] for r in echo_memory.relevant("what should my dog jackets cost?")]
        self.assertEqual(found, ["Shopify store sells waterproof dog jackets"])
        self.assertEqual(echo_memory.relevant("hi echo"), [])

    def test_context_includes_facts_and_matches(self):
        echo_memory.remember("about_you", "Call me Hobbo")
        echo_memory.remember("business", "Adelaide plumbers need websites")
        text = echo_memory.context_for("any plumbers today?")
        self.assertIn("Call me Hobbo", text)
        self.assertIn("plumbers need websites", text)
        self.assertEqual(echo_memory.context_for("anything", always=()), "")

    def test_summary_after_long_chat(self):
        for i in range(12):
            echo_memory.log_turn("test", f"question {i}", f"answer {i}", summarise=False)
        summary = echo_memory.summarise_channel("test", ask=lambda prompt: "- Planned the jacket launch")
        self.assertEqual(summary, "- Planned the jacket launch")
        self.assertIn("jacket launch", echo_memory.last_summary("test"))
        # Nothing left to summarise now.
        self.assertIsNone(echo_memory.summarise_channel("test", ask=lambda prompt: "x"))

    def test_offline_model_keeps_messages(self):
        for i in range(3):
            echo_memory.log_turn("test", f"q{i}", f"a{i}", summarise=False)

        def offline(prompt):
            raise OSError("Ollama is not running")
        self.assertIsNone(echo_memory.summarise_channel("test", ask=offline))
        self.assertEqual(echo_memory.last_summary("test"), "")

    def test_finished_chats_get_summarised(self):
        for i in range(3):
            echo_memory.log_turn("phone", f"q{i}", f"a{i}", summarise=False)
        echo_memory._ask_model, real = (lambda prompt: "- Talked about stock"), echo_memory._ask_model
        try:
            self.assertEqual(echo_memory.summarise_finished_chats(quiet_minutes=15), 0)  # still going
            self.assertEqual(echo_memory.summarise_finished_chats(quiet_minutes=-1), 1)  # chat over
        finally:
            echo_memory._ask_model = real
        self.assertIn("stock", echo_memory.last_summary("phone"))

    def test_migrate_old_files_once(self):
        echo_memory.OLD_PERSONALITY.write_text(json.dumps({"facts": ["I like short replies"]}))
        echo_memory.OLD_JSON_MEMORY.write_text(json.dumps({"store": "Furventure"}))
        self.assertEqual(echo_memory.migrate(), 2)
        self.assertEqual(echo_memory.migrate(), 0)
        contents = {r["content"] for r in echo_memory.recall()}
        self.assertEqual(contents, {"I like short replies", "store: Furventure"})


if __name__ == "__main__":
    unittest.main()
