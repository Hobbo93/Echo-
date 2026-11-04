"""Echo's business tools for the Sales, Finance, Customer Support, Operations and CEO offices.

Everything is stored in %USERPROFILE%\\Echo_business\\ as plain JSON, and every
completed action is written to a daily record (records\\<date>.jsonl).
Echo drafts messages but never sends them to customers, spends money or makes
big changes without your approval.

Commands (chat with the office in Echo HQ, or on Telegram):
  Sales:     pipeline · pitch <business> · mark <business> contacted|meeting|won|lost · follow ups
  Finance:   income 500 website for Joe's Barbers · expense 30 OpusClip · subscription 29 OpusClip monthly
             money (this month's profit and loss) · subscriptions
  Support:   enquiry <name>: <message> · tickets · reply <ticket no> · close <ticket no>
  CEO:       my goal is <goal> · goals · summary (daily business summary)
  Operations: status (is every part of Echo running?) · records (what got done today)
"""
import json
import os
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
import echo_brain

DIR = Path.home() / "Echo_business"
RECORDS = DIR / "records"
OLLAMA = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")

# Office-wide rules, added to every employee's instructions.
OFFICE_RULES = (
    "Office rules: work together with the other Echo employees and point the user to the right office "
    "when something belongs to them. Automate approved routine work and keep going on scheduled work while "
    "the user is away. Report important problems. Always ask for approval before spending money, publishing "
    "content, contacting customers or making significant business changes. Never execute live trades "
    "without explicit authorisation. Never claim you did something you didn't."
)


def _path(name):
    return DIR / (name + ".json")


def load(name, default):
    try:
        return json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(name, data):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(name).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, _path(name))


def record(office, what):
    """Keep a record of completed work."""
    RECORDS.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "office": office, "done": what})
    with open(RECORDS / (date.today().isoformat() + ".jsonl"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def records_today():
    try:
        rows = [json.loads(l) for l in (RECORDS / (date.today().isoformat() + ".jsonl")).read_text(
            encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        rows = []
    if not rows:
        return "Nothing recorded yet today."
    return "Done today:\n" + "\n".join(f"- {r['time'][11:16]} {r['office']}: {r['done']}" for r in rows[-30:])


def ask_ai(prompt, system="You are a helpful business assistant. Be concise and practical.", timeout=120):
    body = json.dumps({"model": echo_brain.model(), "stream": False, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(OLLAMA, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("message", {}).get("content", "").strip()


def money(v):
    return f"${v:,.2f}"


# ==========================================
# SALES: pipeline built from the daily leads
# ==========================================

STAGES = ["new", "contacted", "follow up", "meeting", "won", "lost"]


def _pipeline():
    p = load("pipeline", {})
    try:
        import echo_leads
        latest = echo_leads.latest()
    except Exception:
        latest = None
    if latest:
        added = 0
        for lead in latest.get("all_leads", []):
            key = lead.get("id") or lead["name"]
            if key not in p:
                p[key] = {"name": lead["name"], "phone": lead.get("phone", ""), "email": lead.get("email", ""),
                          "website": lead.get("website", ""), "category": lead.get("category", ""),
                          "address": lead.get("address", ""), "reasons": lead.get("reasons", []),
                          "folder": lead.get("folder", ""), "stage": "new", "updated": date.today().isoformat(),
                          "notes": []}
                added += 1
        if added:
            save("pipeline", p)
    return p


def _find(p, name):
    name = name.lower().strip()
    for key, lead in p.items():
        if name in lead["name"].lower():
            return key, lead
    return None, None


def pipeline_text():
    p = _pipeline()
    if not p:
        return ("Your pipeline is empty. Leads come in daily from the Website and Leads Manager "
                "once the Google Places key is set (LEADS_SETUP.md).")
    lines = ["SALES PIPELINE"]
    for stage in STAGES:
        names = [l["name"] for l in p.values() if l["stage"] == stage]
        if names:
            lines.append(f"{stage.title()} ({len(names)}): " + ", ".join(names[:8]) + (" …" if len(names) > 8 else ""))
    lines.append("\nSay 'pitch <business>' for a personalised message, or 'mark <business> contacted'.")
    return "\n".join(lines)


def pitch(name):
    p = _pipeline()
    key, lead = _find(p, name)
    if not lead:
        return f"I can't find '{name}' in the pipeline. Say 'pipeline' to see the businesses."
    facts = (f"Business: {lead['name']} ({lead['category']}), {lead['address']}. Website: "
             f"{lead['website'] or 'none'}. Why they're a fit: {'; '.join(lead['reasons'])}.")
    try:
        text = ask_ai("Write three short, friendly, personalised outreach drafts for this local Adelaide "
                      "business offering a modern website (and optionally an AI receptionist that answers "
                      "missed calls). 1) a text message under 300 characters, 2) a short email with a subject "
                      "line, 3) a 20-second phone opener. No hype, no fake claims, sign off as 'Tailen'.\n" + facts,
                      timeout=180)
    except Exception:
        text = (f"TEXT: Hi, I'm Tailen, a local web designer. I noticed {lead['name']} doesn't have its own "
                "website yet. I build simple, affordable sites that help customers find and call you. "
                "Happy to send a free mock-up? \n\nEMAIL subject: A website for " + lead['name'])
    if lead.get("folder"):
        try:
            Path(lead["folder"]).mkdir(parents=True, exist_ok=True)
            (Path(lead["folder"]) / "pitch.md").write_text(text, encoding="utf-8")
        except OSError:
            pass
    record("Sales Agent", "Drafted outreach for " + lead["name"])
    contact = " · ".join(x for x in (lead["phone"], lead["email"]) if x) or "no contact details yet"
    return (f"Outreach drafts for {lead['name']} ({contact}):\n\n{text}\n\n"
            "These are drafts: you send them yourself. Then say 'mark " + lead["name"].split()[0] + " contacted'.")


def mark(name, stage):
    stage = stage.lower().replace("followup", "follow up")
    if stage not in STAGES:
        return "Stages: " + ", ".join(STAGES)
    p = _pipeline()
    key, lead = _find(p, name)
    if not lead:
        return f"I can't find '{name}' in the pipeline."
    lead["stage"], lead["updated"] = stage, date.today().isoformat()
    save("pipeline", p)
    record("Sales Agent", f"{lead['name']} moved to {stage}")
    extra = " 🎉 Nice one! Log the payment with 'income <amount> website for " + lead["name"] + "'." if stage == "won" else ""
    return f"{lead['name']} is now '{stage}'.{extra}"


def follow_ups():
    p = _pipeline()
    due = [l for l in p.values() if l["stage"] in ("contacted", "follow up")
           and date.fromisoformat(l["updated"]) <= date.today() - timedelta(days=3)]
    if not due:
        return "No follow-ups due. (I remind you 3 days after you contact someone.)"
    return "Follow-ups due:\n" + "\n".join(f"- {l['name']} ({l['phone'] or l['email'] or 'no contact'}), "
                                           f"last update {l['updated']}" for l in due)


# ==========================================
# FINANCE
# ==========================================

def _ledger():
    return load("ledger", {"entries": [], "subscriptions": []})


def add_entry(kind, amount, what):
    led = _ledger()
    led["entries"].append({"date": date.today().isoformat(), "kind": kind, "amount": round(amount, 2), "what": what})
    save("ledger", led)
    record("Finance Manager", f"Logged {kind} {money(amount)}: {what}")
    return f"Logged {kind}: {money(amount)} ({what}). {month_summary(short=True)}"


def add_subscription(amount, name, period="monthly"):
    led = _ledger()
    led["subscriptions"] = [s for s in led["subscriptions"] if s["name"].lower() != name.lower()]
    led["subscriptions"].append({"name": name, "amount": round(amount, 2), "period": period})
    save("ledger", led)
    record("Finance Manager", f"Tracking subscription {name} {money(amount)} {period}")
    return f"Tracking {name}: {money(amount)} {period}. " + subscriptions_text().split("\n")[-1]


def _monthly_subs(led):
    total = 0.0
    for s in led["subscriptions"]:
        total += s["amount"] / 12 if s["period"].startswith("year") else s["amount"] * (4.33 if s["period"].startswith("week") else 1)
    return total


def subscriptions_text():
    led = _ledger()
    if not led["subscriptions"]:
        return "No subscriptions tracked yet. Example: subscription 29 OpusClip monthly"
    lines = ["Subscriptions:"] + [f"- {s['name']}: {money(s['amount'])} {s['period']}" for s in led["subscriptions"]]
    lines.append(f"Running costs: about {money(_monthly_subs(led))} a month.")
    return "\n".join(lines)


def month_summary(short=False):
    led = _ledger()
    month = date.today().strftime("%Y-%m")
    rows = [e for e in led["entries"] if e["date"].startswith(month)]
    income = sum(e["amount"] for e in rows if e["kind"] == "income")
    spend = sum(e["amount"] for e in rows if e["kind"] == "expense")
    subs = _monthly_subs(led)
    profit = income - spend - subs
    if short:
        return f"This month: income {money(income)}, profit {money(profit)}."
    by = {}
    for e in rows:
        if e["kind"] == "income":
            src = e["what"].split(" for ")[0].split()[0].lower() if e["what"] else "other"
            by[src] = by.get(src, 0) + e["amount"]
    lines = [f"MONEY - {date.today():%B %Y}",
             f"Income: {money(income)}",
             f"Expenses: {money(spend)}",
             f"Subscriptions: {money(subs)} a month",
             f"{'Profit' if profit >= 0 else 'Loss'}: {money(abs(profit))}"]
    if by:
        lines.append("Income by type: " + ", ".join(f"{k} {money(v)}" for k, v in sorted(by.items(), key=lambda x: -x[1])))
    if not rows:
        lines.append("\nNothing logged this month. Say 'income 500 website for Joe's Barbers' or 'expense 30 OpusClip'.")
    return "\n".join(lines)


# ==========================================
# CUSTOMER SUPPORT
# ==========================================

def _tickets():
    return load("tickets", [])


def new_ticket(customer, message):
    t = _tickets()
    num = (max((x["no"] for x in t), default=0) + 1)
    urgent = bool(re.search(r"\b(urgent|asap|refund|broken|down|not working|angry|complain|cancel)\b", message, re.I))
    t.append({"no": num, "customer": customer, "message": message, "status": "open", "urgent": urgent,
              "opened": date.today().isoformat()})
    save("tickets", t)
    record("Customer Support", f"Logged enquiry #{num} from {customer}")
    return (f"Logged enquiry #{num} from {customer}." + (" ⚠️ Marked urgent: I'll flag it in your reports." if urgent else "")
            + f" Say 'reply {num}' and I'll draft a response.")


def draft_reply(num):
    t = _tickets()
    tk = next((x for x in t if x["no"] == num), None)
    if not tk:
        return f"No ticket #{num}."
    try:
        text = ask_ai(f"Draft a warm, professional reply from Tailen to this customer enquiry. Keep it short, "
                      f"solve the problem or say what happens next, don't promise anything uncertain.\n\n"
                      f"Customer: {tk['customer']}\nMessage: {tk['message']}")
    except Exception:
        text = f"Hi {tk['customer']}, thanks for getting in touch. I'm looking into this and will get back to you shortly. - Tailen"
    record("Customer Support", f"Drafted reply to #{num}")
    return f"Draft reply to #{num} ({tk['customer']}):\n\n{text}\n\nYou send it. Then say 'close {num}'."


def close_ticket(num):
    t = _tickets()
    for x in t:
        if x["no"] == num:
            x["status"] = "closed"
            save("tickets", t)
            record("Customer Support", f"Closed #{num}")
            return f"Closed #{num}. 👍"
    return f"No ticket #{num}."


def tickets_text():
    open_t = [x for x in _tickets() if x["status"] == "open"]
    if not open_t:
        return "No open customer enquiries. Log one with: enquiry <name>: <message>"
    return "Open enquiries:\n" + "\n".join(
        f"- #{x['no']} {'⚠️ ' if x['urgent'] else ''}{x['customer']}: {x['message'][:80]}" for x in open_t)


# ==========================================
# OPERATIONS: is everything running?
# ==========================================

HEARTBEATS = DIR / "heartbeats"


def heartbeat(part):
    HEARTBEATS.mkdir(parents=True, exist_ok=True)
    (HEARTBEATS / part).write_text(str(time.time()), encoding="utf-8")


def status_text():
    lines = ["ECHO STATUS"]
    for part, label, limit in (("server", "Echo HQ server", 600), ("scheduler", "Scheduler (reports, leads, trading)", 300),
                               ("telegram", "Telegram chat", 300)):
        try:
            age = time.time() - float((HEARTBEATS / part).read_text())
            ok = age < limit
            lines.append(f"{'🟢' if ok else '🔴'} {label}: {'running' if ok else 'not heard from in ' + str(int(age // 60)) + ' min'}")
        except (OSError, ValueError):
            lines.append(f"⚪ {label}: no signal yet")
    try:
        import echo_preflight
        o = echo_preflight.check_ollama()
        lines.append(("🟢" if o.get("status") == "ok" else "🔴") + " AI brain (Ollama): " + o.get("detail", o.get("status", "")))
    except Exception:
        pass
    try:
        import echo_leads
        lines.append(("🟢" if echo_leads.API_KEY else "⚪") + " Lead finder: " + ("on" if echo_leads.API_KEY else "needs Google Places key"))
    except Exception:
        pass
    try:
        import echo_broker
        lines.append(("🟢 Broker: " + echo_broker.mode()) if echo_broker.is_configured() else "⚪ Broker: not connected (Trench tickets / paper)")
    except Exception:
        pass
    return "\n".join(lines)


# ==========================================
# CEO: goals and the daily business summary
# ==========================================

def set_goal(text):
    goals = load("goals", [])
    goals.append({"goal": text, "set": date.today().isoformat()})
    save("goals", goals[-10:])
    record("CEO", "New goal: " + text)
    return "Got it. I'll set everyone's priorities around: " + text


def goals_text():
    goals = load("goals", [])
    if not goals:
        return "No goals set yet. Tell me: my goal is <what you want>, e.g. 'my goal is $3,000 a month from websites by March'."
    return "Your goals:\n" + "\n".join("- " + g["goal"] for g in goals)


def ceo_summary():
    """The daily business summary: numbers from every office + priorities for tomorrow."""
    parts = []
    try:
        from echo_tasks import load_tasks
        tasks = load_tasks().values()
        waiting = sum(t["status"] == "waiting_for_approval" for t in tasks)
        parts.append(f"Tasks waiting for your approval: {waiting}")
    except Exception:
        pass
    p = _pipeline()
    if p:
        counts = {s: sum(l["stage"] == s for l in p.values()) for s in STAGES}
        parts.append("Sales pipeline: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    fu = follow_ups()
    if fu.startswith("Follow-ups due"):
        parts.append(fu)
    parts.append(month_summary(short=True))
    open_t = [x for x in _tickets() if x["status"] == "open"]
    if open_t:
        parts.append(f"Customer enquiries open: {len(open_t)} ({sum(x['urgent'] for x in open_t)} urgent)")
    try:
        import echo_trading
        st = echo_trading.trench_stats()
        if st:
            parts.append(st)
    except Exception:
        pass
    parts.append(status_text())
    facts = "\n".join(parts)
    goals = goals_text()
    try:
        plan = ask_ai("You are the CEO of Echo, Tailen's AI office (employees: Sales Agent, Marketing Manager, "
                      "Shopify Manager, Research Agent, Operations Manager, Finance Manager, Customer Support, "
                      "Website and Leads Manager, Content Creator, Day Trading Desk, Roblox Map Builder). Using these "
                      "facts and goals, give tomorrow's top 3 priorities, each with which employee owns it and one "
                      "concrete next step. Be brief and honest; don't invent numbers.\n\nFACTS:\n" + facts +
                      "\n\nGOALS:\n" + goals, timeout=180)
    except Exception:
        plan = "(AI brain unavailable, so no priorities today. Check Ollama is running.)"
    record("CEO", "Sent the daily business summary")
    return f"📋 ECHO CEO SUMMARY - {date.today():%a %d %b}\n\n{facts}\n\nTOMORROW'S PRIORITIES\n{plan}"


# ==========================================
# COMMANDS for each office
# ==========================================

def _num(s):
    return float(s.replace(",", "").replace("$", ""))


def handle(employee_name, text):
    """Run an office command. Returns a reply, or None to let the AI answer normally."""
    t = text.strip()
    low = t.lower()
    n = (employee_name or "").lower()
    try:
        if "sales" in n or low.startswith(("pipeline", "pitch ", "mark ", "follow up")):
            if re.search(r"\bpipeline\b", low):
                return pipeline_text()
            m = re.match(r"^pitch\s+(.+)", t, re.I)
            if m:
                return pitch(m.group(1))
            m = re.match(r"^mark\s+(.+?)\s+(new|contacted|follow ?up|meeting|won|lost)\s*$", t, re.I)
            if m:
                return mark(m.group(1), m.group(2).replace("followup", "follow up"))
            if re.search(r"\bfollow ?ups?\b", low):
                return follow_ups()
        if "finance" in n or re.match(r"^(income|expense|subscription|money|subscriptions)\b", low):
            m = re.match(r"^(income|expense)\s+\$?([\d,.]+)\s*(.*)", t, re.I)
            if m:
                return add_entry(m.group(1).lower(), _num(m.group(2)), m.group(3).strip() or "unspecified")
            m = re.match(r"^subscription\s+\$?([\d,.]+)\s+(.+?)(?:\s+(monthly|yearly|weekly))?\s*$", t, re.I)
            if m:
                return add_subscription(_num(m.group(1)), m.group(2).strip(), (m.group(3) or "monthly").lower())
            if re.search(r"\bsubscriptions\b", low):
                return subscriptions_text()
            if re.search(r"\b(money|profit|loss|p&l|report|income|expenses)\b", low):
                return month_summary()
        if "support" in n or low.startswith(("enquiry", "tickets", "reply ", "close ")):
            m = re.match(r"^enquiry\s+(.+?):\s*(.+)", t, re.I)
            if m:
                return new_ticket(m.group(1).strip(), m.group(2).strip())
            m = re.match(r"^reply\s+#?(\d+)", t, re.I)
            if m:
                return draft_reply(int(m.group(1)))
            m = re.match(r"^close\s+#?(\d+)", t, re.I)
            if m:
                return close_ticket(int(m.group(1)))
            if re.search(r"\b(tickets|enquiries|inbox)\b", low):
                return tickets_text()
        if "ceo" in n or low.startswith(("my goal", "goals", "summary")):
            m = re.match(r"^my goal is\s+(.+)", t, re.I)
            if m:
                return set_goal(m.group(1).strip())
            if re.search(r"\bgoals?\b", low) and "my goal" not in low:
                return goals_text()
            if re.search(r"\b(summary|report|how('s| is) (the )?business|update)\b", low):
                return ceo_summary()
        if "operations" in n or low in ("status", "records"):
            if re.search(r"\b(status|running|health|errors?|problems?)\b", low):
                return status_text()
            if re.search(r"\b(records|done today|completed)\b", low):
                return records_today()
    except Exception as exc:
        return "Something went wrong: " + str(exc)[:200]
    return None


# ==========================================
# OFFICE FEED: what each department is working on, needs, and chats about
# (drives the bots and speech bubbles in the 3D HQ)
# ==========================================

def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def office_feed():
    feed = {}

    def dept(key, working, needs, chatter):
        feed[key] = {"working": [w for w in working if w], "needs": [n for n in needs if n],
                     "chatter": [c for c in chatter if c]}

    tasks = _safe(lambda: list(__import__("echo_tasks").load_tasks().values()), []) or []
    waiting = lambda name: sum(1 for t in tasks if t.get("employee") == name and t["status"] == "waiting_for_approval")
    rec = _safe(lambda: [json.loads(l) for l in (RECORDS / (date.today().isoformat() + ".jsonl")).read_text(
        encoding="utf-8").splitlines() if l.strip()], []) or []
    done = lambda office: [r["done"] for r in rec if r["office"] == office][-3:]

    # Sales
    p = _safe(_pipeline, {}) or {}
    counts = {s: sum(l["stage"] == s for l in p.values()) for s in STAGES}
    fu = _safe(follow_ups, "")
    dept("sales",
         [f"{len(p)} businesses in the pipeline" if p else "Waiting for today's leads",
          f"{counts['contacted']} contacted, {counts['meeting']} meetings, {counts['won']} won" if p else ""] + done("Sales Agent"),
         ["Follow-ups are due" if fu.startswith("Follow-ups due") else "",
          "" if p else "No leads yet: the Leads Manager needs the Google Places key"],
         [("Who's next on the call list?", f"{counts['new']} fresh leads, start with the ones with no website." if p else "Nobody yet. We need leads first."),
          ("Did we hear back from anyone?", "Follow-ups are due, we should nudge them." if fu.startswith("Follow-ups due") else "Not yet, give it a couple of days."),
          ("Any wins this month?", f"{counts['won']} so far!" if counts["won"] else "Not yet. Let's get the first one.")])

    # Web design + leads + Roblox
    leads = _safe(lambda: __import__("echo_leads").latest())
    key = _safe(lambda: bool(__import__("echo_leads").API_KEY), False)
    maps = _safe(lambda: len(__import__("echo_roblox").list_maps(100)), 0)
    dept("webdesign",
         [f"{leads['researched']} businesses found on {leads['date']}" if leads else "Ready to find 20 local businesses a day",
          f"{maps} Roblox maps built" if maps else "Roblox Map Builder is ready for requests"] + done("Website and Leads Manager"),
         ["" if key else "Needs the Google Places key to find leads (LEADS_SETUP.md)"],
         [("Got any new businesses for us?", "Twenty fresh ones today, briefs are ready for Base44." if leads else "Can't search yet, we still need that Google key."),
          ("Which ones need a site the most?", "The busy ones with great reviews and no website."),
          ("Anyone asked for a Roblox map?", f"We've built {maps} so far." if maps else "Not yet, I'm ready when Tailen is.")])

    # Content + editing
    cw = waiting("Content Creator")
    dept("content",
         [f"{cw} video and clip ideas planned" if cw else "Planning today's content ideas", "Clipping long videos into Shorts with OpusClip"],
         [f"{cw} ideas are waiting for Tailen's approval" if cw else "", "Video tools aren't connected to Echo yet, so ideas stay as plans"],
         [("How many ideas today?", f"{cw} waiting for approval." if cw else "Working on a fresh batch."),
          ("Can we post anything yet?", "Only once Tailen approves. That's the rule."),
          ("What's trending?", "Short reaction clips and quick tips are doing well.")])
    dept("editing",
         ["Cleaning up clips: captions, cutting filler words and pauses", "Ready to polish Twitch streams and YouTube videos"],
         ["Send a video or Twitch link to start a clip batch"],
         [("Got footage to edit?", "Waiting on the next stream link."),
          ("Captions or no captions?", "Always captions. Most people watch on mute."),
          ("Should we cut the ums?", "Every single one.")])

    # Marketing, research
    dept("marketing", ["Planning campaigns and watching competitors"] + done("Marketing Manager"),
         ["Tell me what to promote and the budget (I never spend without approval)"],
         [("What are we promoting this week?", "The website service. Local businesses need it."),
          ("Ads or organic?", "Organic first, ads once we know what converts.")])
    dept("research", ["Scanning new AI tools and income ideas"] + done("Research Agent"),
         [], [("Found anything good?", "A few AI tools that could automate more of our work."),
              ("Any new income ideas?", "AI receptionists for tradies look promising.")])

    # Operations
    st = _safe(status_text, "") or ""
    bad = [l[2:] for l in st.splitlines() if l.startswith("🔴")]
    dept("operations",
         ["Monitoring every part of Echo", f"{len(rec)} things recorded as done today"],
         bad or [],
         [("Everything running?", "All systems green." if not bad else "Not quite: " + bad[0]),
          ("Reports going out on time?", "6:30, 1 and 5:30, like clockwork."),
          ("Anyone slacking?", f"Nope. {len(rec)} jobs done today.")])

    # Finance
    ms = _safe(lambda: month_summary(short=True), "") or ""
    subs = len(_safe(_ledger, {"subscriptions": []})["subscriptions"])
    dept("finance", [ms or "Tracking income and expenses", f"{subs} subscriptions tracked" if subs else ""],
         ["" if subs else "Tell me your subscriptions so I can track running costs"],
         [("How are we tracking this month?", ms or "Nothing logged yet this month."),
          ("Any bills coming up?", f"{subs} subscriptions to watch." if subs else "I don't know any yet, need Tailen to tell me.")])

    # Shopify
    sh = _safe(lambda: __import__("echo_shopify"))
    connected = bool(sh and _safe(sh.is_configured, False))
    sp = _safe(sh.pending) if sh else None
    changes = _safe(lambda: sh.recent_changes(3), []) if sh else []
    dept("shopify",
         ([c["result"].splitlines()[0].replace("✅ ", "Done: ") for c in changes] or ["Connected to Furventure, ready for jobs"])
         if connected else ["Waiting to be connected to the store"],
         ([f"Waiting for your Yes: {sh.describe(sp).splitlines()[0]}" if sp else ""] if connected else
          ["Not connected to Shopify yet: double-click connect_echo.bat (SHOPIFY_SETUP.md)"]),
         [("Store connected?", "Yes, I can add and change products." if connected else "Not yet, I can only talk until Tailen connects me."),
          ("Anything to change?", "Waiting on Tailen's Yes." if sp else "Tell me what to add or update.")])

    # Trading
    tr = _safe(lambda: __import__("echo_trading"))
    pend = _safe(lambda: tr.pending()) if tr else None
    opens = _safe(lambda: [t for t in tr._load().get("trench", []) if t["status"] == "open"], []) if tr else []
    tst = _safe(lambda: tr.trench_stats(), "") if tr else ""
    dept("trading",
         [f"Watching {len(opens)} open Trench trades" if opens else "Scanning the market every weekday at 7:30 PM", tst],
         [f"Trade idea waiting for approval: {pend['symbol']}" if pend else "",
          "" if _safe(lambda: __import__("echo_broker").is_configured(), False) else
          "Practice account only: connect Alpaca (connect_echo.bat) for real trades"],
         [("What's the market doing?", "Mostly WAIT right now. No clean setups." if not pend else f"{pend['symbol']} looks good, sent it to Tailen."),
          ("Should we trade?", "Only with Tailen's yes. And only good setups."),
          ("Win rate?", tst or "No closed trades yet, we're being patient.")])

    # Support
    tk = _safe(lambda: [x for x in _tickets() if x["status"] == "open"], []) or []
    urg = [x for x in tk if x["urgent"]]
    dept("support", [f"{len(tk)} customer enquiries open" if tk else "Inbox clear, ready for enquiries"] + done("Customer Support"),
         [f"Urgent enquiry from {urg[0]['customer']}" if urg else ""],
         [("Any customers waiting?", f"{len(tk)} open, {len(urg)} urgent." if tk else "All quiet right now."),
          ("How's satisfaction?", "Happy so far!")])

    # CEO
    goals = load("goals", [])
    dept("ceo", ["Keeping everyone focused on: " + goals[-1]["goal"] if goals else "Waiting for Tailen's goals",
                 "Daily business summary at 6 PM"],
         ["" if goals else "Tell me your goal: 'my goal is ...'"],
         [("What's the priority today?", "Get the first website client." if not goals else goals[-1]["goal"]),
          ("Everyone on track?", "Mostly. A few things need Tailen's approval.")])
    dept("relax", ["Recharging and brainstorming new ideas"], [],
         [("Coffee?", "Always."), ("Big idea?", "What if Echo ran a whole agency?"), ("Break's over?", "Five more minutes.")])
    return feed


def rundown():
    """What Echo says when you click it: what's been done and what's needed."""
    lines = ["👋 Here's the rundown:", ""]
    rec_text = records_today()
    lines.append(rec_text if not rec_text.startswith("Nothing") else "Nothing's been marked as done yet today.")
    lines.append("")
    lines.append(month_summary(short=True))
    p = _safe(_pipeline, {}) or {}
    if p:
        lines.append(f"Sales pipeline: {len(p)} businesses, {sum(l['stage'] == 'won' for l in p.values())} won.")
    try:
        import echo_phone
        needs = echo_phone.briefing()
    except Exception:
        needs = []
    lines += ["", "What the team needs from you:"] + (["- " + n for n in needs] if needs else ["- Nothing right now 🎉"])
    return "\n".join(lines)
