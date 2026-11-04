# Claude's setup for this repo

- `hooks/session-start.sh`: at the start of each cloud session, installs the check tools into `.venv`
  and prints the memory briefing (`tools/mem.py brief`).
- `agents/`: `explorer` (cheap, fast code lookup), `reviewer` (checks changes against Echo's rules), `tester`.
- `skills/checkpoint/`: `/checkpoint` saves progress to `memory/` and commits.

The hook only runs once `.claude/settings.json` exists with this content (Claude isn't allowed to
write that file itself, so the owner adds it):

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh" } ] }
    ]
  },
  "permissions": {
    "allow": [
      "Bash(python3 tools/mem.py:*)",
      "Bash(python3 tools/check.py:*)",
      "Bash(python3 -m unittest:*)"
    ]
  }
}
```
