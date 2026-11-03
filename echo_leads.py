# ECHO — EMPLOYEE 4
# Website and Leads Manager: finds local businesses that need a website
#
# Every day (3 PM, or on request) Echo finds 20 NEW southern Adelaide
# businesses from Google Places and gets each one ready for building:
#   - name, address, phone, hours, rating, Google Maps link
#   - whether they already have a website (no website = best lead)
#   - email, found on their own website's home / contact page if published
#   - up to 2 photos from their Google listing, saved to disk
#   - a site brief (brief.md) you can hand straight to Base44
# Everything is saved in %USERPROFILE%\Echo_leads\<date>\ (leads.csv opens in Excel).
#
# Research only: Echo never contacts businesses or publishes anything.
# Needs your own Google Places API key ("google_places_key" in setup).
# Run: py echo_leads.py

import csv
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOCATION = "southern Adelaide, South Australia"
DAILY_RESEARCH_LIMIT = 20
TOP_LEADS = 5
REPORT_HOUR = 15  # 3 PM Adelaide time
PHOTOS_PER_LEAD = 2  # keeps Google photo use near the free monthly allowance

TIMEZONE = ZoneInfo("Australia/Adelaide")
ROOT = Path(__file__).resolve().parent
LEADS_DIR = Path.home() / "Echo_leads"
SEEN_FILE = LEADS_DIR / "seen.json"

SEARCH_TERMS = [
    "barbers in Morphett Vale SA",
    "barbers in Christies Beach SA",
    "barbers in Hallett Cove SA",
    "cleaning services in southern Adelaide",
    "house cleaners in Seaford SA",
    "landscapers in Aldinga SA",
    "landscapers in Happy Valley SA",
    "gardeners in McLaren Vale SA",
    "mobile car detailing in Morphett Vale SA",
    "mobile car detailing in Seaford SA",
    "handyman in Morphett Vale SA",
    "handyman in Aldinga SA",
    "lawn mowing in Hallett Cove SA",
    "dog groomers in southern Adelaide",
    "beauty salons in Seaford SA",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BAD_EMAIL = ("example.", "sentry", "wixpress", "@2x", ".png", ".jpg", ".webp", "domain.com",
             "yourname", "email.com", "godaddy")


def _load_api_key():
    """Env var first, then "google_places_key" in ~/.echo_telegram.json."""
    key = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
    if key:
        return key
    config = Path.home() / ".echo_telegram.json"
    try:
        return str(json.loads(config.read_text(encoding="utf-8-sig"))
                   .get("google_places_key", "")).strip()
    except (OSError, ValueError, AttributeError):
        return ""


API_KEY = _load_api_key()

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
    "places.primaryTypeDisplayName",
    "places.regularOpeningHours.weekdayDescriptions",
    "places.photos",
    "places.reviews",
    "places.editorialSummary",
])


def _http(url, data=None, headers=None, timeout=30):
    req = urllib.request.Request(url, data=data, headers=headers or {},
                                 method="POST" if data else "GET")
    return urllib.request.urlopen(req, timeout=timeout)


def search_businesses(query, limit=20):
    """Search Google Places for real businesses."""
    if not API_KEY:
        return []
    payload = json.dumps({"textQuery": query, "pageSize": max(1, min(int(limit), 20)),
                          "regionCode": "AU"}).encode("utf-8")
    try:
        with _http("https://places.googleapis.com/v1/places:searchText", payload,
                   {"Content-Type": "application/json", "X-Goog-Api-Key": API_KEY,
                    "X-Goog-FieldMask": FIELDS}) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Google Places HTTP {exc.code}: {detail}") from None

    leads = []
    for place in data.get("places", []):
        leads.append({
            "id": place.get("id"),
            "name": place.get("displayName", {}).get("text", "Unknown"),
            "category": place.get("primaryTypeDisplayName", {}).get("text", ""),
            "address": place.get("formattedAddress", ""),
            "website": place.get("websiteUri", ""),
            "phone": place.get("nationalPhoneNumber", ""),
            "email": "",
            "rating": place.get("rating"),
            "reviews": place.get("userRatingCount", 0),
            "status": place.get("businessStatus", ""),
            "maps_url": place.get("googleMapsUri", ""),
            "hours": place.get("regularOpeningHours", {}).get("weekdayDescriptions", []),
            "summary": place.get("editorialSummary", {}).get("text", ""),
            "review_quotes": [
                {"text": r.get("text", {}).get("text", "")[:400],
                 "author": r.get("authorAttribution", {}).get("displayName", ""),
                 "rating": r.get("rating")}
                for r in place.get("reviews", [])[:3] if r.get("text")
            ],
            "_photos": place.get("photos", [])[:PHOTOS_PER_LEAD],
            "photos": [],
            "search": query,
        })
    return leads


def score_lead(lead):
    """Higher score = better website / AI receptionist opportunity (a guess, not a fact)."""
    score, reasons = 0, []
    if not lead["website"]:
        score += 50
        reasons.append("No website")
    elif any(s in lead["website"] for s in ("facebook.com", "instagram.com", "fresha.com", "linktr.ee")):
        score += 40
        reasons.append("Only a social/booking page, no real website")
    reviews = lead.get("reviews") or 0
    if reviews >= 20:
        score += 20
        reasons.append(f"Busy ({reviews} reviews)")
    elif reviews >= 5:
        score += 10
        reasons.append(f"Some reviews ({reviews})")
    if lead["phone"]:
        score += 10
        reasons.append("Takes phone calls (AI receptionist fit)")
    if (lead.get("rating") or 0) >= 4.5:
        score += 10
        reasons.append(f"Highly rated ({lead['rating']})")
    lead["score"], lead["reasons"] = score, reasons
    return lead


# ==========================================
# EMAILS AND PHOTOS
# ==========================================

def find_email(website):
    """Look for a published email on the business's own site (home + contact page)."""
    if not website or any(s in website for s in ("facebook.com", "instagram.com")):
        return ""
    base = website if website.startswith("http") else "https://" + website
    pages = [base]
    root = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(base))
    pages += [root + p for p in ("/contact", "/contact-us", "/contact/")]
    for url in pages:
        try:
            with _http(url, headers={"User-Agent": "Mozilla/5.0 (Echo lead research)"}, timeout=12) as r:
                html = r.read(400_000).decode("utf-8", errors="ignore")
        except Exception:
            continue
        found = [e for e in EMAIL_RE.findall(html.replace("&#64;", "@").replace("[at]", "@"))
                 if not any(b in e.lower() for b in BAD_EMAIL)]
        mailto = [e for e in found if "mailto:" + e in html]
        if mailto or found:
            return (mailto or found)[0]
    return ""


def save_photos(lead, folder):
    """Download up to 2 photos from the Google listing, with credit to who took them."""
    saved = []
    for n, photo in enumerate(lead.pop("_photos", []), 1):
        name = photo.get("name")
        if not name:
            continue
        url = ("https://places.googleapis.com/v1/" + name + "/media?maxWidthPx=1600&key="
               + urllib.parse.quote(API_KEY))
        try:
            with _http(url, timeout=30) as r:
                data = r.read(8_000_000)
        except Exception:
            continue
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"photo{n}.jpg"
        path.write_bytes(data)
        credit = ", ".join(a.get("displayName", "") for a in photo.get("authorAttributions", []))
        saved.append({"file": str(path), "credit": credit})
    lead["photos"] = saved


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "business"


def write_brief(lead, folder):
    """A ready-to-build site brief for Base44 (or any site builder)."""
    folder.mkdir(parents=True, exist_ok=True)
    lines = [f"# Website brief: {lead['name']}", "",
             f"- Business type: {lead['category'] or lead['search']}",
             f"- Address: {lead['address']}",
             f"- Phone: {lead['phone'] or 'not listed'}",
             f"- Email: {lead['email'] or 'not published'}",
             f"- Current website: {lead['website'] or 'none'}",
             f"- Google rating: {lead['rating']} from {lead['reviews']} reviews",
             f"- Google Maps: {lead['maps_url']}", ""]
    if lead["summary"]:
        lines += [f"About: {lead['summary']}", ""]
    if lead["hours"]:
        lines += ["## Opening hours", *("- " + h for h in lead["hours"]), ""]
    if lead["review_quotes"]:
        lines += ["## What customers say (from Google reviews; ask before using on the site)"]
        lines += [f"- \"{q['text']}\" — {q['author']}" for q in lead["review_quotes"]]
        lines.append("")
    if lead["photos"]:
        lines += ["## Photos (from Google; credit the photographer, or use the owner's own photos)"]
        lines += [f"- {Path(p['file']).name} (by {p['credit'] or 'unknown'})" for p in lead["photos"]]
        lines.append("")
    lines += ["## Build prompt for Base44",
              f"Build a modern, mobile-friendly one-page website for {lead['name']}, a "
              f"{(lead['category'] or 'local business').lower()} in {lead['address']}. "
              "Sections: hero with a click-to-call button, services, about, reviews, opening hours, "
              "a map and a contact form. Use the photos provided. Phone: "
              f"{lead['phone'] or 'TBC'}.", ""]
    (folder / "brief.md").write_text("\n".join(lines), encoding="utf-8")


# ==========================================
# DAILY RESEARCH
# ==========================================

def _seen():
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def research_leads(limit=DAILY_RESEARCH_LIMIT):
    """Find `limit` NEW businesses, collect their details and photos, rank them."""
    if not API_KEY:
        raise RuntimeError("Add your Google Places API key first (run setup_echo.bat). No research was done.")
    seen = _seen()
    pool = {}
    for query in SEARCH_TERMS:
        for lead in search_businesses(query, 20):
            key = lead["id"] or lead["name"]
            if lead["status"] in ("CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY") or key in seen:
                continue
            pool.setdefault(key, score_lead(lead))
        if sum(1 for lead in pool.values() if lead["score"] >= 50) >= limit:
            break

    leads = sorted(pool.values(), key=lambda lead: lead["score"], reverse=True)[:limit]
    date = datetime.now(TIMEZONE).date().isoformat()
    day = LEADS_DIR / date
    for lead in leads:
        folder = day / slug(lead["name"])
        lead["email"] = find_email(lead["website"])
        save_photos(lead, folder)
        write_brief(lead, folder)
        lead["folder"] = str(folder)
    for lead in pool.values():
        lead.pop("_photos", None)

    LEADS_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(sorted(seen | {l["id"] or l["name"] for l in leads})), encoding="utf-8")

    result = {
        "date": date,
        "location": LOCATION,
        "researched": len(leads),
        "top_leads": leads[:TOP_LEADS],
        "all_leads": leads,
        "folder": str(day),
        "note": ("From public Google listings. Emails come only from the business's own website. "
                 "Verify before acting; Echo never contacts businesses without your approval."),
    }
    day.mkdir(parents=True, exist_ok=True)
    (day / "leads.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with open(day / "leads.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Business", "Type", "Phone", "Email", "Website", "Address",
                    "Rating", "Reviews", "Why", "Photos", "Brief folder", "Google Maps"])
        for n, l in enumerate(leads, 1):
            w.writerow([n, l["name"], l["category"], l["phone"], l["email"], l["website"] or "none",
                        l["address"], l["rating"], l["reviews"], "; ".join(l["reasons"]),
                        len(l["photos"]), l["folder"], l["maps_url"]])
    (ROOT / f"echo_leads_{date}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def latest():
    """The most recent saved lead list, or None."""
    if not LEADS_DIR.is_dir():
        return None
    days = sorted(p for p in LEADS_DIR.iterdir() if (p / "leads.json").is_file())
    if not days:
        return None
    return json.loads((days[-1] / "leads.json").read_text(encoding="utf-8"))


def summary(result, count=20):
    lines = [f"ECHO LEADS {result['date']}: {result['researched']} businesses ready for building", ""]
    for n, l in enumerate(result["all_leads"][:count], 1):
        lines.append(f"{n}. {l['name']} ({l['category'] or 'business'})")
        bits = [l["phone"] or "no phone", l["email"] or "no email", "no website" if not l["website"] else "has site",
                f"{len(l['photos'])} photos"]
        lines.append("   " + " · ".join(bits))
    lines += ["", "Saved in " + result["folder"] + " (leads.csv opens in Excel; each business has a brief.md).",
              result["note"]]
    return "\n".join(lines)


def looks_like_leads_request(text):
    t = text.lower()
    return "lead" in t or ("business" in t and any(w in t for w in ("find", "local", "research")))


if __name__ == "__main__":
    try:
        result = research_leads()
    except RuntimeError as error:
        raise SystemExit(str(error))
    print(summary(result))
