## Claude Code
- **Context is the cost.** Batch independent calls. Read windows, not whole files. Don't re-read what you have.
- **Delegation:** Opus decides; the Haiku 5.5 team (1/40 the price) does the work: `scout` code, `librarian` estate, `researcher` web, `runner` tests, `editor` set edits, `checker` claims (else `model: haiku`). Batch independent asks. Opus sub-agents only when justified (need, budget). No new Codex agents (9 Oct).
- **Task done over ~150k:** update `.agents/HANDOFF.md`, then last action `nohup seat-fresh <seat> --note 'next: …' >/dev/null 2>&1 &` (a new chat). Mid-task: `self-compact`; keep Shaan's latest words, promises, next step, decisions, exact paths/shas, numbers, errors; drop re-readable output.
- **Waiting:** on one event (a background command, a task notification), never a polling loop or timer watcher (11 Oct: one burned a day's budget).
