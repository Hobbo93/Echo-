"""Messages sent while the PC was off get answered; old Yes/No replies don't approve anything.
Echo adds itself to Windows start-up from the right folder."""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_start  # noqa: E402
import echo_telegram_chat as t  # noqa: E402


def msg(text, minutes_ago=10, chat_id=None, kind="private"):
    return {"message": {"text": text, "date": int(time.time() - minutes_ago * 60),
                        "chat": {"id": int(chat_id or t.CHAT_ID or 42), "type": kind}}}


class CatchUpTest(unittest.TestCase):
    def setUp(self):
        self.saved = (t.CHAT_ID, t.send, t.handle_message)
        t.CHAT_ID = "42"
        self.sent, self.handled = [], []
        t.send = lambda chat, m, kb=None: self.sent.append(m)
        t.handle_message = lambda m: self.handled.append(m["text"])

    def tearDown(self):
        t.CHAT_ID, t.send, t.handle_message = self.saved

    def test_answers_missed_messages_but_not_old_yes(self):
        n = t.catch_up([msg("what's the weather?"), msg("yes"), msg("✅ Place trade"), msg("stop trading")])
        self.assertEqual(n, 2)
        self.assertEqual(self.handled, ["what's the weather?", "stop trading"])
        self.assertIn("I'm back online", self.sent[0])
        self.assertIn("skipped your Yes/No", self.sent[0])

    def test_only_last_24h_only_the_owner_and_max_5(self):
        updates = [msg("too old", minutes_ago=60 * 30), msg("from a stranger", chat_id=7),
                   msg("in a group", kind="group")] + [msg(f"q{i}") for i in range(8)]
        t.catch_up(updates)
        self.assertEqual(self.handled, ["q3", "q4", "q5", "q6", "q7"])
        self.assertIn("to the last 5", self.sent[0])

    def test_nothing_missed_says_nothing(self):
        self.assertEqual(t.catch_up([]), 0)
        self.assertEqual(self.sent, [])


class AutostartTest(unittest.TestCase):
    def test_writes_echo_bat_and_switches_off_old_copies(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "echo_autostart.bat").write_text('cd /d "C:\\Users\\x\\Downloads\\Echo_fresh_test"\npy echo_start.py\n')
            (d / "other_app.bat").write_text("start something_else.exe\n")
            note = echo_start.install_autostart(d)
            self.assertIn("switched off", note)
            self.assertTrue((d / "echo_autostart.bat.old").exists())
            self.assertTrue((d / "other_app.bat").exists())  # other programs are left alone
            text = (d / "Echo.bat").read_bytes().decode()
            self.assertIn(f'cd /d "{echo_start.ROOT}"', text)
            self.assertIn("\r\n", text)  # Windows line endings
            self.assertEqual(echo_start.install_autostart(d), "")  # already right: no change


if __name__ == "__main__":
    unittest.main()
