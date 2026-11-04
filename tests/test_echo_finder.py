"""Tests for finding videos and sending them to OpusClip (echo_finder.py). YouTube is faked."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_finder as f  # noqa: E402
import echo_opusclip  # noqa: E402


def vr(i, length, title):
    return {"videoRenderer": {"videoId": f"vid{i}", "title": {"runs": [{"text": title}]},
                              "ownerText": {"runs": [{"text": "Some Channel"}]}, "lengthText": {"simpleText": length},
                              "viewCountText": {"simpleText": "1,000 views"}, "publishedTimeText": {"simpleText": "1 day ago"}}}


PAGE = "<script>var ytInitialData = " + json.dumps({"contents": {"x": [
    vr(1, "0:45", "Short one"), vr(2, "12:30", "Long one"), {"videoRenderer": {"videoId": "live1", "title": {"runs": [{"text": "LIVE"}]}}},
    vr(3, "1:02:03", "Very long one")]}}) + ";</script>"


class FinderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (f.STATE, echo_opusclip.handle)
        f.STATE = Path(self.tmp.name) / "found.json"
        self.clipped = []
        echo_opusclip.handle = lambda text: self.clipped.append(text) or "I've sent it to your phone."

    def tearDown(self):
        f.STATE, echo_opusclip.handle = self.saved
        self.tmp.cleanup()

    def test_find_lists_videos_and_skips_live(self):
        reply = f.handle("find videos about funny dogs", fetch=lambda url: PAGE)
        self.assertIn("1. Short one", reply)
        self.assertIn("https://www.youtube.com/watch?v=vid2", reply)
        self.assertNotIn("LIVE", reply)
        self.assertIn("permission", reply)

    def test_long_only(self):
        reply = f.handle("find long videos about funny dogs", fetch=lambda url: PAGE)
        self.assertNotIn("Short one", reply)
        self.assertIn("1. Long one", reply)

    def test_clip_a_found_video_goes_through_opusclip_yes(self):
        f.handle("find videos about dogs", fetch=lambda url: PAGE)
        f.handle("clip 2")
        self.assertEqual(self.clipped, ["/clip https://www.youtube.com/watch?v=vid2"])
        self.assertEqual(f.handle("open 1"), ("open", "https://www.youtube.com/watch?v=vid1"))
        self.assertIn("don't have a video", f.handle("clip 9"))

    def test_pasted_links_from_any_platform(self):
        for link in ["https://www.tiktok.com/@someone/video/123", "https://www.instagram.com/reel/abc/",
                     "https://fb.watch/xyz/", "https://youtu.be/abc123"]:
            self.assertTrue(f.wants(link), link)
            self.assertIn("clip it", f.handle(link))
        f.handle("clip it")
        self.assertEqual(self.clipped[-1], "/clip https://youtu.be/abc123")

    def test_routing(self):
        for t in ["find videos about AFL", "/find dog tricks", "search youtube for minecraft", "clip 2", "open 1", "clip it"]:
            self.assertTrue(f.wants(t), t)
        for t in ["find pet shops on google maps", "clip this https://youtu.be/x", "how are you", "post clip 1 to youtube"]:
            self.assertFalse(f.wants(t), t)


if __name__ == "__main__":
    unittest.main()
