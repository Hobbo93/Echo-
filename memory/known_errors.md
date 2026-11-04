# Known errors and pitfalls
Format: symptom → cause → fix (date).

- `pip install flask` into system Python fails ("Cannot uninstall blinker … RECORD file not found") → Debian-owned package → use the `.venv` the session hook creates (2026-11-04).
- Playwright screenshot of `Office.html` times out → WebGL is slow in software → launch with `--use-angle=swiftshader --enable-unsafe-swiftshader`, deviceScaleFactor 1, screenshot timeout 120 s (2026-11-04).
- Shopify Manager answers store questions itself, so it's a bad employee for testing `/api/chat` → use "Research Agent" (2026-11-04).
- `plugin:github:github` MCP sometimes fails to connect ("Authorization header is badly formatted"); the main `github` MCP works (2026-11-04).
- Sessions run in fresh containers: anything outside the repo (including ~/.claude memory) is lost.
- 2026-11-04 Small local model (llama3.2 3B) invents facts and claims actions → limited model → echo_growth honesty rules + check_reply note; recommend qwen2.5:7b if the PC can run it
- 2026-11-04 OpusClip social-posting endpoints need the BARE clip id (after the dot in exportable-clips id); project done when GET /clip-projects/{id} stage == COMPLETE (STALLED = failed); API monthly cap returns 403 API_MONTHLY_CAP_REACHED
- 2026-11-04 echo_autostart.bat had a hard-coded test path (Downloads\Echo_fresh_test) and was meant to be copied into Startup → Echo started the wrong copy or nothing → echo_start.install_autostart() writes Startup\Echo.bat from the real folder
- 2026-11-04 Instagram/TikTok/Facebook have no free search without login → owner shares links into Telegram; YouTube search works by parsing ytInitialData from the results page (may break if YouTube changes its page)
