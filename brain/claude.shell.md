## Claude Code
- **Context is the cost.** Batch reads into one Bash call (`rr 'a' 'b'`). Read windows, not whole files. Don't re-read.
- **Delegation (Shaan, 16-20 Oct):** seats run `claude-sonnet-5-5`, Opus only with a written reason. Reads and checks: Haiku 5.5 (`scout`, `runner`, ...). Builds: Codex `gpt-6.1-sol` (`delegate_task`), one bounded non-UI job each, own worktree, 3/seat, 8 fleet-wide; read its diff, rerun its check before merge. No Sonnet builders (20 Oct): fallback is Haiku 5.5. Skill `haiku-leverage`.
- **Task done over ~150k:** update `.agents/HANDOFF.md`, then last action `nohup seat-fresh <seat> --note 'next: …' >/dev/null 2>&1 &` (a new chat). Mid-task: `self-compact`; keep his words, promises, next step, decisions, paths/shas, errors.
- **Commands:** over ~1 min, `run_in_background` and do the next step; send independent calls together. Wait on that one event, never a poll loop. A PR: `watch_pull_request`, end the turn; never end a turn waiting with no wake set.
- **Tasks:** 3+ steps in `TaskCreate`/`TaskUpdate` (Shaan sees them)
