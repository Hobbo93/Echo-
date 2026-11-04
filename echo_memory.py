"""Echo's long-term memory: one shared store for every part of Echo.

Everything lives in echo_memory.db next to this file (never committed to GitHub).

- remember(category, text)  save a fact, e.g. remember("about_you", "I like short replies")
- relevant(message)         only the few memories that match what you just said
- context_for(message)      those memories as text, ready to add to a prompt
- log_turn(channel, ...)    keeps each conversation; once a chat gets long, Echo's
                            local model writes a short summary and saves it as a
                            memory, so Echo still knows what you talked about
                            after a restart.

Searching uses SQLite's built-in full-text search, so it is fast and needs no
extra installs. Standard library only.
"""
import json
import os
import re
import sqlite3
import threading
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import echo_brain

DB_PATH = Path(__file__).with_name("echo_memory.db")
OLLAMA_URL = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")

SUMMARY_AFTER = 20   # unsummarised messages in a chat before a summary is written
KEEP_TURNS = 400     # raw messages kept per chat once summarised (older ones are deleted)

# Older memory files that are copied in once, then left untouched.
OLD_PERSONALITY = Path.home() / ".echo_personality.json"
OLD_JSON_MEMORY = Path.home() / ".echo_memory.json"

STOPWORDS = set("""a an and are as at be but by can could did do does for from had has have
how i if in into is it its just me my of on or our please so that the their them then there
these they this to up us was we were what when where which who why will with would you your
echo hey hi ok okay yes no""".split())

_lock = threading.Lock()
_summarising = set()
_fts = None  # whether this SQLite has full-text search (almost always yes)


def _now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    """Open the database, creating tables the first time."""
    global _fts
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            summarised INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS turns_channel ON turns(channel, summarised);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    if _fts is None:
        try:
            db.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(content, category, content='memories', content_rowid='id');
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO memories_fts(rowid, content, category)
                    VALUES (new.id, new.content, new.category);
                END;
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO memories_fts(memories_fts, rowid, content, category)
                    VALUES ('delete', old.id, old.content, old.category);
                END;
            """)
            # Index memories saved before search existed (older echo_memory.db files).
            if not db.execute("SELECT value FROM meta WHERE key='fts_built'").fetchone():
                db.execute("INSERT INTO memories_fts(memories_fts) VALUES ('rebuild')")
                db.execute("INSERT OR REPLACE INTO meta VALUES ('fts_built', '1')")
            _fts = True
        except sqlite3.OperationalError:
            _fts = False
    db.commit()
    return db


# ==========================================
# FACTS
# ==========================================

def remember(category, content):
    """Save information permanently. Saving the same thing twice keeps one copy."""
    if not isinstance(content, str):
        content = json.dumps(content)
    content = content.strip()
    if not content:
        return None
    with _lock, closing(connect()) as db:
        found = db.execute("SELECT id FROM memories WHERE category=? AND lower(content)=lower(?)",
                           (category, content)).fetchone()
        if found:
            return found["id"]
        cursor = db.execute("INSERT INTO memories (category, content, created_at) VALUES (?, ?, ?)",
                            (category, content, _now()))
        db.commit()
        return cursor.lastrowid


def recall(category=None, limit=20):
    """The newest memories (optionally from one category), newest first."""
    limit = max(1, min(int(limit), 500))
    with closing(connect()) as db:
        if category is None:
            rows = db.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?", (limit,))
        else:
            rows = db.execute("SELECT * FROM memories WHERE category=? ORDER BY id DESC LIMIT ?",
                              (category, limit))
        return [dict(row) for row in rows]


def forget(memory_id):
    """Delete one memory by its number."""
    with _lock, closing(connect()) as db:
        gone = db.execute("DELETE FROM memories WHERE id=?", (int(memory_id),)).rowcount > 0
        db.commit()
        return gone


def count():
    with closing(connect()) as db:
        return db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]


def _keywords(text):
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'$.-]*", (text or "").lower())
    out = []
    for w in words:
        w = w.strip("'.-")
        if len(w) > 2 and w not in STOPWORDS and w not in out:
            out.append(w)
    return out[:12]


def relevant(message, limit=6, categories=None):
    """Only the memories that match this message, best match first."""
    words = _keywords(message)
    if not words:
        return []
    cats = list(categories or [])
    with closing(connect()) as db:
        if _fts:
            query = " OR ".join('"' + w.replace('"', "") + '"' for w in words)
            sql = ("SELECT m.* FROM memories_fts f JOIN memories m ON m.id = f.rowid "
                   "WHERE memories_fts MATCH ?")
            args = [query]
            if cats:
                sql += " AND m.category IN (%s)" % ",".join("?" * len(cats))
                args += cats
            sql += " ORDER BY bm25(memories_fts) LIMIT ?"
            try:
                return [dict(r) for r in db.execute(sql, args + [limit])]
            except sqlite3.OperationalError:
                pass
        # Fallback without full-text search: simple word matching.
        rows = db.execute("SELECT * FROM memories ORDER BY id DESC LIMIT 2000").fetchall()
        scored = []
        for r in rows:
            if cats and r["category"] not in cats:
                continue
            text = r["content"].lower()
            score = sum(1 for w in words if w in text)
            if score:
                scored.append((score, r["id"], dict(r)))
        scored.sort(key=lambda s: (-s[0], -s[1]))
        return [s[2] for s in scored[:limit]]


def context_for(message, limit=6, always=("about_you",), always_limit=8):
    """Memories worth adding to a prompt: a few recent facts about you, plus
    whatever matches this message. Returns '' when there is nothing useful."""
    picked, seen = [], set()
    for cat in always:
        for r in recall(cat, always_limit):
            if r["id"] not in seen:
                seen.add(r["id"])
                picked.append(r)
    for r in relevant(message, limit):
        if r["id"] not in seen:
            seen.add(r["id"])
            picked.append(r)
    if not picked:
        return ""
    lines = []
    for r in picked:
        label = "earlier chat" if r["category"].startswith("summary") else r["category"].replace("_", " ")
        lines.append(f"- ({label}) {r['content'][:400]}")
    return "Things you remember that may help (use them only if relevant):\n" + "\n".join(lines)


# ==========================================
# CONVERSATIONS AND SUMMARIES
# ==========================================

def log_turn(channel, user_text, reply, summarise=False):
    """Keep one back-and-forth. Chats are summarised later by the scheduler, once they go quiet,
    so summaries never slow down a conversation (summarise=True forces one now for very long chats)."""
    with _lock, closing(connect()) as db:
        now = _now()
        db.executemany("INSERT INTO turns (channel, role, content, created_at) VALUES (?, ?, ?, ?)",
                       [(channel, "user", str(user_text)[:4000], now),
                        (channel, "assistant", str(reply)[:4000], now)])
        db.commit()
        waiting = db.execute("SELECT COUNT(*) FROM turns WHERE channel=? AND summarised=0",
                             (channel,)).fetchone()[0]
    if summarise and waiting >= SUMMARY_AFTER:
        threading.Thread(target=summarise_channel, args=(channel,), daemon=True).start()


def _ask_model(prompt):
    payload = {"model": echo_brain.model(), "stream": False, "options": {"num_predict": 220},
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(OLLAMA_URL, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r).get("message", {}).get("content", "").strip()


def summarise_channel(channel, ask=None):
    """Turn a chat's unsummarised messages into one short memory. Safe to call
    any time; if the model is offline the messages wait for next time."""
    with _lock:
        if channel in _summarising:
            return None
        _summarising.add(channel)
    try:
        with closing(connect()) as db:
            rows = db.execute("SELECT id, role, content FROM turns WHERE channel=? AND summarised=0 "
                              "ORDER BY id LIMIT 60", (channel,)).fetchall()
        if len(rows) < 4:
            return None
        chat = "\n".join(("You" if r["role"] == "user" else "Echo") + ": " + r["content"][:600] for r in rows)
        prompt = ("Summarise this conversation in 2 to 5 short bullet points for Echo's long-term memory. "
                  "Keep decisions, plans, names, numbers, preferences and anything still to do. "
                  "Skip small talk. Write only the bullet points.\n\n" + chat)
        try:
            summary = (ask or _ask_model)(prompt)
        except Exception:
            return None
        if not summary:
            return None
        day = datetime.now().strftime("%d %b %Y")
        remember("summary:" + channel, f"{day}: {summary}")
        with _lock, closing(connect()) as db:
            db.execute("UPDATE turns SET summarised=1 WHERE channel=? AND id<=?", (channel, rows[-1]["id"]))
            old = db.execute("SELECT id FROM turns WHERE channel=? ORDER BY id DESC LIMIT 1 OFFSET ?",
                             (channel, KEEP_TURNS)).fetchone()
            if old:
                db.execute("DELETE FROM turns WHERE channel=? AND summarised=1 AND id<=?", (channel, old["id"]))
            db.commit()
        return summary
    finally:
        with _lock:
            _summarising.discard(channel)


def summarise_finished_chats(quiet_minutes=15):
    """Summarise chats that have gone quiet (the scheduler calls this). Catches
    short chats and phone calls, which aren't summarised while they happen."""
    cutoff = (datetime.now(timezone.utc).timestamp() - quiet_minutes * 60)
    with closing(connect()) as db:
        rows = db.execute("SELECT channel, COUNT(*) AS n, MAX(created_at) AS last FROM turns "
                          "WHERE summarised=0 GROUP BY channel").fetchall()
    done = 0
    for r in rows:
        try:
            quiet = datetime.fromisoformat(r["last"]).timestamp() < cutoff
        except ValueError:
            quiet = True
        if r["n"] >= 4 and quiet and summarise_channel(r["channel"]):
            done += 1
    return done


def last_summary(channel):
    rows = recall("summary:" + channel, 1)
    return rows[0]["content"] if rows else ""


# ==========================================
# ONE-TIME MOVE OF OLDER MEMORY FILES
# ==========================================

def migrate():
    """Copy facts from Echo's older memory files in, once. The old files are kept."""
    with closing(connect()) as db:
        if db.execute("SELECT value FROM meta WHERE key='migrated'").fetchone():
            return 0
    moved = 0
    try:
        facts = json.loads(OLD_PERSONALITY.read_text(encoding="utf-8")).get("facts", [])
    except (OSError, ValueError, AttributeError):
        facts = []
    for fact in facts:
        if isinstance(fact, str) and remember("about_you", fact):
            moved += 1
    try:
        old = json.loads(OLD_JSON_MEMORY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    if isinstance(old, dict):
        for key, value in old.items():
            if remember("note", f"{key}: {value if isinstance(value, str) else json.dumps(value)}"):
                moved += 1
    with _lock, closing(connect()) as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('migrated', ?)", (_now(),))
        db.commit()
    return moved


def describe(limit=15):
    """A short list of what Echo remembers, for /memories on Telegram."""
    rows = [r for r in recall(limit=200) if not r["category"].startswith("summary")][:limit]
    summaries = sum(1 for r in recall(limit=500) if r["category"].startswith("summary"))
    if not rows and not summaries:
        return "I haven't saved any memories yet. Say \"remember that ...\" and I'll keep it."
    lines = [f"#{r['id']} ({r['category'].replace('_', ' ')}) {r['content'][:150]}" for r in rows]
    tail = f"\n\nPlus {summaries} summaries of earlier chats." if summaries else ""
    return ("🧠 What I remember (newest first):\n" + "\n".join(lines) + tail +
            "\n\nTo delete one, send: /forget NUMBER")


if __name__ == "__main__":
    print(f"Moved {migrate()} memories from older files.")
    print(f"Echo memory ready: {count()} memories saved.")
    print(describe())
