#!/bin/bash
# Cloud sessions only: install Echo's check tools, then print Claude's memory briefing.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Python packages go in a git-ignored .venv (the system Python's Debian packages block pip).
hashes=.venv/.session-start.sha256
if ! sha256sum --check --status "$hashes" 2>/dev/null; then
  rm -f "$hashes"
  python3 -m venv .venv >&2
  .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements-dev.txt >&2
  sha256sum .claude/hooks/session-start.sh requirements-dev.txt requirements.txt > "$hashes"
fi

# Every command in this session uses the .venv Python.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$PWD/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# Printed text becomes Claude's starting context: a short briefing instead of re-reading files.
.venv/bin/python tools/mem.py brief
