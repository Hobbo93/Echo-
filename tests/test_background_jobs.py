"""Background AI jobs wait while the owner is talking, and never run two at once."""
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_brain  # noqa: E402
import echo_scheduler  # noqa: E402


class BackgroundTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = echo_brain.ACTIVITY
        echo_brain.ACTIVITY = Path(self.tmp.name) / "activity"
        echo_scheduler._background["thread"] = None

    def tearDown(self):
        t = echo_scheduler._background["thread"]
        if t:
            t.join(2)
        echo_brain.ACTIVITY = self.saved
        self.tmp.cleanup()

    def test_activity_window(self):
        self.assertFalse(echo_brain.owner_active())
        echo_brain.mark_active()
        self.assertTrue(echo_brain.owner_active())
        echo_brain.ACTIVITY.write_text(str(time.time() - 600))
        self.assertFalse(echo_brain.owner_active())

    def test_one_job_at_a_time_and_not_while_chatting(self):
        release = threading.Event()
        ran = []
        self.assertTrue(echo_scheduler.run_in_background("slow", lambda: (ran.append(1), release.wait(2))))
        self.assertFalse(echo_scheduler.run_in_background("second", lambda: ran.append(2)))  # first still busy
        release.set()
        echo_scheduler._background["thread"].join(2)
        echo_brain.mark_active()
        self.assertFalse(echo_scheduler.run_in_background("third", lambda: ran.append(3)))  # owner chatting
        self.assertEqual(ran, [1])

    def test_job_errors_dont_crash_the_scheduler(self):
        def boom():
            raise RuntimeError("Ollama is off")
        self.assertTrue(echo_scheduler.run_in_background("boom", boom))
        echo_scheduler._background["thread"].join(2)


if __name__ == "__main__":
    unittest.main()
