---
name: checkpoint
description: Save progress to Claude's project memory and commit. Use after finishing a significant step, before long or risky work, or when the conversation is getting long.
---
Save where things stand so the next session can carry on without re-explaining.

1. `python3 tools/check.py` — fix or note any failure (don't claim a pass you didn't see).
2. Update memory, briefly:
   - Finished work: `python3 tools/mem.py done "what, where"`
   - New pitfalls: `python3 tools/mem.py add known_errors "symptom → cause → fix"`
   - Reusable recipes: `python3 tools/mem.py add solutions "..."`
   - Decisions: `python3 tools/mem.py add decisions "— decision — why"`
   - Edit `memory/active_tasks.md` (remove done items, add new ones) and `memory/architecture.md` if structure changed.
   - `python3 tools/mem.py checkpoint "where things stand" --next "next step" "after that"`
3. Commit everything with a clear message and push to the session's branch.
4. Tell the owner in one or two plain sentences what was saved.

Never write passwords, tokens or keys into memory (mem.py refuses them).
