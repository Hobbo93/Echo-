"""Tests for nightly backups (echo_backup.py): what's saved, what's never saved, keeping 14."""
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_backup as bk  # noqa: E402


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.home, self.root, self.dest = d / "home", d / "echo", d / "OneDrive" / "Echo_backups"
        for p in (self.home, self.root):
            p.mkdir()
        self.saved = (bk.ROOT, bk.HOME, bk.STATE, bk.FILES, bk.FOLDERS)
        bk.ROOT, bk.HOME, bk.STATE = self.root, self.home, self.home / ".echo_backup.json"
        bk.FILES = [(self.root / "echo_memory.db", "echo_folder/echo_memory.db"),
                    (self.home / ".echo_growth.json", "user_folder/.echo_growth.json"),
                    (self.home / ".echo_telegram.json", "user_folder/.echo_telegram.json")]
        bk.FOLDERS = [(self.home / "Echo_business", "user_folder/Echo_business")]
        with sqlite3.connect(self.root / "echo_memory.db") as db:
            db.execute("CREATE TABLE memories (content TEXT)")
            db.execute("INSERT INTO memories VALUES ('my dog is Max')")
        (self.home / ".echo_growth.json").write_text("{}")
        (self.home / ".echo_telegram.json").write_text('{"bot_token": "secret"}')
        (self.home / "Echo_business").mkdir()
        (self.home / "Echo_business" / "money.json").write_text("[]")

    def tearDown(self):
        bk.ROOT, bk.HOME, bk.STATE, bk.FILES, bk.FOLDERS = self.saved
        self.tmp.cleanup()

    def test_backup_contents_and_no_keys(self):
        path, text = bk.backup_now(self.dest)
        names = zipfile.ZipFile(path).namelist()
        self.assertIn("echo_folder/echo_memory.db", names)
        self.assertIn("user_folder/Echo_business/money.json", names)
        self.assertIn("README.txt", names)
        self.assertNotIn("user_folder/.echo_telegram.json", names)  # keys never backed up
        self.assertIn("Backed up", text)
        with tempfile.TemporaryDirectory() as out:
            zipfile.ZipFile(path).extract("echo_folder/echo_memory.db", out)
            with sqlite3.connect(Path(out) / "echo_folder/echo_memory.db") as db:
                self.assertEqual(db.execute("SELECT content FROM memories").fetchone()[0], "my dog is Max")

    def test_keeps_last_14(self):
        self.dest.mkdir(parents=True)
        for i in range(20):
            (self.dest / f"echo_backup_2026-01-{i + 1:02d}_0100.zip").write_text("old")
        bk.backup_now(self.dest)
        self.assertEqual(len(list(self.dest.glob("echo_backup_*.zip"))), 14)

    def test_due_once_a_day(self):
        self.assertTrue(bk.due())
        bk.backup_now(self.dest)
        now = datetime.now()
        self.assertFalse(bk.due(now))
        self.assertTrue(bk.due(now + timedelta(days=1, hours=1)))

    def test_prefers_cloud_folder(self):
        (self.home / "OneDrive").mkdir()
        import os
        saved = os.environ.pop("OneDrive", None), os.environ.pop("OneDriveConsumer", None)
        try:
            self.assertEqual(bk.destination(), self.home / "OneDrive" / "Echo_backups")
        finally:
            for k, v in zip(("OneDrive", "OneDriveConsumer"), saved):
                if v:
                    os.environ[k] = v
        bk.STATE.write_text(json.dumps({"folder": str(self.dest)}))
        self.assertEqual(bk.destination(), self.dest)


if __name__ == "__main__":
    unittest.main()
