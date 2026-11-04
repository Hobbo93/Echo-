# Echo: notes for Claude

Echo is a personal AI "company" on the owner's Windows PC: 15 AI employees on local Ollama,
reached through a 3D office, Telegram and phone. Details: `memory/project_summary.md`,
`memory/architecture.md`. The owner works from an iPhone and isn't a programmer: reply
short, plain English, outcome first (`memory/user_preferences.md`).

## Start of every session
1. Run `python3 tools/mem.py brief` (objective, last checkpoint, active tasks, pitfalls).
2. Continue from the checkpoint. Don't redo anything in `memory/completed_tasks.md`.
3. Before touching an area, `python3 tools/mem.py search WORDS` for past decisions, errors and fixes.

## Memory (the repo is the only thing that survives a cloud session)
- `memory/*.md` = human-readable notes; `memory/state.json` = objective + checkpoint.
- After each significant step: `python3 tools/mem.py checkpoint "what's done" --next "a" "b"`.
- Log with `python3 tools/mem.py add FILE "text"`: `known_errors` (symptom → cause → fix),
  `solutions` (reusable recipe), `decisions` (decision — why), `done "task"` for finished work.
  Edit `active_tasks.md` / `architecture.md` directly when they change.
- Never store passwords, tokens or keys anywhere in the repo (mem.py refuses them).
- Save a checkpoint before long work and whenever the conversation is getting long.

## Making changes
1. Find code with `python3 tools/mem.py where NAME` or Grep; read only the lines you need.
2. Check who calls what you change (Grep the function name).
3. Commit before risky edits (rollback point). Undo with `git revert <sha>`, never force-push main.
4. Make targeted edits; add or update a test in `tests/` (fake `urllib.request.urlopen`;
   Ollama, Telegram, Twilio and Shopify can't be reached from the cloud).
5. Run `python3 tools/check.py` (compile, pyflakes, imports, secret scan, tests, memory size).
   Never say tests passed unless they ran. GitHub Actions runs the same check on every push.
6. Update memory, commit with a clear message, push to the session's branch.

## Hard rules for Echo's code
- Every outside action (trade, post, email, spend, contact) waits for the owner's Yes on Telegram/phone.
- Secrets only in `%USERPROFILE%\.echo_telegram.json` or env vars, never in the repo.
- Standard library first; runtime deps are only `requirements.txt` (flask, tzdata).
- Windows paths and `.bat` launchers: use `pathlib`, UTF-8.
- The PC installs updates from `main` only, after the owner approves; merging to main ships it.
- Runtime data (`echo_*.db`, state JSON, `content_*`) is gitignored; never commit it.

## Saving tokens
- Don't read whole big files (`echo_trading.py`, `echo_server.py`, `echo_roblox.py`,
  `echo_business.py`, `Office.html`); search, then read a line range.
- Don't re-read a file you've already read this session unless it changed.
- Hand broad searches to the Explore agent (its result comes back short); do small lookups yourself.
- Keep this file under ~1,200 tokens (`check.py` enforces it); detail belongs in `memory/`.
