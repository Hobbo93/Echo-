"""Tests for Echo's simple PC actions (echo_computer.py). Nothing is really opened."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_computer as pc  # noqa: E402


class ComputerTest(unittest.TestCase):
    def test_searches(self):
        cases = {
            "search youtube for dog grooming tips": "youtube.com/results?search_query=dog+grooming+tips",
            "hey echo, go on youtube and search dog tricks": "youtube.com/results?search_query=dog+tricks",
            "can you look up waterproof dog jackets on amazon": "amazon.com.au/s?k=waterproof+dog+jackets",
            "google cheap dog beds adelaide": "google.com/search?q=cheap+dog+beds+adelaide",
            "find pet shops on google maps for me": "google.com/maps/search/pet+shops",
        }
        for text, want in cases.items():
            p = pc.plan(text)
            self.assertIsNotNone(p, text)
            self.assertIn(want, p["url"], text)

    def test_open_sites(self):
        self.assertEqual(pc.plan("open my shopify admin")["url"], "https://thedogden-2.myshopify.com/admin")
        self.assertEqual(pc.plan("open youtube studio")["url"], "https://studio.youtube.com")
        self.assertEqual(pc.plan("please open gmail")["url"], "https://mail.google.com")
        self.assertEqual(pc.plan("open https://example.com/x")["url"], "https://example.com/x")

    def test_screen(self):
        for t in ["/screen", "show me my screen", "what's on my pc", "screenshot"]:
            self.assertEqual(pc.plan(t)["action"], "screen", t)

    def test_not_pc_requests(self):
        for t in ["find a way to connect to shopify", "show my products", "open a new store discount",
                  "how are you", "post clip 1 to youtube", "search for meaning in life"]:
            self.assertIsNone(pc.plan(t), t)

    def test_do_opens_and_sends_screenshot(self):
        opened = []
        real = (pc.open_url, pc.screenshot)
        pc.open_url = opened.append
        pc.screenshot = lambda: "shot.png"
        try:
            msg, shot = pc.do(pc.plan("search youtube for dog tricks"), wait=0)
        finally:
            pc.open_url, pc.screenshot = real
        self.assertIn("youtube.com", opened[0])
        self.assertEqual(shot, "shot.png")
        self.assertIn("Opened", msg)

    def test_only_web_links(self):
        with self.assertRaises(ValueError):
            pc.open_url("file:///C:/Windows/System32/cmd.exe")

    def test_screenshot_failure_is_reported(self):
        real = pc.screenshot

        def broken():
            raise RuntimeError("no screen")
        pc.screenshot = broken
        try:
            msg, shot = pc.do({"action": "screen", "label": "your screen"})
        finally:
            pc.screenshot = real
        self.assertIsNone(shot)
        self.assertIn("No screenshot", msg)


if __name__ == "__main__":
    unittest.main()
