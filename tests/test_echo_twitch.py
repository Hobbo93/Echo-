import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import echo_twitch  # noqa: E402
import echo_twitch_bot  # noqa: E402

CFG = {"twitch_client_id": "a" * 30, "twitch_client_secret": "b" * 30, "twitch_channel": "CoolStreamer"}


class FakeTwitch:
    """Answers Twitch's API like the real thing, from a few settable values."""

    def __init__(self):
        self.live = None
        self.calls = []

    def __call__(self, url, data=None, headers=None, method=None):
        self.calls.append(url)
        if url.endswith("/oauth2/token"):
            return {"access_token": "apptoken", "expires_in": 3600}
        if "/users" in url:
            return {"data": [{"id": "42", "login": "coolstreamer", "display_name": "CoolStreamer"}]}
        if "/streams" in url:
            return {"data": [self.live] if self.live else []}
        if "/clips" in url:
            return {"data": [{"title": "Big win", "view_count": 50, "url": "https://clips.twitch.tv/a"},
                             {"title": "Funny fail", "view_count": 90, "url": "https://clips.twitch.tv/b"}]}
        if "/videos" in url:
            return {"data": [{"url": "https://www.twitch.tv/videos/1", "title": "VOD"}]}
        if "/channels/followers" in url:
            return {"total": 1234}
        raise AssertionError("unexpected " + url)


class TwitchTest(unittest.TestCase):
    def setUp(self):
        self.store = {}
        self.fake = FakeTwitch()
        self.sent = []
        echo_twitch._app_token.update(token="", until=0)
        echo_twitch._last_check[0] = 0
        self.patches = [
            mock.patch.object(echo_twitch.echo_connect, "_cfg", return_value=dict(CFG)),
            mock.patch.object(echo_twitch.echo_business, "load", side_effect=lambda n, d: self.store.get(n, d)),
            mock.patch.object(echo_twitch.echo_business, "save", side_effect=lambda n, v: self.store.__setitem__(n, v)),
            mock.patch.object(echo_twitch.echo_business, "ask_ai", return_value="1. Hook: ..."),
            mock.patch.object(echo_twitch, "_request", self.fake),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_not_connected_points_to_connect(self):
        with mock.patch.object(echo_twitch.echo_connect, "_cfg", return_value={}):
            self.assertIn("/connect 6", echo_twitch.handle("/twitch", self.sent.append))
            self.assertIsNone(echo_twitch.handle("hello", self.sent.append))

    def test_live_then_offline_alerts_and_clips(self):
        self.fake.live = {"title": "Ranked grind", "game_name": "Valorant", "viewer_count": 12,
                          "started_at": "2026-11-19T08:00:00Z"}
        echo_twitch.tick(self.sent.append, force=True)
        self.assertIn("You're live", self.sent[0])
        self.assertIn("twitch.tv/coolstreamer", self.sent[0])
        self.fake.live["viewer_count"] = 40
        echo_twitch.tick(self.sent.append, force=True)
        self.assertEqual(len(self.sent), 1)  # no repeat alert while live
        self.fake.live = None
        with mock.patch("echo_opusclip.is_configured", return_value=False):
            echo_twitch.tick(self.sent.append, force=True)
        self.assertIn("Peak viewers: 40", self.sent[1])
        clips = self.sent[2]
        self.assertLess(clips.index("Funny fail"), clips.index("Big win"))  # most viewed first
        self.assertIn("twitch.tv/videos/1", clips)
        self.assertIn("/connect 1", clips)  # offers OpusClip without spending anything
        self.assertEqual(len(self.store["twitch"]["history"]), 1)

    def test_stats_and_follower_change(self):
        first = echo_twitch.stats()
        self.assertIn("Followers: 1,234", first)
        self.store["twitch"]["last_followers"] = 1200
        self.assertIn("(+34 since last report)", echo_twitch.stats())

    def test_weekly_report_once_on_monday_morning(self):
        monday = datetime(2026, 11, 23, 9, 5)
        due, week = echo_twitch.weekly_due({}, monday)
        self.assertTrue(due)
        self.assertFalse(echo_twitch.weekly_due({"last_twitch_report": week}, monday)[0])
        self.assertFalse(echo_twitch.weekly_due({}, datetime(2026, 11, 23, 8, 0))[0])
        self.assertFalse(echo_twitch.weekly_due({}, datetime(2026, 11, 24, 10, 0))[0])

    def test_bot_off_and_clips_commands(self):
        self.assertIn("off", echo_twitch.handle("/twitch bot off", self.sent.append))
        self.assertFalse(echo_twitch.bot_enabled())
        self.assertIn("Funny fail", echo_twitch.handle("/twitch clips", self.sent.append))


class TwitchBotTest(unittest.TestCase):
    def test_parse_and_triggers(self):
        line = "@badge-info=;color= :viewer1!viewer1@viewer1.tmi.twitch.tv PRIVMSG #coolstreamer :!echo what game is this?"
        viewer, text = echo_twitch_bot.parse(line)
        self.assertEqual(viewer, "viewer1")
        self.assertEqual(echo_twitch_bot.wants_reply(text, "echobot"), "what game is this?")
        self.assertEqual(echo_twitch_bot.wants_reply("hey @EchoBot you there", "echobot"), "hey  you there")
        self.assertIsNone(echo_twitch_bot.wants_reply("just chatting", "echobot"))
        self.assertIsNone(echo_twitch_bot.parse("PING :tmi.twitch.tv"))

    def test_limiter(self):
        lim = echo_twitch_bot.Limiter()
        self.assertTrue(lim.ok("a", now=1000))
        self.assertFalse(lim.ok("A", now=1010))       # same viewer within 30 s
        self.assertTrue(lim.ok("a", now=1031))
        for i in range(echo_twitch_bot.MAX_PER_MINUTE):
            lim.ok(f"v{i}", now=1040)
        self.assertFalse(lim.ok("new", now=1041))     # overall cap per minute

    def test_reply_is_cleaned(self):
        with mock.patch.object(echo_twitch_bot.echo_business, "ask_ai",
                               return_value="Check https://spam.example   it's   great"):
            self.assertEqual(echo_twitch_bot.answer("v", "hi"), "Check it's great")


if __name__ == "__main__":
    unittest.main()
