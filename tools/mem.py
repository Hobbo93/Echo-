"""Claude's project memory tool. Small output on purpose: it saves reading whole files.

  python3 tools/mem.py brief              start-of-session briefing (the hook runs this)
  python3 tools/mem.py search WORDS       best-matching memory notes and code, with file:line
  python3 tools/mem.py where NAME         where a function, class, route or command is defined
  python3 tools/mem.py add FILE TEXT      add a dated note, e.g. add known_errors "symptom → cause → fix"
  python3 tools/mem.py done TEXT          log a finished task in completed_tasks.md
  python3 tools/mem.py checkpoint TEXT [--next "a" "b"] [--objective TEXT]
  python3 tools/mem.py stats              size of each memory file (about 4 characters per token)

The search index (memory/.index.db, git-ignored) is rebuilt automatically when files change.
Standard library only. Refuses to save anything that looks like a password or key.
"""
import ast
import hashlib
import json
import re
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEM = ROOT / "memory"
STATE = MEM / "state.json"
INDEX = MEM / ".index.db"
FILES = ["project_summary", "user_preferences", "architecture", "completed_tasks",
         "active_tasks", "known_errors", "solutions", "decisions"]
SECRET = re.compile(r"(shpat_|shpss_|sk-[A-Za-z0-9]{10}|AKIA[0-9A-Z]{12}|ghp_|github_pat_|xox[bpas]-|"
                    r"-----BEGIN [A-Z ]*PRIVATE KEY|\b\d{8,10}:[A-Za-z0-9_-]{30,}\b|"
                    r"(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*\S{6,})", re.I)
STOP = set("the a an and or of to in on for is are was be it this that with as at by from how what "
           "where when why do does i you we my our".split())


def tokens(text):
    return len(text) // 4


# ------------------------------------------------------------------ index

def _sources():
    files = sorted(MEM.glob("*.md")) + [ROOT / "CLAUDE.md"] + sorted(ROOT.glob("*.py")) + \
        sorted((ROOT / "tests").glob("*.py")) + sorted((ROOT / "tools").glob("*.py")) + sorted(ROOT.glob("*.md"))
    return [f for f in dict.fromkeys(files) if f.exists()]


def _fingerprint(files):
    h = hashlib.sha256()
    for f in files:
        st = f.stat()
        h.update(f"{f}:{st.st_mtime_ns}:{st.st_size}".encode())
    return h.hexdigest()


def _md_chunks(path):
    """One chunk per bullet/paragraph, labelled with its heading."""
    heading, chunk, start, out = "", [], 1, []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    def flush():
        if chunk and "".join(chunk).strip():
            out.append((start, heading, " ".join(s.strip() for s in chunk)))
        chunk.clear()

    for n, line in enumerate(lines, 1):
        if line.startswith("#"):
            flush()
            heading = line.lstrip("# ").strip()
        elif re.match(r"\s*([-*]|\d+\.|\|)\s", line) or not line.strip():
            flush()
            if line.strip():
                chunk.append(line)
                start = n
        else:
            if not chunk:
                start = n
            chunk.append(line)
    flush()
    return out


def _py_chunks(path):
    """One chunk per function/class (name + first docstring line), plus Flask routes and Telegram commands."""
    text = path.read_text(encoding="utf-8", errors="replace")
    out = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = (ast.get_docstring(node) or "").strip().splitlines()
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            out.append((node.lineno, f"{kind} {node.name}", f"{node.name} {doc[0] if doc else ''}"))
    for n, line in enumerate(text.splitlines(), 1):
        m = re.search(r'@app\.route\("([^"]+)"', line)
        if m:
            out.append((n, "route " + m.group(1), "route " + m.group(1)))
        for cmd in re.findall(r'["\'](/[a-z]{3,20})\b', line):
            out.append((n, "command " + cmd, "telegram command " + cmd))
    return out


def ensure_index():
    files = _sources()
    fp = _fingerprint(files)
    db = sqlite3.connect(INDEX)
    db.execute("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
    row = db.execute("SELECT v FROM meta WHERE k='fp'").fetchone()
    if row and row[0] == fp:
        return db
    db.executescript("DROP TABLE IF EXISTS chunks; CREATE VIRTUAL TABLE chunks USING "
                     "fts5(path UNINDEXED, line UNINDEXED, label, body, kind UNINDEXED);")
    for f in files:
        rel = str(f.relative_to(ROOT))
        kind = "memory" if f.parent == MEM or f.name == "CLAUDE.md" else ("code" if f.suffix == ".py" else "doc")
        chunks = _py_chunks(f) if f.suffix == ".py" else _md_chunks(f)
        db.executemany("INSERT INTO chunks VALUES (?,?,?,?,?)",
                       [(rel, ln, label, body, kind) for ln, label, body in chunks])
    db.execute("INSERT OR REPLACE INTO meta VALUES ('fp', ?)", (fp,))
    db.commit()
    return db


def _query(words):
    terms = [w for w in re.findall(r"[A-Za-z0-9_/]+", " ".join(words).lower()) if w not in STOP and len(w) > 1]
    return " OR ".join('"' + t + '"*' for t in terms)


def search(words, limit=10, kind=None):
    q = _query(words)
    if not q:
        return []
    with closing(ensure_index()) as db:
        sql = "SELECT path, line, label, body, kind FROM chunks WHERE chunks MATCH ?"
        args = [q]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY bm25(chunks, 0, 0, 3.0, 1.0) LIMIT ?"
        return db.execute(sql, args + [limit]).fetchall()


# ------------------------------------------------------------------ commands

def cmd_brief():
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    active = (MEM / "active_tasks.md").read_text(encoding="utf-8").splitlines() if (MEM / "active_tasks.md").exists() else []
    tasks = [l for l in active if re.match(r"\d+\.", l)][:5]
    errors = [l for l in (MEM / "known_errors.md").read_text(encoding="utf-8").splitlines()
              if l.startswith("- ")][:6] if (MEM / "known_errors.md").exists() else []
    out = ["# Session briefing (from memory/; search more with: python3 tools/mem.py search WORDS)",
           f"Objective: {s.get('objective', '(none set)')}",
           f"Last checkpoint ({s.get('updated', '?')}): {s.get('checkpoint', '(none)')}",
           "Next: " + "; ".join(s.get("next_actions", [])),
           "Active tasks:", *tasks,
           "Known pitfalls:", *[e[:160] for e in errors]]
    print("\n".join(out))


def cmd_search(args):
    limit = 10
    if "-n" in args:
        i = args.index("-n")
        limit = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    notes = search(args, max(3, limit // 2), "memory")  # decisions and fixes first
    seen = {(r[0], r[1]) for r in notes}
    rows = notes + [r for r in search(args, limit) if (r[0], r[1]) not in seen][:limit - len(notes)]
    if not rows:
        print("No matches. Try other words, or: python3 tools/mem.py where NAME")
    for path, line, label, body, kind in rows:
        print(f"{path}:{line}  [{kind}] {label[:50]} — {body[:180]}")


def cmd_where(args):
    name = args[0] if args else ""
    with closing(ensure_index()) as db:
        rows = db.execute("SELECT path, line, label FROM chunks WHERE kind='code' AND "
                          "(label LIKE ? OR label LIKE ?) ORDER BY path, line LIMIT 30",
                          (f"% {name}", f"% {name}%")).fetchall()
    print("\n".join(f"{p}:{l}  {lab}" for p, l, lab in rows) or f"'{name}' not found.")


def _check_safe(text):
    if SECRET.search(text):
        sys.exit("Refused: that looks like a password, token or key. Memory must never hold secrets.")


def cmd_add(args):
    if len(args) < 2:
        sys.exit("Usage: mem.py add FILE TEXT")
    name = args[0].removesuffix(".md")
    if name not in FILES:
        sys.exit("FILE must be one of: " + ", ".join(FILES))
    text = " ".join(args[1:]).strip()
    _check_safe(text)
    path = MEM / f"{name}.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = f"- {date.today().isoformat()} {text}"
    # Newest-first files get the entry under the header block; others at the end.
    if name == "completed_tasks":
        at = next((i for i, l in enumerate(lines) if l.startswith("- ")), len(lines))
        lines.insert(at, entry)
    else:
        lines.append(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved to memory/{name}.md")


def cmd_checkpoint(args):
    s = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    nxt, obj, words, i = None, None, [], 0
    while i < len(args):
        if args[i] == "--next":
            nxt, i = [], i + 1
            while i < len(args) and not args[i].startswith("--"):
                nxt.append(args[i])
                i += 1
        elif args[i] == "--objective":
            obj, i = args[i + 1], i + 2
        else:
            words.append(args[i])
            i += 1
    _check_safe(" ".join(words + (nxt or []) + [obj or ""]))
    if words:
        s["checkpoint"] = " ".join(words)
    if nxt is not None:
        s["next_actions"] = nxt
    if obj:
        s["objective"] = obj
    s["updated"] = date.today().isoformat()
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Checkpoint saved.")


def cmd_stats():
    total = 0
    for f in [ROOT / "CLAUDE.md"] + sorted(MEM.glob("*.md")) + [STATE]:
        if f.exists():
            t = tokens(f.read_text(encoding="utf-8"))
            total += t
            print(f"{t:6d} tokens  {f.relative_to(ROOT)}")
    print(f"{total:6d} tokens  all memory (loaded only when searched; CLAUDE.md + brief load every session)")


def main(argv):
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "brief":
        cmd_brief()
    elif cmd == "search":
        cmd_search(args)
    elif cmd == "where":
        cmd_where(args)
    elif cmd == "add":
        cmd_add(args)
    elif cmd == "done":
        cmd_add(["completed_tasks"] + args)
    elif cmd == "checkpoint":
        cmd_checkpoint(args)
    elif cmd == "stats":
        cmd_stats()
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
