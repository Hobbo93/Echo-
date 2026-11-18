import base64
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import echo_live  # noqa: E402
import echo_obs  # noqa: E402


class FakeOBS:
    def __init__(self, folder):
        self.live, self.scene, self.replay = False, "Gameplay", False
        self.scenes = ["Starting Soon", "Gameplay", "Be Right Back"]
        self.folder = folder
        self.log = []

    def __call__(self, *requests):
        out = []
        for kind, data in requests:
            self.log.append(kind)
            if kind == "GetStreamStatus":
                out.append({"outputActive": self.live, "outputDuration": 125000 if self.live else 0,
                            "outputTotalFrames": 1000, "outputSkippedFrames": 3})
            elif kind == "GetSceneList":
                out.append({"currentProgramSceneName": self.scene,
                            "scenes": [{"sceneName": s} for s in reversed(self.scenes)]})
            elif kind == "GetStats":
                out.append({"activeFps": 60, "cpuUsage": 12.5})
            elif kind == "StartStream":
                self.live = True
                out.append({})
            elif kind == "StopStream":
                self.live = False
                out.append({})
            elif kind == "SetCurrentProgramScene":
                self.scene = data["sceneName"]
                out.append({})
            elif kind == "GetReplayBufferStatus":
                out.append({"outputActive": self.replay})
            elif kind == "GetProfileParameter":
                out.append({"parameterValue": "Simple"})
            elif kind in ("SetProfileParameter",):
                out.append({})
            elif kind == "StartReplayBuffer":
                self.replay = True
                out.append({})
            elif kind == "SaveReplayBuffer":
                p = Path(self.folder) / "Replay 2026-11-19.mp4"
                p.write_bytes(b"video")
                import os
                import time
                os.utime(p, (time.time() - 5, time.time() - 5))
                out.append({})
            elif kind == "GetLastReplayBufferReplay":
                out.append({"savedReplayPath": str(Path(self.folder) / "Replay 2026-11-19.mp4")})
            else:
                raise AssertionError(kind)
        return out


class LiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.obs = FakeOBS(root)
        self.patches = [mock.patch.object(echo_obs, "call", self.obs),
                        mock.patch.object(echo_live, "_twitch", return_value=None),
                        mock.patch.object(echo_live.echo_files, "OUTBOX", root / "out"),
                        mock.patch.object(echo_live.echo_files, "SENT", root / "out" / "sent"),
                        mock.patch.object(echo_live.echo_files, "INBOX", root / "in"),
                        mock.patch.object(echo_live.time, "sleep", lambda s: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_casual_chat_never_goes_live(self):
        for text in ("should I go live tonight?", "go live at 8 maybe", "I want to end stream early tomorrow",
                     "clip the video I sent", "/clip https://youtube.com/x", "hello"):
            self.assertIsNone(echo_live.handle(text), text)
        self.assertNotIn("StartStream", self.obs.log)
        self.assertNotIn("StopStream", self.obs.log)

    def test_go_live_and_end(self):
        self.assertIn("Going live", echo_live.handle("go live"))
        self.assertTrue(self.obs.live and self.obs.replay)
        self.assertIn("already live", echo_live.handle("/golive"))
        self.assertIn("LIVE for 2:05", echo_live.handle("/live"))
        self.assertIn("Stream ended after 2:05", echo_live.handle("end stream"))
        self.assertFalse(self.obs.live)

    def test_scenes(self):
        self.assertIn("Be Right Back", echo_live.handle("/scene brb") or echo_live.handle("/scene be right"))
        self.assertEqual(self.obs.scene, "Be Right Back")
        self.assertIn("no OBS scene", echo_live.handle("/scene banana"))

    def test_clip_that_sends_video_to_phone(self):
        reply = echo_live.handle("clip that")
        self.assertIn("last 30 seconds", reply)
        sent = list((Path(self.tmp.name) / "out").glob("Clip *.mp4"))
        self.assertEqual(len(sent), 1)

    def test_obs_off_message(self):
        with mock.patch.object(echo_obs, "call", side_effect=echo_obs.OBSError("OBS isn't open")):
            self.assertIn("OBS isn't open", echo_live.handle("/golive"))


class OBSAuthTest(unittest.TestCase):
    def test_auth_matches_obs_websocket_spec(self):
        pw, salt, challenge = "supersecret", "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI=", \
            "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY="
        secret = base64.b64encode(hashlib.sha256((pw + salt).encode()).digest()).decode()
        want = base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()
        self.assertEqual(echo_obs._auth(pw, salt, challenge), want)

    def test_find_scene(self):
        scenes = ["Starting Soon", "Gameplay", "Be Right Back"]
        self.assertEqual(echo_obs.find_scene("gameplay", scenes), "Gameplay")
        self.assertEqual(echo_obs.find_scene("start", scenes), "Starting Soon")
        self.assertEqual(echo_obs.find_scene("right", scenes), "Be Right Back")
        self.assertIsNone(echo_obs.find_scene("lobby", scenes))


if __name__ == "__main__":
    unittest.main()
