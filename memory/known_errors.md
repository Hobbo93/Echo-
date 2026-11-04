# Known errors and pitfalls
Format: symptom → cause → fix (date).

- `pip install flask` into system Python fails ("Cannot uninstall blinker … RECORD file not found") → Debian-owned package → use the `.venv` the session hook creates (2026-11-04).
- Playwright screenshot of `Office.html` times out → WebGL is slow in software → launch with `--use-angle=swiftshader --enable-unsafe-swiftshader`, deviceScaleFactor 1, screenshot timeout 120 s (2026-11-04).
- Shopify Manager answers store questions itself, so it's a bad employee for testing `/api/chat` → use "Research Agent" (2026-11-04).
- `plugin:github:github` MCP sometimes fails to connect ("Authorization header is badly formatted"); the main `github` MCP works (2026-11-04).
- Sessions run in fresh containers: anything outside the repo (including ~/.claude memory) is lost.
- 2026-11-04 Small local model (llama3.2 3B) invents facts and claims actions → limited model → echo_growth honesty rules + check_reply note; recommend qwen2.5:7b if the PC can run it
