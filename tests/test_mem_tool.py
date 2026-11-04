"""Tests for Claude's memory tool (tools/mem.py)."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import mem  # noqa: E402


class MemToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(ROOT / "memory", self.tmp / "memory", ignore=shutil.ignore_patterns(".index.db"))
        (self.tmp / "CLAUDE.md").write_text("# notes\n- Shopify keys live on the PC\n")
        self.saved = (mem.ROOT, mem.MEM, mem.STATE, mem.INDEX)
        mem.ROOT, mem.MEM = self.tmp, self.tmp / "memory"
        mem.STATE, mem.INDEX = mem.MEM / "state.json", mem.MEM / ".index.db"

    def tearDown(self):
        mem.ROOT, mem.MEM, mem.STATE, mem.INDEX = self.saved
        shutil.rmtree(self.tmp)

    def run_cmd(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            mem.main(list(args))
        return buf.getvalue()

    def test_add_then_search_finds_it(self):
        self.run_cmd("add", "known_errors", "zebra widget crashes → bad path → use pathlib")
        out = self.run_cmd("search", "zebra", "widget")
        self.assertIn("known_errors.md", out)

    def test_refuses_secrets(self):
        with self.assertRaises(SystemExit):
            mem.main(["add", "solutions", "api_key = abcdef123456"])
        with self.assertRaises(SystemExit):
            mem.main(["checkpoint", "token shpat_0123456789abcdef"])

    def test_checkpoint_updates_state(self):
        self.run_cmd("checkpoint", "built thing", "--next", "test it", "--objective", "ship it")
        s = json.loads(mem.STATE.read_text())
        self.assertEqual((s["checkpoint"], s["next_actions"], s["objective"]),
                         ("built thing", ["test it"], "ship it"))
        self.assertIn("ship it", self.run_cmd("brief"))


if __name__ == "__main__":
    unittest.main()
