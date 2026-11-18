import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import echo_files  # noqa: E402


class EchoFilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [mock.patch.object(echo_files, "INBOX", root / "in"),
                        mock.patch.object(echo_files, "OUTBOX", root / "out"),
                        mock.patch.object(echo_files, "SENT", root / "out" / "sent")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_incoming_kinds(self):
        self.assertIsNone(echo_files.incoming({"text": "hi"}))
        self.assertIsNone(echo_files.incoming({"document": {"file_id": "a", "mime_type": "image/png"}}))
        fid, name, size, kind = echo_files.incoming({"video": {"file_id": "v1", "file_size": 10}})
        self.assertEqual((fid, kind, size), ("v1", "video", 10))
        self.assertTrue(name.endswith(".mp4"))
        _, name, _, _ = echo_files.incoming({"document": {"file_id": "d", "file_name": "plan.pdf"}})
        self.assertEqual(name, "plan.pdf")

    def test_save_never_overwrites_and_strips_paths(self):
        a = echo_files.save_incoming(b"1", "../../evil/plan.pdf")
        b = echo_files.save_incoming(b"2", "plan.pdf")
        self.assertEqual(a.parent, echo_files.INBOX)
        self.assertEqual(a.name, "plan.pdf")
        self.assertEqual(b.name, "plan (2).pdf")
        self.assertEqual(echo_files.pick(1).read_bytes() + echo_files.pick(2).read_bytes(), b"21")
        self.assertIn("plan.pdf", echo_files.list_text())

    def test_outbox_waits_for_copy_then_moves_to_sent(self):
        echo_files.ensure_folders()
        f = echo_files.OUTBOX / "clip.mp4"
        f.write_bytes(b"x")
        self.assertEqual(echo_files.ready_to_send(), [])  # still "copying"
        old = time.time() - 10
        os.utime(f, (old, old))
        self.assertEqual(echo_files.ready_to_send(), [f])
        self.assertEqual(echo_files.upload_method(f)[0], "sendVideo")
        moved = echo_files.mark_sent(f)
        self.assertTrue(moved.exists() and not f.exists())
        self.assertEqual(echo_files.ready_to_send(settle=0), [])


if __name__ == "__main__":
    unittest.main()
