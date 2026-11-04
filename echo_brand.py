"""Brand Studio: helps build your clothing brand, for free.

    my brand is Stringman, streetwear for Aussie gamers     set the brand (name, style, who it's for)
    /brand                     your brand and what Brand Studio can do
    design ideas               5 fresh design ideas (tees, hoodies, caps) that fit the brand
    mockup 2                   a free picture of design idea 2
    listing 2                  product title, description, tags and a suggested price
    add design 2 to my store   a DRAFT product in Shopify with the picture (asks your Yes first)
    launch plan                a 4-week launch plan using free channels (your YouTube, IG, TikTok)

Print-on-demand (Printify or Printful, both free to start) prints and posts each order, so you hold
no stock: see BRAND_SETUP.md. Echo never publishes, posts or spends money without your Yes.
Pictures come from Pollinations (free); ideas come from your local AI and Echo's research notes.
"""
import json
import re
from datetime import date

import echo_business
import echo_log

BRAND = "brand"          # echo_business store: {"name", "style", "audience", "ideas": [...]}
RESEARCH_TOPICS = ["streetwear trends Australia", "print on demand best selling designs",
                   "TikTok clothing brand launch ideas"]


def profile():
    return echo_business.load(BRAND, {})


def _save(p):
    echo_business.save(BRAND, p)


def set_brand(text):
    m = re.match(r"^\s*my (?:clothing )?brand is\s+(.+)$", text, re.I)
    if not m:
        return None
    raw = m.group(1).strip().rstrip(".")
    name, _, style = raw.partition(",")
    p = profile()
    p.update(name=name.strip()[:60], style=style.strip()[:200] or p.get("style", ""), set=date.today().isoformat())
    _save(p)
    try:
        import echo_growth
        for topic in RESEARCH_TOPICS:
            echo_growth.queue(topic, why="Brand Studio")
    except Exception as exc:
        echo_log.error("brand research", exc)
    echo_business.record("Brand Studio", "Brand set: " + p["name"])
    return (f"👕 Brand Studio is working on {p['name']}" + (f" ({p['style']})" if p.get("style") else "") +
            ". I've added clothing trends to my research list. Next: say 'design ideas'.")


def _research_notes():
    try:
        import echo_memory
        rows = echo_memory.relevant("streetwear clothing fashion print demand design trend", 4, ["research"])
        return "\n".join(r["content"][:400] for r in rows)
    except Exception:
        return ""


def _parse_ideas(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    ideas = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not str(it.get("name", "")).strip():
            continue
        ideas.append({k: " ".join(str(it.get(k, "")).split())[:200]
                      for k in ("name", "product", "design", "colours", "why")})
    return ideas[:5]


def design_ideas(ask=None):
    p = profile()
    if not p.get("name"):
        return "First tell me about the brand: 'my brand is <name>, <style and who it's for>'."
    notes = _research_notes()
    prompt = (f"You design clothing for a small new brand called {p['name']} ({p.get('style') or 'streetwear'}). "
              "Suggest 5 original designs that would sell well as print-on-demand (tees, hoodies, caps). "
              "Original artwork and wording only: no logos, characters or slogans owned by others. "
              + (f"Recent trend notes (use if useful):\n{notes}\n" if notes else "") +
              'Answer with ONLY a JSON list: [{"name": "...", "product": "hoodie", "design": "what the print shows '
              'and says", "colours": "...", "why": "why it would sell"}]')
    try:
        ideas = _parse_ideas((ask or (lambda q: echo_business.ask_ai(q, timeout=240)))(prompt))
    except Exception as exc:
        echo_log.error("brand ideas", exc)
        return f"I couldn't come up with ideas right now ({str(exc)[:100]}). Is Ollama running?"
    if not ideas:
        return "My ideas came out jumbled this time. Say 'design ideas' again."
    p["ideas"] = ideas
    _save(p)
    lines = [f"👕 5 design ideas for {p['name']}:"]
    for i, d in enumerate(ideas, 1):
        lines.append(f"\n{i}. {d['name']} ({d['product']})\n   {d['design']}\n   Colours: {d['colours']}\n   Why: {d['why']}")
    lines.append("\nSay 'mockup 2' for a picture, 'listing 2' for the shop text, or 'add design 2 to my store'.")
    return "\n".join(lines)


def _idea(n):
    ideas = profile().get("ideas", [])
    if not ideas:
        return None, "No design ideas yet. Say 'design ideas' first."
    if not 1 <= n <= len(ideas):
        return None, f"Pick a number from 1 to {len(ideas)}."
    return ideas[n - 1], ""


def mockup(n, make=None):
    """A free picture of design idea n. Returns (message, image path or None)."""
    idea, err = _idea(n)
    if not idea:
        return err, None
    prompt = (f"Product photo of a {idea['product']} on a plain studio background, {idea['colours']}, "
              f"with an original printed design: {idea['design']}. Clean, realistic clothing mockup.")
    try:
        import echo_photos
        path = (make or echo_photos.make_picture)(prompt)
    except Exception as exc:
        return f"The picture didn't come through ({str(exc)[:120]}). Try again in a minute.", None
    idea["mockup"] = str(path)
    p = profile()
    p["ideas"][n - 1] = idea
    _save(p)
    return (f"🖼️ Mock-up of '{idea['name']}'. AI pictures are rough: the final print file should be made "
            "in Canva or Printify's design tool (both free)."), path


def listing(n, ask=None):
    idea, err = _idea(n)
    if not idea:
        return err, None
    p = profile()
    prompt = (f"Write a Shopify product listing for '{idea['name']}', a {idea['product']} from the brand "
              f"{p['name']} ({p.get('style', '')}). Design: {idea['design']}. Answer with ONLY JSON: "
              '{"title": "...", "description": "2-3 short paragraphs", "tags": ["..."], "price_aud": number}. '
              "Price it for print-on-demand in Australia (tees about 39-49, hoodies about 69-89).")
    try:
        text = (ask or (lambda q: echo_business.ask_ai(q, timeout=180)))(prompt)
        m = re.search(r"\{.*\}", text or "", re.S)
        got = json.loads(m.group(0)) if m else {}
    except Exception as exc:
        echo_log.error("brand listing", exc)
        got = {}
    default_price = 79 if "hood" in idea["product"].lower() else 45
    item = {"title": str(got.get("title") or idea["name"])[:120],
            "description": str(got.get("description") or idea["design"])[:2000],
            "tags": [str(t)[:30] for t in (got.get("tags") or [p["name"], idea["product"]])][:10],
            "price": float(got.get("price_aud") or default_price)}
    idea["listing"] = item
    p["ideas"][n - 1] = idea
    _save(p)
    return (f"🏷️ {item['title']}: ${item['price']:.2f}\n\n{item['description']}\n\nTags: {', '.join(item['tags'])}"
            "\n\nSay 'add design %d to my store' to put it in Shopify as a draft (I'll ask your Yes first)." % n), item


def add_to_store(n):
    idea, err = _idea(n)
    if not idea:
        return err
    import echo_shopify
    if not echo_shopify.is_configured():
        return echo_shopify.NOT_CONNECTED
    item = idea.get("listing") or listing(n)[1]
    plan = {"action": "create_product", "title": item["title"], "price": item["price"],
            "description": item["description"], "tags": item["tags"], "product_type": idea["product"].title(),
            "vendor": profile().get("name", ""), "status": "DRAFT"}
    if idea.get("mockup"):
        plan["images"] = [idea["mockup"]]
    return echo_shopify.propose(plan)


def launch_plan(ask=None):
    p = profile()
    if not p.get("name"):
        return "First tell me about the brand: 'my brand is <name>, <style and who it's for>'."
    prompt = (f"Write a 4-week launch plan for a new print-on-demand clothing brand called {p['name']} "
              f"({p.get('style', '')}) run by one person in Adelaide with no ad budget. They already have a "
              "YouTube channel, an Instagram and a TikTok for short clips, and a Shopify store. Use only free "
              "tactics. Week by week, 3-4 concrete actions each. Be realistic: no promises of sales.")
    try:
        plan = (ask or (lambda q: echo_business.ask_ai(q, timeout=240)))(prompt)
    except Exception as exc:
        return f"I couldn't write the plan right now ({str(exc)[:100]})."
    p["launch_plan"] = plan
    _save(p)
    return f"🚀 4-week launch plan for {p['name']}:\n\n{plan}"


def describe():
    p = profile()
    if not p.get("name"):
        return ("👕 Brand Studio helps build your clothing brand for free. Start with:\n"
                "my brand is <name>, <style and who it's for>\n(e.g. 'my brand is Stringman, streetwear for Aussie gamers')")
    return (f"👕 Brand Studio: {p['name']}" + (f" ({p['style']})" if p.get("style") else "") +
            f"\nDesign ideas saved: {len(p.get('ideas', []))}\n"
            "Commands: design ideas · mockup 2 · listing 2 · add design 2 to my store · launch plan\n"
            "Selling without stock: see BRAND_SETUP.md (Printify or Printful, free to start).")


WANTS = re.compile(r"^\s*my (clothing )?brand is\s|^/brand\b|^(brand studio|my brand)$|"
                   r"^(new |more |give me |some )?(design|clothing|shirt|hoodie) ideas\b|"
                   r"^(mock-?up|picture of design|show design)\s*#?\d|^(listing|list design|write listing)\s*(for\s*)?(design\s*)?#?\d|"
                   r"^add design\s*#?\d\s+to |^(brand )?launch plan\b", re.I)


def wants(text):
    return bool(WANTS.match((text or "").strip()))


def handle(text, ask=None):
    """Returns (reply, image path or None), or None if the message isn't for Brand Studio."""
    t = text.strip()
    low = t.lower()
    reply = set_brand(t)
    if reply:
        return reply, None
    if low.startswith("/brand") or low in ("brand studio", "my brand"):
        return describe(), None
    if re.match(r"^(new |more |give me |some )?(design|clothing|shirt|hoodie) ideas\b", low):
        return design_ideas(ask), None
    m = re.match(r"^(?:mock-?up|picture of design|show design)\s*#?(\d)\b", low)
    if m:
        return mockup(int(m.group(1)))
    m = re.match(r"^(?:listing|list design|write listing)\s*(?:for\s*)?(?:design\s*)?#?(\d)\b", low)
    if m:
        return listing(int(m.group(1)), ask)[0], None
    m = re.match(r"^add design\s*#?(\d)\s+to (?:my |the )?(?:store|shop|shopify)", low)
    if m:
        return add_to_store(int(m.group(1))), None
    if re.match(r"^(brand )?launch plan\b", low):
        return launch_plan(ask), None
    return None
