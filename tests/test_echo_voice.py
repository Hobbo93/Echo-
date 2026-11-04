"""Tests for setting up the free natural voice (echo_voice.py). Nothing is really downloaded."""
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_voice as v  # noqa: E402


class VoiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (v.VOICE_DIR, v.VOICE_CONFIG, v.PIPER_MODEL)
        v.VOICE_DIR, v.VOICE_CONFIG, v.PIPER_MODEL = d / "Echo_voice", d / ".echo_voice.json", ""
        self.urls = []

    def tearDown(self):
        v.VOICE_DIR, v.VOICE_CONFIG, v.PIPER_MODEL = self.saved
        self.tmp.cleanup()

    def fake_download(self, url, dest, progress=None):
        self.urls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if url.endswith(".zip"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("piper/piper.exe", "exe")
                z.writestr("piper/espeak-ng-data/x", "data")
            dest.write_bytes(buf.getvalue())
        else:
            dest.write_text("voice")

    def test_setup_downloads_official_files_and_switches(self):
        self.assertIsNone(v.piper())
        msg = v.setup_voice("british", download=self.fake_download)
        self.assertIn("British", msg)
        self.assertTrue(all(u.startswith(("https://github.com/rhasspy/piper/", "https://huggingface.co/rhasspy/"))
                            for u in self.urls))
        exe, model = v.piper()
        self.assertTrue(exe.endswith("piper.exe"))
        self.assertTrue(model.endswith("en_GB-alba-medium.onnx"))
        self.assertEqual(json.loads(v.VOICE_CONFIG.read_text())["voice"], "british")

    def test_switching_voice_reuses_piper(self):
        v.setup_voice("american", download=self.fake_download)
        first = len(self.urls)
        v.setup_voice("british", download=self.fake_download)
        self.assertFalse(any(u.endswith(".zip") for u in self.urls[first:]))  # piper not downloaded twice

    def test_missing_files_mean_no_natural_voice(self):
        v.VOICE_CONFIG.write_text(json.dumps({"piper": "/nope/piper.exe", "model": "/nope/v.onnx"}))
        self.assertIsNone(v.piper())


if __name__ == "__main__":
    unittest.main()
