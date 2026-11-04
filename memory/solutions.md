# Reusable solutions
- **Test Flask routes without Ollama:** import `echo_server`, replace `echo_server.urllib.request.urlopen` with a fake returning `{"message":{"content":"..."}}`, use `app.test_client()`.
- **Test memory without touching real data:** point `echo_memory.DB_PATH` (and `OLD_*` paths) at a temp folder; pass `ask=` to `summarise_channel`.
- **Screenshot the office:** run `echo_server.py` with HOME set to a scratch folder, then Playwright on http://127.0.0.1:5000 (see known_errors.md for flags).
- **Long work in the background on the PC:** add a `run_*` step to `run_daily_schedule()` in `echo_scheduler.py`, rate-limited with a module-level timestamp.
- **New Telegram command:** add a branch in `handle_command()` before the "remember that" handler, and a line in the help text.
- 2026-11-04 **Research without API keys:** Google News RSS (news.google.com/rss/search?q=...&hl=en-AU&gl=AU&ceid=AU:en) + Wikipedia search API; see echo_growth.fetch_sources
- 2026-11-04 **Free business data:** Overpass API (overpass.private.coffee works; overpass-api.de often resets) — query nwr[shop|amenity|craft][name] in a small bbox; skip elements with brand* tags (chains)
