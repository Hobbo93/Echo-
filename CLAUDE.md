# Echo — notes for Claude

Echo is a personal AI "company" that runs on the owner's Windows PC (Adelaide, Australia).
15 AI employees answer through a local Ollama model (`llama3.2`), shown in a 3D office
(`Office.html`, served by `echo_server.py` at http://127.0.0.1:5000), on Telegram and by phone.
The owner usually works from an iPhone and is not a programmer: explain things simply.

Read `docs/PROGRESS.md` before starting work, and update it when you finish.

## Hard rules
- Echo must never trade, publish, spend money, send email or contact anyone without the
  owner tapping Yes (Telegram or phone). Keep every new action behind `echo_approvals` /
  the existing Yes/No flows.
- Never put API keys or tokens in the repo. Secrets live on the PC in
  `%USERPROFILE%\.echo_telegram.json` (read via `_settings()`-style helpers) or env vars.
- Python standard library first. Only `flask` and `tzdata` are required
  (`requirements.txt`); voice extras are in `requirements-voice.txt`.
- Code runs on Windows (`py`, `.bat` launchers): use `pathlib`, UTF-8, no Unix-only calls.
- The PC installs updates from the `main` branch only, after the owner approves on Telegram
  (`echo_telegram_approved_updater.py`). Work on feature branches; merging to main ships it.
- Runtime data files (`echo_*.db`, `echo_*.json` state, `content_*`) are gitignored. Never commit them.

## Where things are
| Area | Files |
|---|---|
| Office server + chat API | `echo_server.py` (`/api/chat`, `ask_ollama`), `Office.html` |
| Employees (names, roles, rules) | `echo_employees.py` (`EMPLOYEES`, all on `llama3.2`) |
| Memory (shared by everything) | `echo_memory.py` (SQLite + full-text search, chat summaries) |
| Personality, mood, "remember that…" | `echo_personality.py` (`persona(spoken, message)`) |
| Telegram chat + commands | `echo_telegram_chat.py` (`handle_command`), `echo_telegram.py` |
| Phone (Twilio) | `echo_phone.py` |
| Daily schedule + reports | `echo_scheduler.py`, `echo_tasks.py`, `echo_automation.py` |
| Approvals | `echo_approvals.py` |
| Shopify (store Furventure, `thedogden-2.myshopify.com`) | `echo_shopify.py`, `SHOPIFY_SETUP.md` |
| Trading (Alpaca, paper by default) | `echo_trading.py`, `echo_broker.py`, `echo_chart.py` |
| Sales/finance/support/CEO | `echo_business.py` |
| Leads, email, content, Roblox, photos, voice | `echo_leads.py`, `echo_email.py`, `echo_content.py`, `echo_roblox.py`, `echo_photos.py`, `echo_voice.py` |
| Setup and health | `echo_setup.py`, `echo_preflight.py`, `echo_connections.py`, `*.bat`, `*_SETUP.md` |

## Checking work
- Tests: `python -m unittest discover tests`
- Compile everything: `python -m py_compile *.py`
- Ollama, Telegram, Twilio and Shopify are not reachable from cloud sessions: fake
  `urllib.request.urlopen` in tests instead of calling them.

## Working efficiently
- Search with Grep for the function you need instead of reading whole files; the big files
  are `echo_trading.py`, `echo_server.py`, `echo_roblox.py`, `echo_business.py`, `Office.html`.
- Keep this file short. Put history and decisions in `docs/PROGRESS.md`.
