"""Tests for Echo's OpusClip connection, using a fake OpusClip (nothing is really posted)."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_opusclip as oc  # noqa: E402

ACCOUNTS = [{"postAccountId": "pa_yt", "platform": "YOUTUBE", "extUserName": "Stringman135"},
            {"postAccountId": "pa_ig", "subAccountId": "sub_ig", "platform": "INSTAGRAM_BUSINESS",
             "extUserName": "brainyburstclips"},
            {"postAccountId": "pa_x", "platform": "TWITTER", "extUserName": "x_acc"}]
CLIPS = [{"id": "P1.CU1", "projectId": "P1", "title": "Dog steals the show", "durationMs": 31000,
          "uriForPreview": "https://cdn.example/1.mp4", "description": "Funny dog", "hashtags": "#dogs"},
         {"id": "P1.CU2", "projectId": "P1", "title": "Second clip", "durationMs": 45000,
          "uriForPreview": "https://cdn.example/2.mp4"}]


class FakeOpus:
    def __init__(self):
        self.calls = []
        self.stage = "CURATE"

    def __call__(self, method, path, body=None, query=None):
        self.calls.append((method, path, body))
        if path == "/social-accounts":
            return {"data": ACCOUNTS}
        if path == "/clip-projects":
            return {"projectId": "P1", "stage": "QUEUED"}
        if path.startswith("/clip-projects/"):
            return {"projectId": "P1", "stage": self.stage}
        if path == "/exportable-clips":
            return CLIPS
        if path == "/social-copy-jobs":
            raise oc.OpusError("copy unavailable")  # falls back to the clip's own text
        return {"data": {"postId": "ok"}}


class OpusClipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (oc.DIR, oc.PENDING, oc.STATE, oc.LOG, oc.CONFIG, oc._api, oc._ask_owner)
        oc.DIR, oc.PENDING, oc.STATE, oc.LOG = d, d / "pending.json", d / "state.json", d / "log.json"
        oc.CONFIG = d / "cfg.json"
        oc.CONFIG.write_text(json.dumps({"opusclip_api_key": "test-key"}))
        self.fake = FakeOpus()
        oc._api = self.fake
        oc._ask_owner = lambda msg: True

    def tearDown(self):
        oc.DIR, oc.PENDING, oc.STATE, oc.LOG, oc.CONFIG, oc._api, oc._ask_owner = self.saved
        self.tmp.cleanup()

    def posts(self):
        return [c for c in self.fake.calls if c[1] in ("/post-tasks", "/publish-schedules")]

    def test_not_connected_message(self):
        oc.CONFIG.write_text("{}")
        self.assertIn("not connected", oc.handle("/clips"))

    def test_clip_waits_for_yes_then_project_is_tracked(self):
        reply = oc.handle("/clip https://youtube.com/watch?v=abc")
        self.assertIn("sent it to your phone", reply)
        self.assertFalse(any(c[1] == "/clip-projects" for c in self.fake.calls))  # nothing before Yes
        self.assertIn("making clips", oc.approve())
        self.assertEqual(self.fake.calls[-1][2], {"videoUrl": "https://youtube.com/watch?v=abc"})

    def test_ready_clips_are_announced_once(self):
        oc.handle("/clip https://youtube.com/watch?v=abc")
        oc.approve()
        sent = []
        self.assertEqual(oc.check_projects(sent.append), 0)  # still curating
        self.fake.stage = "COMPLETE"
        self.assertEqual(oc.check_projects(sent.append), 1)
        self.assertEqual(oc.check_projects(sent.append), 0)
        self.assertIn("1. Dog steals the show (31s)", sent[0])

    def _ready(self):
        oc.handle("/clip https://youtube.com/watch?v=abc")
        oc.approve()
        self.fake.stage = "COMPLETE"
        oc.check_projects()

    def test_post_needs_yes_and_uses_bare_clip_id(self):
        self._ready()
        reply = oc.handle("/post 1 youtube instagram")
        self.assertIn("sent it to your phone", reply)
        self.assertEqual(self.posts(), [])  # nothing posted before Yes
        result = oc.approve()
        self.assertIn("YouTube", result)
        self.assertIn("Instagram", result)
        bodies = [c[2] for c in self.posts()]
        self.assertEqual({b["clipId"] for b in bodies}, {"CU1"})
        self.assertEqual(bodies[1]["subAccountId"], "sub_ig")
        self.assertIn("#dogs", bodies[0]["postDetail"]["custom"]["description"])

    def test_no_means_nothing_posted(self):
        self._ready()
        oc.handle("/post 1 youtube")
        self.assertIn("cancelled", oc.skip())
        self.assertIn("expired", oc.approve())
        self.assertEqual(self.posts(), [])

    def test_schedule_time_and_all_skips_x(self):
        self._ready()
        now = datetime(2026, 11, 4, 12, 0, tzinfo=oc.TZ)
        plan, _ = oc.plan_post("/post 2 all at 6pm", now)
        self.assertEqual(plan["clip"]["clipId"], "CU2")
        self.assertEqual({p["platform"] for p in plan["posts"]}, {"YOUTUBE", "INSTAGRAM_BUSINESS"})
        self.assertEqual(plan["publishAt"], "2026-11-04T07:30:00Z")  # 6 PM Adelaide (ACDT, UTC+10:30)

    def test_bad_requests_explain_what_to_do(self):
        self.assertIn("don't have any clips", oc.handle("/post 1 youtube"))
        self._ready()
        self.assertIn("Which clip", oc.handle("/post 9 youtube"))
        self.assertIn("Where to", oc.handle("/post 1"))

    def test_failed_post_is_reported_honestly(self):
        self._ready()
        oc.handle("/post 1 youtube")
        real = self.fake.__call__

        def failing(method, path, body=None, query=None):
            if path == "/post-tasks":
                raise oc.OpusError("OpusClip error 500")
            return real(method, path, body, query)
        oc._api = failing
        self.assertIn("NOT posted", oc.approve())


if __name__ == "__main__":
    unittest.main()
