# Agent brain — one shared core, composed per tool

Both AI tools read a flat instruction file. Those files are **generated**, not hand-edited:

| Tool | Reads | Generated from |
|------|-------|----------------|
| Claude Code (and `claude-direct`, `claude-worker`) | `~/.claude/CLAUDE.md` | `WORKING-WITH-SHAAN.core.md` + `estate.md` + `claude.shell.md` |
| Codex | `~/.codex/AGENTS.md` | `WORKING-WITH-SHAAN.core.md` + `estate.md` + `codex.shell.md` |
| omp (`omp-zero`, `omp-worker`) | `~/.omp/agent/AGENTS.md` | `WORKING-WITH-SHAAN.core.md` + `estate.md` + `omp.shell.md` |

`estate.md` is the estate router: which bank, skill or command to use for which job, and where to
write and clean up. `compose-brain.mjs` lints it: every backticked skill must be installed for both
Claude (`~/.claude/skills`) and Codex (`~/.agents/skills` or `~/.codex/skills`), every command must
be on the login PATH, and every path must exist, or `--check` fails. Until 2026-09-23 the Codex
target was `~/.codex/instructions.md`, which native Codex never loaded.

## To change agent behavior
1. Tool-agnostic truth (voice, coding discipline, verification, safety, how Shaan works) → edit **`WORKING-WITH-SHAAN.core.md`**. Propagates to BOTH tools.
2. Claude-only mechanics (Agent tool, herdr, Bifrost routing, boot sequence) → edit **`claude.shell.md`**.
3. Codex-only mechanics (repo setup, Codex sub-agents, transcript paths) → edit **`codex.shell.md`**.
4. Run **`node compose-brain.mjs`**. `--check` = CI dry-run (exit 1 if a target is stale).

Never edit `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md` directly — they carry a GENERATED header and your edit will be overwritten on the next compose.

Budget (4 Oct, Elon pass): each composed file under 4 KB; compose-brain.mjs fails past it. Older versions are in git history.
