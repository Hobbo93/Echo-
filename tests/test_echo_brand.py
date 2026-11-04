"""Tests for Brand Studio (echo_brand.py) with a fake AI, picture maker and store."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_brand as b  # noqa: E402
import echo_business  # noqa: E402
import echo_growth  # noqa: E402
import echo_shopify  # noqa: E402

IDEAS = json.dumps([{"name": "Lag Lord", "product": "hoodie", "design": "Pixel skull with the words LAG LORD",
                     "colours": "black, neon green", "why": "gamer humour"},
                    {"name": "Sunburnt Spawn", "product": "tee", "design": "Retro sunset over a respawn point",
                     "colours": "orange, purple", "why": "Aussie summer"}])


class BrandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (echo_business.DIR, echo_growth.STATE_FILE, echo_shopify.is_configured, echo_shopify.propose)
        echo_business.DIR, echo_growth.STATE_FILE = d / "biz", d / "growth.json"
        self.proposed = []
        echo_shopify.is_configured = lambda: True
        echo_shopify.propose = lambda plan: self.proposed.append(plan) or "Sent to your phone"

    def tearDown(self):
        echo_business.DIR, echo_growth.STATE_FILE, echo_shopify.is_configured, echo_shopify.propose = self.saved
        self.tmp.cleanup()

    def test_needs_a_brand_first(self):
        self.assertIn("my brand is", b.design_ideas(ask=lambda p: IDEAS))

    def test_full_flow(self):
        reply, _ = b.handle("my brand is Stringman, streetwear for Aussie gamers")
        self.assertIn("Stringman", reply)
        self.assertIn("streetwear trends Australia", echo_growth.describe_research())  # research queued
        self.assertIn("1. Lag Lord (hoodie)", b.design_ideas(ask=lambda p: IDEAS))
        msg, path = b.mockup(1, make=lambda prompt: Path(self.tmp.name) / "m.png")
        self.assertTrue(str(path).endswith("m.png"))
        text, item = b.listing(1, ask=lambda p: '{"title": "Lag Lord Hoodie", "description": "Warm.", '
                                                '"tags": ["gaming"], "price_aud": 79}')
        self.assertIn("$79.00", text)
        b.add_to_store(1)
        plan = self.proposed[0]
        self.assertEqual((plan["status"], plan["title"], plan["images"][0][-5:]), ("DRAFT", "Lag Lord Hoodie", "m.png"))

    def test_listing_falls_back_when_ai_is_off(self):
        b.set_brand("my brand is Stringman")
        b.design_ideas(ask=lambda p: IDEAS)

        def off(p):
            raise OSError("Ollama off")
        text, item = b.listing(1, ask=off)
        self.assertEqual(item["price"], 79.0)  # hoodie default
        self.assertIn("Lag Lord", text)

    def test_routing(self):
        for t in ["my brand is X", "/brand", "design ideas", "mockup 2", "listing 1", "add design 2 to my store", "launch plan"]:
            self.assertTrue(b.wants(t), t)
        for t in ["add a dog jacket to my store", "sell everything", "how are you"]:
            self.assertFalse(b.wants(t), t)


if __name__ == "__main__":
    unittest.main()
