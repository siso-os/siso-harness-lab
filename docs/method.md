# Method: how work is done and proven here

## The instruments

| Instrument | What it measures | How |
|---|---|---|
| `scripts/probe-turn1.sh <dir> <label>` | Turn-1 context of a Claude Code session in a directory (input + cache_creation + cache_read from the first usage line). Deterministic across runs. | `claude -p --max-turns 1 --output-format stream-json --verbose 'Reply with exactly: OK'` |
| `scripts/audit.py OUT.json [DAYS]` | Transcript audit over `~/.claude/projects/*/*.jsonl`: context per turn, single-tool turns, subagent return lengths, correction-shaped prompts, hook-denied re-sends, polling, model routing. ~1.2 GB, minutes. | Also wrapped as `~/.claude/console/bin/console-audit [DAYS]`, which posts the headline to the console. On demand only. |
| Hook probe | Feed a realistic stdin payload to a hook and read stdout. | `echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' \| node ~/.claude/hooks/X.mjs`. Put payloads in a file when the command text itself would trip the safety guard. |
| Scratch console | End-to-end test of console producer/consumer without touching the live one. | `CONSOLE_HOME=<scratch> CONSOLE_PORT=9151 node ~/.claude/console/server.mjs`, then curl `/post` and `/answer`, then `ls <scratch>/state/inbox`. |
| Rollout attribution | Which model a Codex session ran. | `turn_context.payload.model` in the rollout JSONL. Never grep prose for a model name. |

## What counts as proof

- A before and after number from the same instrument, or a probe whose output is quoted.
- For a producer/consumer pair (hook writes, hook reads; server writes, script polls): run
  both halves and list the files that actually exist. One-sided checks passed for weeks on
  two real bugs.
- For a routing or safety hook: probe every alias and every intent (work vs review; real
  dangerous command vs the same text inside quotes or a heredoc).
- For a "dead" verdict on a file, skill, or hook: read it, then check callers and the
  registry (`~/.claude/settings.json` is authoritative for hooks; files in `hooks/` are
  inert unless registered). Names, timestamps, and `retired` markers are claims.
- BLOCKED (could not observe) is reported as BLOCKED, never as FAIL or PASS.

## Working pattern

1. Read `STATE.md`, take the top unblocked `BACKLOG.md` item, post a console card.
2. Measure the baseline with the instrument the item names.
3. Back up, change, append the manifest line.
4. Probe: positive case, negative case, one malformed case.
5. Re-measure. Write the numbers into the backlog item and `STATE.md`.
6. If a worker is needed: brief in a file, read-only unless stated, `RETURN` block capped at
   ~200 words with STATUS/CHANGED/VERIFY/EVIDENCE. Diff any file it touched before accepting.
7. Commit this repo. Never commit `~/.claude`.

## Layout of the setup being tuned

| Thing | Path |
|---|---|
| Hook registry (authoritative) | `~/.claude/settings.json` |
| Hook scripts | `~/.claude/hooks/`, `~/.claude/console/bin/` |
| Global skills / agents | `~/.claude/skills/` (12), `~/.claude/agents/` (gpt-luna, gpt-sol) |
| Brain (source of CLAUDE.md) | `~/SISO_Workspace/SISO_Agents/siso-harness-lab/brain/` → `node compose-brain.mjs` |
| Console | `~/.claude/console/` (server.mjs, bin/, state/), http://127.0.0.1:8891 |
| Memory | `~/.claude/projects/-Users-shaansisodia/memory/` + `MEMORY.md` index |
| Codex | `~/.codex/` (config.toml, instructions.md, AGENTS.md, skills/, fable*.config.toml) |
| Restore manifests | `~/.claude/backups/<run>/MANIFEST.txt` (copied into `reports/<run>/RESTORE-MANIFEST.txt` at close-out) |
| Lessons | `~/.claude/lessons/LEDGER.md` (one line per mistake) |
| Launchers | `~/bin/claude-direct` (gateway-free, Shaan's settings), `~/bin/claude-phone` (isolated profile for channels), `~/bin/codex-fable` |
