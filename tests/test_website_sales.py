"""Tests for the website sales machine: free leads from OpenStreetMap, preview sites, selling."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import echo_business  # noqa: E402
import echo_leads  # noqa: E402
import echo_sales  # noqa: E402

OSM = [
    {"type": "node", "id": 1, "lat": -35.1, "lon": 138.5,
     "tags": {"name": "Blu C Cafe", "amenity": "cafe", "addr:street": "Beach Road", "addr:suburb": "Christies Beach",
              "phone": "+61 8 8382 0000", "opening_hours": "Mo-Su 07:00-15:00"}},
    {"type": "node", "id": 2, "tags": {"name": "Big Chain Burgers", "amenity": "fast_food", "brand": "Big Chain"}},
    {"type": "way", "id": 3, "center": {"lat": -35.1, "lon": 138.5},
     "tags": {"name": "Sparky Sam", "craft": "electrician", "website": "https://facebook.com/sparkysam"}},
    {"type": "node", "id": 4, "tags": {"name": "Has A Site Florist", "shop": "florist", "website": "https://florist.com.au"}},
]


class SalesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (echo_leads.LEADS_DIR, echo_leads.SEEN_FILE, echo_leads.API_KEY, echo_leads.ROOT,
                      echo_business.DIR, echo_leads._overpass, echo_leads.find_email, echo_business.ask_ai)
        echo_leads.LEADS_DIR, echo_leads.SEEN_FILE = d / "leads", d / "leads" / "seen.json"
        echo_leads.API_KEY, echo_leads.ROOT, echo_business.DIR = "", d, d / "biz"
        echo_leads._overpass = lambda q: OSM
        echo_leads.find_email = lambda website: ""
        echo_business.ask_ai = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Ollama off"))

    def tearDown(self):
        (echo_leads.LEADS_DIR, echo_leads.SEEN_FILE, echo_leads.API_KEY, echo_leads.ROOT,
         echo_business.DIR, echo_leads._overpass, echo_leads.find_email, echo_business.ask_ai) = self.saved
        self.tmp.cleanup()

    def test_free_leads_skip_chains_and_rank_no_website_first(self):
        result = echo_leads.research_leads(limit=10)
        names = [l["name"] for l in result["all_leads"]]
        self.assertNotIn("Big Chain Burgers", names)  # chains already have websites
        self.assertEqual(names[0], "Blu C Cafe")  # no website + phone
        self.assertIn("Sparky Sam", names)  # only a Facebook page
        cafe = result["all_leads"][0]
        self.assertEqual(cafe["address"], "Beach Road, Christies Beach, SA")
        self.assertTrue((Path(cafe["folder"]) / "brief.md").exists())
        self.assertIn("OpenStreetMap", result["note"])

    def test_preview_site_is_safe_and_complete(self):
        echo_leads.research_leads(limit=10)
        path, note = echo_sales.build_preview("blu c")
        page = path.read_text()
        self.assertIn("Blu C Cafe", page)
        self.assertIn("tel:+61883820000", page)
        self.assertIn("Barista coffee", page)  # sensible defaults when the AI is off
        self.assertIn("Mo-Su 07:00-15:00", page)
        self.assertIn("Not live yet", page)
        self.assertIn("ready", note)

    def test_preview_escapes_names(self):
        lead = {"name": "<script>alert(1)</script> Cafe", "category": "Cafe", "address": "x, Aldinga, SA"}
        page = echo_sales.preview_html(lead, echo_sales._copy(lead, ask=lambda p: "{}"))
        self.assertNotIn("<script>alert", page)

    def test_sell_and_sell_a_stock(self):
        echo_leads.research_leads(limit=10)
        self.assertTrue(echo_sales.wants("sell Blu C Cafe"))
        self.assertFalse(echo_sales.wants("sell AAPL"))  # a trade, not a website
        echo_sales.set_price("my website price is $499")
        text, path = echo_sales.handle("sell Blu C Cafe")
        self.assertIn("$499", text)
        self.assertTrue(path.exists())

    def test_scoreboard_and_nudge(self):
        echo_leads.research_leads(limit=10)
        echo_business.mark("Blu C", "won")
        board = echo_sales.scoreboard()
        self.assertIn("Said yes: 1", board)
        self.assertIn("Blu C Cafe", board)
        p = echo_business.load("pipeline", {})
        for lead in p.values():
            if lead["name"] == "Sparky Sam":
                lead["stage"], lead["updated"] = "contacted", date(2026, 1, 1).isoformat()
        echo_business.save("pipeline", p)
        self.assertIn("Sparky Sam", echo_sales.morning_nudge())


if __name__ == "__main__":
    unittest.main()
