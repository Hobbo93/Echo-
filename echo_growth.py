"""Echo grows: honest answers, learning from your corrections, and research while the PC is on.

1. Honesty. Every prompt starts with strict truth rules plus the real list of what Echo is
   and isn't connected to, so it stops making things up. check_reply() catches replies that
   claim something happened ("I've posted it", "I just checked the price") when nothing ran,
   and adds a clear note saying so.
2. Learning. When you correct Echo ("that's not true", "stop telling me what I want to hear",
   or /feedback ...), the correction is saved as a lesson. Each evening Echo reviews the day's
   chats and lessons and rewrites a short list of rules for how to talk to you. It tells you
   what changed, and /learned shows the list. Safety and honesty rules can't be overridden.
3. Research. While the PC is on (7 AM to 10 PM), Echo researches one topic every 90 minutes
   from real sources (Google News RSS and Wikipedia, free, no keys): first anything you asked
   for, then questions it couldn't answer, then your businesses. Notes are saved to memory
   with their sources, and only say what the sources say.

Standard library only. State lives in %USERPROFILE%\\.echo_growth.json.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import datetime
from pathlib import Path

import echo_memory
import echo_brain

STATE_FILE = Path.home() / ".echo_growth.json"
OLLAMA_URL = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
UA = {"User-Agent": "EchoPersonalAssistant/1.0 (local research)"}

RESEARCH_EVERY_MIN = 90
RESEARCH_HOURS = (7, 22)
RESEARCH_PER_DAY = 8
REFLECT_AT = "20:30"
MAX_RULES = 8
MAX_QUEUE = 25

BUSINESS_TOPICS = [
    "dog products trends Australia", "Shopify small business tips", "YouTube Shorts algorithm changes",
    "Instagram Reels trends", "TikTok trends Australia", "small business websites Adelaide",
    "Roblox game trends", "ASX market news", "Nasdaq market news", "new free AI tools",
    "Ollama new local AI models", "OpusClip updates",
]

HONESTY_RULES = (
    "HONESTY COMES FIRST, above your personality and above keeping the user happy:\n"
    "- Tell the truth, even when it's not what they want to hear. Point out problems and risks in their ideas.\n"
    "- If you don't know, say \"I don't know\" and offer to research it. Never guess and present it as fact.\n"
    "- Never invent facts, numbers, prices, news, quotes, sources, results or things that happened.\n"
    "- In this chat you can't browse the web, see live prices or check accounts. Only use what's listed "
    "below, what you remember, and general knowledge (say it may be out of date).\n"
    "- Never say you did something (sent, posted, bought, checked, booked) unless the system confirms it.\n"
    "- No flattery or empty praise. Praise only what's actually good. Say how sure you are when it matters."
)

# Replies that claim an outside action or live lookup happened. Chat replies can't do either.
_ACTION_CLAIM = re.compile(
    r"\b(I'?ve|I have|I just|I've just|I already|I went ahead and|I'?ll go ahead and)\s+(just\s+)?"
    r"(sent|emailed|posted|published|uploaded|scheduled|called|rang|texted|messaged|contacted|booked|"
    r"bought|sold|placed|ordered|paid|transferred|deposited|refunded|cancelled|deleted|"
    r"updated your|changed your|added (it|that|the)|listed|created (the|a|your) (listing|product|post|discount|website|site))\b",
    re.I)
_LIVE_CLAIM = re.compile(
    r"\b(I'?ve|I have|I just|I've just)\s+(checked|looked (it |that )?up|searched|browsed|googled|pulled up|"
    r"reviewed (your|the latest|the live))\b|\b(current(ly)?|right now|as of (now|today)|live)\b[^.\n]{0,40}"
    r"\b(price|trading at|is at|sits at|worth)\b[^.\n]{0,20}[$€£]\s?\d", re.I)
_DONT_KNOW = re.compile(r"\b(I don'?t know|I'?m not sure|I can'?t (check|confirm|verify|see)|"
                        r"I don'?t have (access|live|current|up-to-date)|no way for me to know)\b", re.I)
_FEEDBACK = re.compile(
    r"(👎|\b(that'?s|thats|this is|it'?s) (not true|wrong|false|made up|fake|bull\w*|rubbish|not real|a lie)\b|"
    r"\byou('?re| are) (wrong|lying|making (it|that|this|stuff|things) up)\b|"
    r"\bstop (lying|making (stuff|things|it) up|sugar ?coating|telling me what i want)|"
    r"\b(be|just be) honest\b|\btell me the truth\b|\bdidn'?t (actually )?happen\b|"
    r"\byou didn'?t (actually|really)\b|\bdon'?t (lie|make (stuff|things) up)\b|^/?feedback\b)", re.I)
_BAD_RULE = re.compile(r"\b(always agree|agree with everything|pretend|make (things|stuff|it) up|invent|"
                       r"lie|flatter|never say (no|i don'?t know)|hide|don'?t mention|guess)\b", re.I)


# ==========================================
# STATE
# ==========================================

def _load():
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        s = s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        s = {}
    s.setdefault("queue", [])          # [{"topic", "why", "asked"}]
    s.setdefault("rules", [])          # learned ways to talk to the owner
    s.setdefault("rotation", 0)
    s.setdefault("last_research", 0)
    s.setdefault("research_day", "")
    s.setdefault("research_count", 0)
    s.setdefault("last_reflect", "")
    s.setdefault("today", [])          # topics researched today, for the evening digest
    return s


def _save(s):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _ask(prompt, max_tokens=300, ask=None):
    if ask:
        return ask(prompt)
    payload = {"model": echo_brain.model(), "stream": False, "options": {"num_predict": max_tokens, "temperature": .2},
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(OLLAMA_URL, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r).get("message", {}).get("content", "").strip()


# ==========================================
# 1. HONESTY
# ==========================================

_caps = {"at": 0, "text": ""}


def capabilities(max_age=600):
    """What Echo can really do right now, from the real connection checks."""
    if time.time() - _caps["at"] < max_age and _caps["text"]:
        return _caps["text"]
    try:
        import echo_connections
        rows = echo_connections.check_all(live=False)
        on = [f"{r['office']} ({r['service']})" for r in rows if r["ok"]]
        off = [f"{r['office']} ({r['service']})" for r in rows if not r["ok"]]
        text = ("Connected and working: " + (", ".join(on) or "nothing yet") + ".\n"
                "NOT connected, so you can't use these: " + (", ".join(off) or "none") + ".")
    except Exception:
        text = "Connection status unknown right now: don't claim any connection works."
    _caps.update(at=time.time(), text=text)
    return text


def learned_text(lessons=3):
    """Learned rules for talking to the owner, plus the newest raw corrections."""
    s = _load()
    parts = []
    if s["rules"]:
        parts.append("How the owner wants you to talk (learned from them):\n" + "\n".join("- " + r for r in s["rules"]))
    recent = echo_memory.recall("lesson", lessons)
    if recent:
        parts.append("Recent corrections from the owner (don't repeat these mistakes):\n" +
                     "\n".join("- " + r["content"][:220] for r in recent))
    return "\n\n".join(parts)


def prompt_block():
    """Everything a system prompt needs from this module."""
    try:
        from echo_router import COMMANDS_HELP
    except Exception:
        COMMANDS_HELP = ""
    return "\n\n".join(p for p in (HONESTY_RULES, "What you're really connected to:\n" + capabilities(),
                                   COMMANDS_HELP, learned_text()) if p)


def check_reply(reply):
    """Add an honest note when a chat reply claims something that can't have happened."""
    if not reply:
        return reply
    notes = []
    if _ACTION_CLAIM.search(reply):
        notes.append("I can't do outside actions from a chat reply, so nothing was actually sent, posted, "
                     "bought or changed. Use the real command, and I'll ask for your Yes first.")
    if _LIVE_CLAIM.search(reply):
        notes.append("I can't look things up live in chat, so any \"current\" numbers or checks above are not "
                     "real-time. Treat them as unverified.")
    if not notes:
        return reply
    return reply.rstrip() + "\n\n⚠️ Honesty check: " + " ".join(notes)


def after_reply(message, reply):
    """If Echo admitted it didn't know, queue the question for research."""
    if reply and _DONT_KNOW.search(reply) and len(message.split()) >= 3 and "?" in message:
        queue(message.strip()[:120], why="you asked and I didn't know")


# ==========================================
# 2. LEARNING FROM YOU
# ==========================================

def is_feedback(text):
    return bool(text and _FEEDBACK.search(text.strip()))


def record_feedback(text, last_reply=""):
    """Save a correction as a lesson. Returns a short honest acknowledgement."""
    said = re.sub(r"^/?feedback[:\s]*", "", text.strip(), flags=re.I) or text.strip()
    lesson = f"Owner said: \"{said[:200]}\""
    if last_reply:
        lesson += f" about my reply: \"{last_reply[:160]}\""
    echo_memory.remember("lesson", lesson)
    return ("You're right to call that out, and I've saved it as a lesson. Tonight I'll go over today's "
            "chats and change how I answer. If something I said was made up, ignore it. Ask again and "
            "I'll say plainly what I don't know.")


def _parse_rules(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    items = []
    if m:
        try:
            items = [str(x) for x in json.loads(m.group(0))]
        except ValueError:
            items = []
    if not items:
        items = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", l) for l in (text or "").splitlines()
                 if re.match(r"\s*(?:[-*•]|\d+[.)])\s+", l)]
    rules = []
    for r in items:
        r = r.strip().strip('"').strip()
        if 10 <= len(r) <= 200 and not _BAD_RULE.search(r) and r not in rules:
            rules.append(r)
    return rules[:MAX_RULES]


def reflect(ask=None):
    """Review today's chats and lessons, rewrite the talking rules. Returns (added, removed)."""
    s = _load()
    with closing(echo_memory.connect()) as db:
        turns = db.execute("SELECT role, content FROM turns ORDER BY id DESC LIMIT 60").fetchall()
    chat = "\n".join(("Owner" if r["role"] == "user" else "Echo") + ": " + r["content"][:300]
                     for r in reversed(turns))
    lessons = "\n".join("- " + r["content"][:250] for r in echo_memory.recall("lesson", 15)) or "- (none)"
    old = "\n".join("- " + r for r in s["rules"]) or "- (none yet)"
    prompt = (
        "You are improving how an AI assistant called Echo talks to its owner. Echo must always be honest "
        "and never tell the owner what they want to hear if it isn't true.\n\n"
        f"Current rules:\n{old}\n\nCorrections the owner gave:\n{lessons}\n\nRecent chat:\n{chat or '(no chats)'}\n\n"
        f"Write the updated list of at most {MAX_RULES} short, specific rules for how Echo should talk to and "
        "react to this owner (tone, length, honesty, what annoys them, what helps them). Keep good current "
        "rules, fix ones the chats show are wrong, and add rules for every correction. "
        "Answer with only a JSON list of strings."
    )
    try:
        new = _parse_rules(_ask(prompt, 400, ask))
    except Exception:
        return None
    if not new:
        return None
    added = [r for r in new if r not in s["rules"]]
    removed = [r for r in s["rules"] if r not in new]
    s["rules"] = new
    _save(s)
    if added or removed:
        echo_memory.remember("growth", f"{datetime.now():%d %b %Y}: updated my talking rules. "
                             f"Added: {'; '.join(added) or 'none'}. Dropped: {'; '.join(removed) or 'none'}.")
    return added, removed


# ==========================================
# 3. RESEARCH
# ==========================================

def queue(topic, why="you asked"):
    topic = re.sub(r"\s+", " ", (topic or "")).strip()
    if len(topic) < 3:
        return "Tell me what to research, e.g. /research add dog jacket prices in Australia"
    s = _load()
    if any(q["topic"].lower() == topic.lower() for q in s["queue"]):
        return f"\"{topic}\" is already on my research list."
    s["queue"] = (s["queue"] + [{"topic": topic, "why": why, "asked": datetime.now().isoformat(timespec="minutes")}])[-MAX_QUEUE:]
    _save(s)
    return f"Added to my research list: \"{topic}\". I'll look into it while your PC is on and tell you what I find, with sources."


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(2_000_000)


def fetch_sources(topic, limit=6):
    """Real, recent sources for a topic: Google News headlines + Wikipedia background."""
    out = []
    try:
        q = urllib.parse.quote(topic + " when:14d")
        root = ET.fromstring(_get(f"https://news.google.com/rss/search?q={q}&hl=en-AU&gl=AU&ceid=AU:en"))
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if title:
                out.append({"title": title, "source": (item.findtext("source") or "Google News").strip(),
                            "date": (item.findtext("pubDate") or "")[:16], "link": (item.findtext("link") or "").strip(),
                            "text": re.sub(r"<[^>]+>", " ", item.findtext("description") or "")[:300]})
            if len(out) >= limit - 2:
                break
    except Exception:
        pass
    try:
        q = urllib.parse.quote(topic)
        data = json.loads(_get("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json"
                               f"&srlimit=2&srsearch={q}"))
        for hit in data.get("query", {}).get("search", []):
            out.append({"title": hit["title"], "source": "Wikipedia", "date": hit.get("timestamp", "")[:10],
                        "link": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(hit["title"].replace(" ", "_")),
                        "text": re.sub(r"<[^>]+>", "", hit.get("snippet", ""))[:300]})
    except Exception:
        pass
    return out[:limit]


def research(topic, ask=None, sources=None):
    """Research one topic from real sources. Returns the saved note, or None if nothing was found."""
    sources = fetch_sources(topic) if sources is None else sources
    if not sources:
        return None
    listing = "\n".join(f"[{i}] {s['title']} ({s['source']}, {s['date']}): {s['text']}"
                        for i, s in enumerate(sources, 1))
    prompt = (f"Topic: {topic}\n\nSources:\n{listing}\n\n"
              "Using ONLY these sources, write 2 to 4 short bullet points: what's new or important, and why it "
              "could matter for a small Australian business owner (dog products store on Shopify, short videos "
              "on YouTube/Instagram/TikTok, websites for local businesses, Roblox, trading). End each bullet "
              "with its source number like [2]. If the sources don't say something, don't say it. If they're "
              "not useful, write only: NOTHING USEFUL")
    try:
        notes = _ask(prompt, 350, ask)
    except Exception:
        return None
    if not notes or "NOTHING USEFUL" in notes.upper():
        notes = "Nothing useful in the sources I found."
    refs = "; ".join(f"[{i}] {s['source']}: {s['title'][:80]}" for i, s in enumerate(sources, 1))
    note = f"{datetime.now():%d %b %Y} research on \"{topic}\":\n{notes}\nSources: {refs}"
    echo_memory.remember("research", note)
    return note


def _next_topic(s):
    if s["queue"]:
        item = s["queue"].pop(0)
        return item["topic"], item.get("why", "")
    topic = BUSINESS_TOPICS[s["rotation"] % len(BUSINESS_TOPICS)]
    s["rotation"] += 1
    return topic, ""


def research_step(now=None, notify=None, ask=None):
    """Do one research job if it's time. notify(text) tells the owner about topics they asked for."""
    now = now or datetime.now()
    s = _load()
    day = now.date().isoformat()
    if s["research_day"] != day:
        s.update(research_day=day, research_count=0, today=[])
    if not (RESEARCH_HOURS[0] <= now.hour < RESEARCH_HOURS[1]) or s["research_count"] >= RESEARCH_PER_DAY \
            or time.time() - s["last_research"] < RESEARCH_EVERY_MIN * 60:
        return None
    topic, why = _next_topic(s)
    s["last_research"] = time.time()
    s["research_count"] += 1
    _save(s)
    note = research(topic, ask=ask)
    s = _load()
    s["today"] = (s["today"] + [topic])[-RESEARCH_PER_DAY:]
    _save(s)
    if note and why and notify:
        notify("🔎 Research you asked for:\n\n" + note)
    return note


# ==========================================
# DAILY ROUTINE (called by echo_scheduler.py every minute)
# ==========================================

def tick(now=None, notify=None, ask=None):
    now = now or datetime.now()
    if echo_brain.owner_active():
        return  # the owner is talking to Echo: research and the review wait for a quiet spell
    research_step(now, notify, ask)
    s = _load()
    day = now.date().isoformat()
    if now.strftime("%H:%M") >= REFLECT_AT and s["last_reflect"] != day:
        s["last_reflect"] = day
        _save(s)
        result = reflect(ask)
        if notify:
            notify(digest(result))


def digest(result=None):
    s = _load()
    lines = ["🌱 Echo's daily growth report"]
    if s["today"]:
        lines.append("\nResearched today: " + ", ".join(s["today"]))
        latest = [r for r in echo_memory.recall("research", 3)]
        for r in latest[:2]:
            lines.append("\n" + r["content"][:600])
    else:
        lines.append("\nNo research today (Ollama or the internet may have been off).")
    if result:
        added, removed = result
        if added:
            lines.append("\nI changed how I talk to you:\n" + "\n".join("+ " + r for r in added))
        if removed:
            lines.append("Dropped:\n" + "\n".join("- " + r for r in removed))
        if not added and not removed:
            lines.append("\nNo changes to how I talk today.")
    lines.append("\nCorrect me any time (\"that's not true\" or /feedback ...). /learned shows what I've learned.")
    return "\n".join(lines)


def describe_learning():
    s = _load()
    rules = "\n".join("• " + r for r in s["rules"]) or "• Nothing yet. I update these every evening."
    lessons = "\n".join("• " + r["content"][:180] for r in echo_memory.recall("lesson", 5)) or "• None yet"
    research_n = len(echo_memory.recall("research", 500))
    return (f"🧠 How I talk to you (learned):\n{rules}\n\nYour latest corrections:\n{lessons}\n\n"
            f"Research notes saved: {research_n}. Research list: {len(s['queue'])} waiting.")


def describe_research():
    s = _load()
    waiting = "\n".join(f"• {q['topic']} ({q.get('why', '')})" for q in s["queue"][:8]) or "• Nothing waiting"
    latest = echo_memory.recall("research", 2)
    found = "\n\n".join(r["content"][:700] for r in latest) or "No research notes yet."
    return (f"🔎 Research list:\n{waiting}\n\nLatest findings:\n\n{found}\n\n"
            "Add a topic: /research add dog jacket prices in Australia")
