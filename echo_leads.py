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
PHOTOS_PER_LEAD = 1  # 20 leads a day x 1 photo stays inside Google's free 1,000 photos a month

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


# ==========================================
# FREE SOURCE: OpenStreetMap (no key, no card) - used when there's no Google key
# ==========================================

OVERPASS = ["https://overpass.private.coffee/api/interpreter", "https://overpass-api.de/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
# Southern Adelaide, in small boxes (south, west, north, east) so each search stays quick.
AREAS = {
    "Christies Beach / Morphett Vale": (-35.20, 138.46, -35.08, 138.56),
    "Reynella / Hallett Cove": (-35.10, 138.48, -35.02, 138.58),
    "Noarlunga / Seaford": (-35.24, 138.46, -35.15, 138.55),
    "Aldinga / McLaren Vale": (-35.30, 138.45, -35.18, 138.56),
    "Happy Valley / Aberfoyle Park": (-35.10, 138.55, -35.02, 138.64),
}
OSM_KINDS = ('nwr["shop"~"^(hairdresser|beauty|barber|bakery|butcher|florist|car_repair|pet|pet_grooming|tyres|clothes|'
             'massage|tattoo|bicycle|hardware|gift)$"]["name"]{box};'
             'nwr["amenity"~"^(cafe|restaurant|fast_food|dentist|veterinary|car_wash|childcare)$"]["name"]{box};'
             'nwr["craft"~"^(electrician|plumber|carpenter|builder|painter|gardener|roofer|tiler)$"]["name"]{box};')


def _osm_query(box):
    b = "(%s,%s,%s,%s)" % box
    return "[out:json][timeout:50];(" + OSM_KINDS.replace("{box}", b) + ");out center tags 300;"


def _overpass(query):
    last = None
    for url in OVERPASS:
        try:
            with _http(url, urllib.parse.urlencode({"data": query}).encode(),
                       {"User-Agent": "EchoPersonalAssistant/1.0"}, timeout=90) as r:
                return json.load(r).get("elements", [])
        except (OSError, ValueError) as exc:  # busy server: try the next one
            last = exc
    raise RuntimeError(f"OpenStreetMap search is busy right now ({last}). Try /findleads again later.")


def _osm_lead(el, area):
    t = el.get("tags", {})
    kind = t.get("shop") or t.get("amenity") or t.get("craft") or "business"
    street = " ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street")) if x)
    suburb = t.get("addr:suburb") or t.get("addr:city") or area.split(" / ")[0]
    website = t.get("website") or t.get("contact:website") or t.get("url") or ""
    social = t.get("contact:facebook") or t.get("facebook") or t.get("contact:instagram") or ""
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lon = el.get("lon") or el.get("center", {}).get("lon")
    name = t.get("name", "Unknown")
    maps = (f"https://www.google.com/maps/search/{urllib.parse.quote_plus(name + ' ' + suburb + ' SA')}")
    return {
        "id": f"osm:{el.get('type')}/{el.get('id')}",
        "name": name,
        "category": kind.replace("_", " ").title(),
        "address": ", ".join(x for x in (street, suburb, "SA") if x),
        "website": website or social,
        "phone": t.get("phone") or t.get("contact:phone") or "",
        "email": t.get("email") or t.get("contact:email") or "",
        "rating": None,
        "reviews": 0,
        "status": "",
        "maps_url": maps,
        "osm_url": f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
        "hours": [t["opening_hours"]] if t.get("opening_hours") else [],
        "summary": "",
        "review_quotes": [],
        "_photos": [],
        "photos": [],
        "search": f"{kind} in {area}",
        "lat": lat, "lon": lon,
    }


def search_osm(seen, limit=DAILY_RESEARCH_LIMIT, fetch=None):
    """Free lead search: independent local businesses from OpenStreetMap, rotating through areas."""
    fetch = fetch or _overpass
    pool = {}
    start = int(datetime.now(TIMEZONE).strftime("%j")) % len(AREAS)  # a different area first each day
    names = list(AREAS)
    for area in names[start:] + names[:start]:
        for el in fetch(_osm_query(AREAS[area])):
            t = el.get("tags", {})
            if any(k.startswith("brand") for k in t):  # chains already have websites
                continue
            lead = _osm_lead(el, area)
            if lead["id"] in seen or lead["name"].lower() in {p["name"].lower() for p in pool.values()}:
                continue
            pool[lead["id"]] = score_lead(lead)
        if sum(1 for lead in pool.values() if lead["score"] >= 50) >= limit:
            break
    return list(pool.values())


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
             (f"- Google rating: {lead['rating']} from {lead['reviews']} reviews" if lead.get("rating")
              else "- Google rating: check the map link"),
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
    seen = _seen()
    pool = {}
    if not API_KEY:  # free route: OpenStreetMap
        pool = {lead["id"]: lead for lead in search_osm(seen, limit)}
    for query in (SEARCH_TERMS if API_KEY else []):
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
        "note": (("From public Google listings. " if API_KEY else
                  "From OpenStreetMap (free). Phone numbers are often missing: tap the map link to look them up. ")
                 + "Emails come only from the business's own website. "
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
