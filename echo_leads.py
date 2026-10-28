# ECHO — EMPLOYEE 4
# Adelaide Business Lead Researcher

import os
import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

LOCATION = "Adelaide, South Australia"
DAILY_RESEARCH_LIMIT = 20
TOP_LEADS = 5
REPORT_HOUR = 15  # 3 PM Adelaide time

TIMEZONE = ZoneInfo("Australia/Adelaide")

SEARCH_TERMS = [
    "barbers in southern Adelaide",
    "cleaning services in southern Adelaide",
    "landscapers in southern Adelaide",
    "mobile car detailers in Adelaide",
    "handyman services in southern Adelaide",
]

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")


def search_businesses(query):
    """Search Google Places for real businesses."""

    if not API_KEY:
        return []

    url = (
        "https://places.googleapis.com/v1/"
        "places:searchText"
    )

    payload = json.dumps({
        "textQuery
