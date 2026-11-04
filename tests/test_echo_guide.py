"""Tests for guide mode (echo_guide.py), with a fake screen and a fake vision model."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_guide as g  # noqa: E402
import echo_photos  # noqa: E402


class GuideTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        self.tmp.write(b"\x89PNG\r\n\x1a\nfake")
        self.tmp.close()
        self.saved = (echo_photos.has_vision, echo_photos.screenshot, echo_photos.look)
        echo_photos.has_vision = lambda: True
        echo_photos.screenshot = lambda: self.tmp.name
        self.prompts = []

        def look(images, question):
            self.prompts.append(question)
            return "Click the green 'Create app' button in the top-right corner."
        echo_photos.look = look
        g._state.clear()

    def tearDown(self):
        echo_photos.has_vision, echo_photos.screenshot, echo_photos.look = self.saved
        Path(self.tmp.name).unlink()
        g._state.clear()

    def test_start_phrases(self):
        for t in ["/guide connect my shopify store", "guide me through setting up gmail",
                  "walk me through connecting opusclip", "show me how to make a youtube short"]:
            self.assertTrue(g.is_start(t), t)
        for t in ["how are you", "show me my screen", "help me", "next"]:
            self.assertFalse(g.is_start(t), t)

    def test_guide_steps_with_screenshot_and_recipe(self):
        tip, shot = g.start("/guide connect my shopify store")
        self.assertIn("Step 1", tip)
        self.assertIn("Create app", tip)
        self.assertEqual(shot, self.tmp.name)
        self.assertIn("dev.shopify.com/dashboard", self.prompts[0])  # follows Echo's written steps
        self.assertTrue(g.wants_next("next"))
        tip, _ = g.step()
        self.assertIn("Step 2", tip)
        self.assertIn("Create app", self.prompts[1])  # remembers what it already said

    def test_next_and_stop_only_while_guiding(self):
        self.assertFalse(g.wants_next("next"))
        self.assertFalse(g.wants_stop("stop"))
        g.start("/guide connect gmail")
        self.assertTrue(g.wants_stop("stop"))
        self.assertIn("finished after 1 step", g.stop())
        self.assertFalse(g.active())

    def test_needs_vision_model(self):
        echo_photos.has_vision = lambda: False
        tip, shot = g.start("/guide connect my shopify store")
        self.assertIsNone(shot)
        self.assertIn("photo brain", tip)
        self.assertFalse(g.active())

    def test_screen_problem_is_reported(self):
        def broken():
            raise RuntimeError("PC is locked")
        echo_photos.screenshot = broken
        tip, shot = g.start("/guide connect my shopify store")
        self.assertIsNone(shot)
        self.assertIn("PC is locked", tip)


if __name__ == "__main__":
    unittest.main()
