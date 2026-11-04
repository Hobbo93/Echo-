# Echo progress log

Newest first. Claude adds an entry at the end of each piece of work: what changed,
decisions made, and what is next.

## 2026-11-04: Shared memory and Claude project notes
- **Done:** `echo_memory.py` is now Echo's single memory (SQLite with full-text search).
  - "remember that…" facts, the old `~/.echo_personality.json` facts and the old
    `~/.echo_memory.json` notes all live there (copied in once, old files kept).
  - Telegram, phone and every office employee add only the memories that match each
    message to the prompt, instead of a fixed list.
  - Every chat is saved. After 20 messages, or once a chat goes quiet (the scheduler
    checks every 30 min), the local model writes a short summary that becomes a memory.
    Telegram starts from the last summary after a restart. Phone calls are summarised
    after they end, never during.
  - New Telegram commands: `/memories`, `/forget NUMBER`.
  - `Echo_upgrades.py` is now a thin wrapper around `echo_memory.py`.
- **Done:** `CLAUDE.md` and this log, so Claude doesn't need the project re-explained.
- **Waiting on the owner:** connect Shopify on the PC (`SHOPIFY_SETUP.md`, `connect_echo.bat`).

## Upgrade plan (agreed list, not yet approved unless marked done)
1. ✅ Claude project notes (`CLAUDE.md`, `docs/PROGRESS.md`)
2. Automated tests + GitHub Actions + session-start check
3. ✅ Shared Echo memory with search and summaries
4. Official Anthropic plugins: `code-review`, `frontend-design`
5. Employees that delegate tasks to each other + smaller model for simple jobs
