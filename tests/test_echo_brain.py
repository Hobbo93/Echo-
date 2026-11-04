"""Tests for choosing and switching Echo's AI model (echo_brain.py). Nothing is downloaded."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_brain as b  # noqa: E402

GB = 2**30


class BrainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (b.SETTINGS, b.specs, b.pull, b.speed_test, os.environ.pop("ECHO_MODEL", None),
                      os.environ.pop("ECHO_VISION_MODEL", None))
        b.SETTINGS = Path(self.tmp.name) / "brain.json"
        self.pulled = []
        b.pull = lambda name, progress=None: self.pulled.append(name)
        b.speed_test = lambda name: 4.0

    def tearDown(self):
        b.SETTINGS, b.specs, b.pull, b.speed_test, em, ev = self.saved
        if em:
            os.environ["ECHO_MODEL"] = em
        if ev:
            os.environ["ECHO_VISION_MODEL"] = ev
        self.tmp.cleanup()

    def test_defaults_and_old_employee_setting(self):
        self.assertEqual(b.model(), "llama3.2")
        self.assertEqual(b.vision_model(), "gemma3:4b")
        self.assertEqual(b.resolve("llama3.2"), "llama3.2")
        self.assertEqual(b.resolve("mistral"), "mistral")

    def test_pick_gpu_ignores_integrated_graphics(self):
        s = b.pick_gpu(31.8, [{"name": "Intel(R) UHD Graphics 770", "vram": 2 * GB},
                              {"name": "NVIDIA GeForce RTX 3060", "vram": 12 * GB}])
        self.assertEqual((s["gpu"], s["vram_gb"]), ("NVIDIA GeForce RTX 3060", 12.0))
        s = b.pick_gpu(16, [{"name": "AMD Radeon(TM) Graphics", "vram": 0.5 * GB}])
        self.assertEqual(s["vram_gb"], 0.0)

    def test_recommendations(self):
        rec = lambda ram, vram: b.recommend({"ram_gb": ram, "gpu": "GPU" if vram else "", "vram_gb": vram})
        self.assertEqual(rec(32, 12)[0], "large")
        self.assertEqual(rec(16, 8)[0], "medium")
        tier, why, phone_ok = rec(16, 0)
        self.assertEqual((tier, phone_ok), ("medium", False))
        self.assertIn("slower", why)
        self.assertEqual(rec(8, 0)[0], "small")

    def test_upgrade_switches_everything_and_back(self):
        b.specs = lambda: {"ram_gb": 32, "gpu": "NVIDIA GeForce RTX 3060", "vram_gb": 12.0}
        said = []
        b.upgrade(said.append)
        self.assertEqual(self.pulled, ["gemma3:12b"])  # one model does chat and photos
        self.assertEqual((b.model(), b.vision_model(), b.fast_model()), ("gemma3:12b",) * 3)
        self.assertEqual(b.resolve("llama3.2"), "gemma3:12b")  # employees follow the brain
        self.assertIn("now thinks with gemma3:12b", said[-1])
        b.downgrade()
        self.assertEqual(b.model(), "llama3.2")

    def test_cpu_only_keeps_phone_fast(self):
        b.specs = lambda: {"ram_gb": 16, "gpu": "", "vram_gb": 0.0}
        said = []
        b.upgrade(said.append)
        self.assertEqual((b.model(), b.fast_model()), ("qwen2.5:7b", "llama3.2"))
        self.assertIn("Phone calls stay on llama3.2", said[-1])

    def test_failed_download_keeps_old_brain(self):
        b.specs = lambda: {"ram_gb": 16, "gpu": "NVIDIA RTX 4060", "vram_gb": 8.0}

        def broken(name, progress=None):
            raise RuntimeError("Cannot reach Ollama")
        b.pull = broken
        said = []
        b.upgrade(said.append)
        self.assertEqual(b.model(), "llama3.2")
        self.assertIn("didn't finish", said[-1])

    def test_env_variable_still_wins(self):
        os.environ["ECHO_MODEL"] = "mistral"
        try:
            self.assertEqual(b.model(), "mistral")
        finally:
            del os.environ["ECHO_MODEL"]


if __name__ == "__main__":
    unittest.main()
