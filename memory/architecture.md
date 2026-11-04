# Architecture
Plain Python scripts in the repo root, standard library first (+ flask, tzdata). Each part runs
in its own window via `echo_start.py`, wrapped by `echo_keepalive.py` (auto restart).

## Processes
- `echo_server.py`: Flask office + `/api/chat` → `ask_ollama(message, employee, history)`.
- `echo_scheduler.py`: 60 s loop; daily queue, reports 06:30/13:00/17:30, leads 15:00, trade scan,
  CEO summary, ops check, phone check-ins, memory summaries (every 30 min).
- `echo_telegram_chat.py`: Telegram bot; `handle_command()` routes commands before chat.
- `echo_telegram_approved_updater.py`: polls GitHub `main`, installs only after Telegram Yes.
- `echo_phone.py`: Twilio webhooks + Cloudflare tunnel; 12 s reply limit per turn.

## Shared pieces
- Config/secrets: `%USERPROFILE%\.echo_telegram.json` (+ env vars). Read with small `_settings()`/`_cfg()` helpers.
- Approvals: Yes/No over Telegram or phone; pending JSON files per module (e.g. `shopify_pending.json`).
- Memory: `echo_memory.py` (SQLite `echo_memory.db`: `memories` + FTS5 `memories_fts`, `turns`, `meta`).
  `echo_personality.persona(spoken, message)` adds relevant memories to prompts.
- Business data: `%USERPROFILE%\Echo_business\*.json`. Roblox output: `%USERPROFILE%\Echo_roblox\`.
- Status of every integration: `echo_connections.check_all()` (`/connections` on Telegram).

## Integrations
| Service | Module | State |
|---|---|---|
| Ollama | all | required, local |
| Telegram | echo_telegram*.py | built |
| Shopify Admin API (client credentials → 24 h token) | echo_shopify.py | built, owner must add keys |
| Gmail (app password, SMTP) | echo_email.py | built, owner must add keys |
| Alpaca | echo_broker.py | built, paper by default |
| Google Places | echo_leads.py | built, needs key |
| Twilio | echo_phone.py | built, needs account |
| Roblox Studio (local plugin polls 127.0.0.1) | echo_roblox.py | built |
| OpusClip API (Pro plan, beta; YouTube/IG/TikTok linked there) | — | not built yet |
| Base44 | — | via Claude's connector only |
