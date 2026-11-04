# Decisions
Format: date — decision — why.

- 2026-11-04 — Claude's memory lives in the repo (`memory/`, `CLAUDE.md`), not in memory MCP servers — cloud sessions are wiped; only git persists. Memory MCP/community plugins rejected as unverified.
- 2026-11-04 — Search uses SQLite FTS5 (bm25), no embeddings — free, no installs, works on the PC's Python; semantic search not worth the dependencies at this size.
- 2026-11-04 — Echo's three memory stores merged into `echo_memory.py`; old files copied once and kept.
- 2026-11-04 — Phone calls are never summarised mid-call (12 s Twilio limit); the scheduler summarises quiet chats every 30 min.
- 2026-11-04 — YouTube/Instagram/TikTok posting goes through OpusClip's API (accounts already linked there), not separate Google/Meta developer apps.
- Standing — every outside action needs the owner's Yes; no secrets in the repo.
- 2026-11-04 — .claude/ (session hook, agents, permission allowlist) needs the owner's explicit approval — writing Claude's own settings is blocked by the safety check
- 2026-11-04 — Office look = night/dusk neon (owner's reference image, Nov 2026); keep department colours from DEPTS in Office.html
- 2026-11-04 — Echo's self-improvement changes only its talking rules (max 8, unsafe ones filtered) and memory; it never edits its own code or safety rules — keeps the owner in control
- 2026-11-04 — Connection questions are never answered by the LLM; echo_router.answer_connections runs real checks (owner was told 'yes connected' falsely)
