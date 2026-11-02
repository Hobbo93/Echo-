# ECHO — EMPLOYEE 4
# Adelaide Business Lead Researcher
#
# Research only: finds public business listings and ranks them.
# It never contacts businesses or builds demos.
# Needs a Google Places API key in GOOGLE_PLACES_API_KEY.
# Run: py echo_leads.py

import os
import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOCATION = "Adelaide, South Australia"
DAILY_RESEARCH_LIMIT = 20
TOP_LEADS = 5
REPORT_HOUR = 15  # 3 PM Adelaide time

TIMEZONE = ZoneInfo("Australia/Adelaide")
ROOT = Path(__file__).resolve().parent

SEARCH_TERMS = [
    "barbers in southern Adelaide",
    "cleaning services in southern Adelaide",
    "landscapers in southern Adelaide",
    "mobile car detailers in Adelaide",
    "handyman services in southern Adelaide",
]

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

FIELDS = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.websiteUri",
    "places.nationalPhoneNumber",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.googleMapsUri",
])


def search_businesses(query, limit=10):
    """Search Google Places for real businesses."""

    if not API_KEY:
        return []

    url = (
        "https://places.googleapis.com/v1/"
        "places:searchText"
    )

    payload = json.dumps({
        "textQuery": query,
        "pageSize": max(1, min(int(limit), 20)),
        "regionCode": "AU",
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": FIELDS,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Google Places HTTP {exc.code}: {detail}") from None

    return [
        {
            "id": place.get("id"),
            "name": place.get("displayName", {}).get("text", "Unknown"),
            "address": place.get("formattedAddress", ""),
            "website": place.get("websiteUri", ""),
            "phone": place.get("nationalPhoneNumber", ""),
            "rating": place.get("rating"),
            "reviews": place.get("userRatingCount", 0),
            "status": place.get("businessStatus", ""),
            "maps_url": place.get("googleMapsUri", ""),
            "search": query,
        }
        for place in data.get("places", [])
    ]


def score_lead(lead):
    """Higher score = better website / AI receptionist opportunity.

    These are guesses from public listing data, not verified facts.
    """
    score = 0
    reasons = []

    if not lead["website"]:
        score += 50
        reasons.append("No website listed")

    reviews = lead.get("reviews") or 0
    if reviews >= 20:
        score += 20
        reasons.append(f"Active business ({reviews} reviews)")
    elif reviews >= 5:
        score += 10
        reasons.append(f"Some reviews ({reviews})")

    if lead["phone"]:
        score += 10
        reasons.append("Takes phone calls (AI receptionist fit)")

    if (lead.get("rating") or 0) >= 4.5:
        score += 10
        reasons.append(f"Highly rated ({lead['rating']})")

    lead["score"] = score
    lead["reasons"] = reasons
    return lead


def research_leads():
    """Find up to 20 businesses and rank the best 5."""
    if not API_KEY:
        raise RuntimeError(
            "Set GOOGLE_PLACES_API_KEY first. "
            "No research was done."
        )

    found = {}
    per_search = max(1, DAILY_RESEARCH_LIMIT // len(SEARCH_TERMS))

    for query in SEARCH_TERMS:
        for lead in search_businesses(query, per_search):
            if lead["status"] in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"):
                continue
            found.setdefault(lead["id"] or lead["name"], lead)
        if len(found) >= DAILY_RESEARCH_LIMIT:
            break

    leads = sorted(
        (score_lead(lead) for lead in list(found.values())[:DAILY_RESEARCH_LIMIT]),
        key=lambda lead: lead["score"],
        reverse=True,
    )

    date = datetime.now(TIMEZONE).date().isoformat()
    result = {
        "date": date,
        "location": LOCATION,
        "researched": len(leads),
        "top_leads": leads[:TOP_LEADS],
        "all_leads": leads,
        "note": (
            "Ranked from public Google listings. "
            "Verify before acting. Do not contact "
            "businesses without approval."
        ),
    }

    (ROOT / f"echo_leads_{date}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    result = research_leads()
    print(f"Researched {result['researched']} businesses. Top {TOP_LEADS}:")
    for number, lead in enumerate(result["top_leads"], 1):
        print(f"{number}. {lead['name']} (score {lead['score']}) - "
              + "; ".join(lead["reasons"]))
