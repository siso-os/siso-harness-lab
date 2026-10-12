## Claude Code
- **Context is the cost.** Batch independent calls. Read windows, not whole files. Don't re-read.
- **Delegation (Shaan, 13 Oct):** Opus builds and does heavy reasoning; Haiku 5.5 agents are its arms and legs (skill `haiku-leverage`): they gather context (`scout` code, `librarian` estate, `researcher` web) and run checks (`runner`, `checker`); `editor` only mechanical typing. Opus sub-agents only when justified. No new Codex agents.
- **Task done over ~150k:** update `.agents/HANDOFF.md`, then last action `nohup seat-fresh <seat> --note 'next: …' >/dev/null 2>&1 &` (a new chat). Mid-task: `self-compact`; keep Shaan's latest words, promises, next step, decisions, exact paths/shas, numbers, errors; drop re-readable output.
- **Waiting:** on one event (a background command, a task notification), never a polling loop or timer watcher (11 Oct: one burned a day's budget).
