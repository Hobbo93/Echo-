"""Tests for Echo's optional Claude brain (echo_ai.py) with a fake Anthropic client. Nothing is charged."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_ai as ai  # noqa: E402


class FakeAPI:
    def __init__(self, text="Hi from Claude", stop="end_turn", fail=False):
        self.calls = []
        self.text, self.stop, self.fail = text, stop, fail
        self.messages = NS(create=lambda **kw: self._reply("plain", kw))
        self.beta = NS(messages=NS(create=lambda **kw: self._reply("beta", kw)))

    def _reply(self, kind, kw):
        self.calls.append((kind, kw))
        if self.fail:
            raise OSError("no internet")
        usage = NS(input_tokens=2000, output_tokens=300, cache_read_input_tokens=0, cache_creation_input_tokens=0)
        return NS(content=[NS(type="thinking", thinking=""), NS(type="text", text=self.text)],
                  stop_reason=self.stop, usage=usage, model=kw["model"])


class ClaudeBrainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (ai.CONFIG, ai.SETTINGS, ai.USAGE)
        ai.CONFIG, ai.SETTINGS, ai.USAGE = d / "cfg.json", d / "ai.json", d / "usage.json"
        ai.CONFIG.write_text(json.dumps({"anthropic_api_key": "sk-ant-fake-key-for-tests-0000000000"}))

    def tearDown(self):
        ai.CONFIG, ai.SETTINGS, ai.USAGE = self.saved
        self.tmp.cleanup()

    def msgs(self):
        return [{"role": "system", "content": "You are Echo."}, {"role": "assistant", "content": "earlier"},
                {"role": "user", "content": "hello"}]

    def test_off_by_default(self):
        api = FakeAPI()
        self.assertIsNone(ai.try_claude(self.msgs(), client=api))
        self.assertEqual(api.calls, [])  # nothing sent, nothing charged

    def test_main_brain_defaults_to_sonnet(self):
        ai.handle("/brain claude")
        api = FakeAPI()
        ai.try_claude(self.msgs(), "main", client=api)
        self.assertEqual(api.calls[0][:1] + (api.calls[0][1]["model"],), ("plain", "claude-sonnet-5-5"))
        self.assertIn("Sonnet 5.5", ai.describe())

    def test_main_brain_opus_with_fallbacks_and_caching(self):
        ai.handle("/brain claude opus")
        api = FakeAPI()
        self.assertEqual(ai.try_claude(self.msgs(), "main", client=api), "Hi from Claude")
        kind, kw = api.calls[0]
        self.assertEqual((kind, kw["model"], kw["fallbacks"]), ("beta", "claude-opus-5-5", "default"))
        self.assertEqual(kw["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(kw["messages"][0]["role"], "user")  # can't start with the assistant
        self.assertEqual(kw["output_config"], {"effort": "low"})
        self.assertAlmostEqual(ai.spent(), (2000 * 4 + 300 * 20) / 1e6)

    def test_second_brain_is_haiku(self):
        ai.handle("/brain claude")
        api = FakeAPI()
        ai.try_claude(self.msgs(), "background", client=api)
        kind, kw = api.calls[0]
        self.assertEqual((kind, kw["model"]), ("plain", "claude-haiku-5-5"))

    def test_sonnet_option(self):
        ai.handle("/brain claude sonnet")
        api = FakeAPI()
        ai.try_claude(self.msgs(), "main", client=api)
        self.assertEqual(api.calls[0][1]["model"], "claude-sonnet-5-5")
        self.assertIn("Sonnet 5.5", ai.describe())
        ai.handle("/brain claude opus")
        ai.try_claude(self.msgs(), "main", client=api)
        self.assertEqual(api.calls[1][1]["model"], "claude-opus-5-5")

    def test_budget_stops_claude(self):
        ai.handle("/brain claude")
        ai.handle("/brain budget 0.005")
        api = FakeAPI()
        ai.try_claude(self.msgs(), client=api)  # $0.014: goes over the tiny limit
        self.assertIsNone(ai.try_claude(self.msgs(), client=api))
        self.assertEqual(len(api.calls), 1)
        self.assertIn("Limit reached", ai.describe())

    def test_failures_and_refusals_fall_back_to_local(self):
        ai.handle("/brain claude")
        self.assertIsNone(ai.try_claude(self.msgs(), client=FakeAPI(fail=True)))
        self.assertIsNone(ai.try_claude(self.msgs(), client=FakeAPI(stop="refusal")))

    def test_photos_go_as_images(self):
        ai.handle("/brain claude")
        api = FakeAPI()
        ai.try_claude([{"role": "user", "content": "what's this?"}], images=[b"\x89PNG\r\n\x1a\nfake"], client=api)
        blocks = api.calls[0][1]["messages"][-1]["content"]
        self.assertEqual((blocks[0]["type"], blocks[0]["source"]["media_type"]), ("image", "image/png"))

    def test_commands(self):
        ai.CONFIG.write_text("{}")
        self.assertIn("/connect 5", ai.handle("/brain claude"))
        self.assertIn("free local brain", ai.handle("/brain local"))
        self.assertIsNone(ai.handle("/brain upgrade"))  # that's the local-model upgrade


if __name__ == "__main__":
    unittest.main()
