"""One command to check Echo before committing. Exit code 0 = all good.

  python3 tools/check.py          everything
  python3 tools/check.py --fast   skip the test suite

Checks: every .py compiles · pyflakes (if installed) for undefined names and other
real bugs · imports are standard library, Echo's own modules or in requirements ·
no secrets in tracked files · unit tests · memory files stay small enough to load cheaply.
"""
import ast
import py_compile
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import mem  # noqa: E402

# Optional packages Echo imports inside try/except, and what provides them.
OPTIONAL = {"faster_whisper", "av", "piper", "winsound", "winreg", "msvcrt", "playwright", "PIL", "numpy"}
REQ_NAMES = {"flask": "flask", "tzdata": "tzdata", "faster-whisper": "faster_whisper"}
BUDGET = {"CLAUDE.md": 1200, "brief": 900}  # tokens loaded every session
SERIOUS = re.compile(r"undefined name|syntax error|invalid syntax|referenced before assignment|"
                     r"redefinition of unused .* from line|import \* used", re.I)

problems, notes = [], []


def tracked(pattern="*.py"):
    out = subprocess.run(["git", "ls-files", pattern], cwd=ROOT, capture_output=True, text=True).stdout
    return [ROOT / p for p in out.split()]


def check_compile(files):
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True, cfile=str(ROOT / ".check.pyc"))
        except py_compile.PyCompileError as exc:
            problems.append(f"compile: {exc.msg.strip()[:200]}")
    (ROOT / ".check.pyc").unlink(missing_ok=True)


def check_pyflakes(files):
    try:
        import pyflakes  # noqa: F401
    except ImportError:
        notes.append("pyflakes not installed (session hook installs it); skipped static analysis")
        return
    out = subprocess.run([sys.executable, "-m", "pyflakes", *map(str, files)], cwd=ROOT,
                         capture_output=True, text=True).stdout.splitlines()
    serious = [l for l in out if SERIOUS.search(l)]
    problems.extend("pyflakes: " + l.replace(str(ROOT) + "/", "") for l in serious)
    if len(out) > len(serious):
        notes.append(f"pyflakes: {len(out) - len(serious)} minor warnings (unused imports/variables); "
                     f"run python3 -m pyflakes FILE to see them")


def check_imports(files):
    local = {f.stem for f in ROOT.glob("*.py")} | {f.stem for f in (ROOT / "tools").glob("*.py")}
    reqs = set()
    for req in ROOT.glob("requirements*.txt"):
        for line in req.read_text().splitlines():
            name = re.split(r"[<>=\[; ]", line.strip(), maxsplit=1)[0].lower()
            if name and not name.startswith(("#", "-")):
                reqs.add(REQ_NAMES.get(name, name.replace("-", "_")))
    allowed = set(sys.stdlib_module_names) | local | reqs | OPTIONAL | {"pyflakes"}
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else [])
            for n in names:
                top = n.split(".")[0]
                if top not in allowed:
                    problems.append(f"import: {f.relative_to(ROOT)}:{node.lineno} '{top}' is not standard "
                                    f"library or in requirements*.txt")


def check_secrets():
    for f in tracked("*"):
        if not f.is_file() or f.suffix in {".png", ".jpg", ".ico", ".db"} or f.stat().st_size > 2_000_000:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            m = mem.SECRET.search(line)
            # Placeholders and code that *reads* settings are fine; real values look random and long.
            if m and re.search(r"[A-Za-z0-9_\-]{24,}", line) and not re.search(
                    r"YOUR_|EXAMPLE|PLACEHOLDER|_TOKEN\"|getenv|\.get\(|re\.compile|SECRET =", line):
                problems.append(f"secret?: {f.relative_to(ROOT)}:{n} looks like a real key; move it to .echo_telegram.json")


def check_tests():
    if not (ROOT / "tests").exists():
        notes.append("no tests/ folder")
        return
    t = time.time()
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=ROOT, capture_output=True, text=True)
    last = (r.stderr.strip().splitlines() or ["(no output)"])
    summary = next((l for l in last if l.startswith("Ran ")), "")
    if r.returncode:
        problems.append("tests failed:\n" + "\n".join(last[-25:]))
    else:
        notes.append(f"tests: {summary} in {time.time() - t:.1f}s, OK")


def check_memory_budget():
    claude = mem.tokens((ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.cmd_brief()
    brief = mem.tokens(buf.getvalue())
    for name, size in (("CLAUDE.md", claude), ("brief", brief)):
        if size > BUDGET[name]:
            problems.append(f"memory: {name} is ~{size} tokens (budget {BUDGET[name]}); move detail into memory/*.md")
    notes.append(f"memory: CLAUDE.md ~{claude} tokens, session brief ~{brief} tokens")


def main():
    files = [f for f in tracked("*.py") if f.exists()]
    files += [f for f in (ROOT / "tools").glob("*.py") if f not in files]
    files += [f for f in (ROOT / "tests").glob("*.py") if f not in files]
    check_compile(files)
    check_pyflakes(files)
    check_imports(files)
    check_secrets()
    check_memory_budget()
    if "--fast" not in sys.argv:
        check_tests()
    for n in notes:
        print("·", n)
    for p in problems:
        print("✗", p)
    print("✓ all checks passed" if not problems else f"✗ {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
