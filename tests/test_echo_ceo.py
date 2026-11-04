"""Tests for the CEO's weekly plan (echo_ceo.py) with a fake AI."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_business  # noqa: E402
import echo_ceo as ceo  # noqa: E402
import echo_growth  # noqa: E402

ANSWER = json.dumps([
    {"employee": "Sales Agent", "task": "Draft 5 website pitches for the newest leads", "why": "pipeline"},
    {"employee": "research agent", "task": "Research what Adelaide cafes pay for websites", "why": "pricing"},
    {"employee": "Nobody Real", "task": "Review this week's numbers", "why": "focus"},
    {"employee": "CEO", "task": "ok", "why": "too short, dropped"},
])


class CeoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (echo_business.DIR, ceo.PLAN, echo_growth.STATE_FILE)
        echo_business.DIR, ceo.PLAN = d, d / "ceo_plan.json"
        echo_growth.STATE_FILE = d / "growth.json"
        echo_business.save("goals", [{"goal": "$3,000 a month from websites", "set": "2026-11-01"}])

    def tearDown(self):
        echo_business.DIR, ceo.PLAN, echo_growth.STATE_FILE = self.saved
        self.tmp.cleanup()

    def test_plan_from_goals(self):
        text = ceo.make_plan(ask=lambda p: ANSWER, today=date(2026, 11, 4))
        self.assertIn("1. Draft 5 website pitches", text)
        tasks = ceo.load()["tasks"]
        self.assertEqual([t["employee"] for t in tasks], ["Sales Agent", "Research Agent", "CEO"])  # unknown → CEO
        self.assertEqual(len(tasks), 3)  # the too-short task was dropped
        self.assertIn("Adelaide cafes", echo_growth.describe_research())  # research handed to the Research Agent

    def test_done_and_progress(self):
        ceo.make_plan(ask=lambda p: ANSWER)
        self.assertIn("2 to go", ceo.mark_done(1))
        self.assertIn("1 of 3", ceo.progress_line())
        self.assertIn("no task 9", ceo.mark_done(9))
        self.assertIn("✅ 1.", ceo.describe())
        self.assertNotIn("1. Draft", ceo.morning_text())  # done tasks drop out of the morning top 3

    def test_new_week_needs_a_plan(self):
        ceo.make_plan(ask=lambda p: ANSWER, today=date(2026, 11, 4))
        self.assertFalse(ceo.needs_new_plan(date(2026, 11, 6)))
        self.assertTrue(ceo.needs_new_plan(date(2026, 11, 10)))

    def test_no_goals_no_plan(self):
        echo_business.save("goals", [])
        self.assertFalse(ceo.needs_new_plan())
        self.assertIn("No goals yet", ceo.make_plan(ask=lambda p: ANSWER))

    def test_bad_ai_answer(self):
        self.assertIn("didn't make sense", ceo.make_plan(ask=lambda p: "I think you should work hard"))

    def test_commands(self):
        ceo.make_plan(ask=lambda p: ANSWER)
        self.assertIn("This week's plan", ceo.handle("/plan"))
        self.assertIn("Task 2 done", ceo.handle("/done 2"))
        self.assertIsNone(ceo.handle("how are you"))


if __name__ == "__main__":
    unittest.main()
