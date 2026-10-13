# SISO Harness Lab: how every agent works, and what it costs

**In one line:** the agent-stack project. It makes Shaan's Claude Code (and Codex) seats do more useful work per plan
token: Opus builds and reasons; the Haiku 5.5 agents gather its context and run its checks (Shaan, 13 Oct). District `SISO_Agents`, GitHub sisodias/siso-harness-lab.

| Door | |
|---|---|
| Owner | the HARNESS seat (Agent Base > Harness, since 12 Oct); Agent Zero changes it through jobs otherwise |
| State | `.agents/HANDOFF.md` (newest first); durable facts `.agents/memory/MEMORY.md` (one file each + an index line) |
| Runs | `.agents/runs/<date>-<subject>/` (current: `2026-10-12-harness/`: PLAN.md, ROUND6.md, bench and baselines) |
| Tests | `npm test` (some suites for other tools fail already; run your own file with `node --test tests/<x>.test.mjs`) |
| Worktrees | this repo: `_data/worktrees/siso-harness-lab/<lane>`; Agent Base: `_data/worktrees/siso-internal-labs-agent-base/harness-<lane>` off origin/main, landed by PR |
| Elsewhere | `estate where <words>`; the map is `~/SISO_Workspace/AGENTS.md` |

## What lives here
- **The brain:** `brain/` composes `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.omp/agent/AGENTS.md`
  (`node brain/compose-brain.mjs`; `--check` enforces byte budgets and that every routed skill and path exists). Edit the
  source, never the output.
- **Hooks** (`hooks/`, registered in both `~/.claude/settings.json` and `~/.config/claude-siso-3/settings.json`):
  fetch-nudge (3rd read in a row -> hand it to scout; the 4th is turned back once), test-filter (test runs show the end, or the failures; full log
  to a file), read-gate (first whole read of a >=32 KB file -> window, grep or scout), after-compact (git + HANDOFF
  after a compaction), context-ping (informing pings by context size; a finished task over 150k is pointed at
  A0's `seat-fresh`: HANDOFF, then a new conversation), spend-glance, estate-guard. Each has an off
  switch in its header and a test in `tests/`.
- **Instruments** (`scripts/`): `token-where.py` (where plan tokens go; headline $ per Shaan request, Opus fetch-loop
  share), `injection-cost.py` (what reminders, hooks and listings cost), `usage-tasks.py` (cost per seat and per task, waste named; Agent Base's Usage page serves it via /api/usage/tasks), `compact-window-sim.py`, `cache-ttl-sim.py`,
  `harness-bench.py` (real tasks across models/configs, graded by hand), `stack-page.py --post` (the page:
  http://127.0.0.1:8891/card/agent-stack/html).
- **Commands** (`bin/`): the launchers (`claude-siso`, `claude-siso-3`, `claude-move`, ...), `self-compact`, `heavy`,
  `tsc-inc`, `shot`, `spend-ledger`, `codex-run`, `dev-lease`.
- **The seat side** lives in Agent Base: `services/host/src/host.ts` (query() options: model, effort, env, lean,
  advisor, compaction 33%, carry on after compaction) and `stack/plugin/agents/` (the Haiku team: scout, librarian,
  researcher, runner, editor, checker; Opus roles specker, worker, reviewer). Seats run the host from the main
  checkout; `tools/ab-live` deploys it with `tools/ab-host-sync`, and a seat gets it when it next starts.

## Rules that hold here
- **Measure, change, measure.** Every change carries a before/after number from the instruments above or a live run
  with its output. A green syntax check is not evidence. Attribute by the model field, never by substring.
- **Every change under `~/.claude`, `~/.codex` or the brain is restorable:** copy to `~/.claude/backups/<run>/` and add a
  `MANIFEST.txt` line first; settings changes go in both config dirs. Never commit `~/.claude`.
- **Hooks never block work.** No hook forces or blocks compaction on size (informing pings only); hooks fail open and
  print nothing on error. Nothing scheduled, no watchers (DECISIONS.md).
- **Run both halves.** Verify a producer/consumer pair by running both and listing what is on disk.
- **Others' work:** `.agents/HANDOFF.md` and many files here carry other agents' uncommitted edits. Stage only your
  own hunks (`git add -p`, or `git hash-object -w` + `git update-index --cacheinfo`); never open a shared file for
  writing before reading it.

## Close-out
Prepend a dated line to your entry in `.agents/HANDOFF.md`, tick the run's checklist, commit only your files with a
message naming the run, and post a card (`console-post`) when Shaan should look.
