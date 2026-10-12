# Cold-start prompt

Paste this into any fresh agent (Claude Code, Codex, a future model) to put it on this project:

```
You are picking up the SISO Harness Lab: the long-running project to make Shaan's Claude Code and Codex agent setup produce more useful work per token. Nothing is in your context; everything is on disk.

Read, in order:
1. ~/SISO_Workspace/SISO_Agents/siso-harness-lab/AGENTS.md
2. STATE.md (same dir; newest entry wins)
3. BACKLOG.md; take the top item that is not blocked on Shaan
4. DECISIONS.md; these are rulings, not suggestions
5. docs/method.md; measure before, change, probe, measure after

Then post one console card (~/.claude/console/bin/console-post -a harness-lab -k card) naming the item you took, and work it. Close out per AGENTS.md § Close-out: STATE.md entry, backlog row moved to Done with numbers, commit this repo, console card. Never commit ~/.claude.
```
