# Oracle fleet, 5–6 Sep 2026: where the tokens went, and the rules that fixed it

Written by the Claude Fable pane that coordinated the fleet (Oracle Streaming `default / AGENT ZERO` tab 2), at Shaan's request, so the waste is on the record outside the project. Training data for how SISO uses AI. Facts come from the six seats' own recaps on oracle-streaming main at `4b3cd6384` (`.agents/briefs/unfuck-20260905/recaps/`).

## The numbers

| Window | Seats | Seat-hours | Commits on main | Cause |
|---|---|---|---|---|
| Fri 04:00 → Fri 20:00 | 4 Astra (Bifrost, xhigh) | ~34 | 0 | Codex sandbox denied `.agents` writes and Herdr lookups for 7 h; then read-proof, hash receipts, ACKs, "active-hold" units only a human could release |
| Fri 20:00 → Sat 03:25 | 6 Astra | ~40 | 0 | My landing rule: "lands when verify-4-layers passes". Absolute. Main had 148 pre-existing red test files. Nothing could pass. Every pane said "working". ZERO polled one status command for 2 h 21 m. |
| Sat 03:25 → Sat 06:00 | 6 Astra | ~15 | 44 (36 + 8) | Rule changed to a ratchet (no NEW red test vs main + typecheck/depcruise) and then to no routine reviewer. Token bomb landed and deployed, Operator backend live, 88/119 broken rows closed, 22→11 worktrees. |

Roughly 75 seat-hours of Astra at xhigh produced nothing landable. The last 15 produced everything. The model was the same. The rules changed.

## What wasted it, in order of cost

1. **An absolute gate on a red baseline.** "All tests green" on a repo that is not green is an impossible task that looks like work. Rule: run the gate on main first; if main fails it, the gate is relative to main. (Claude pane's fault.)
2. **Human holds inside an autonomous fleet.** "Active-hold, review by tomorrow" on every lane meant the fleet's output was a queue for Shaan. Rule: the seat that builds it lands it; the only human gate is the real live window.
3. **A reviewer seat for ordinary diffs.** A weaker model (gpt-sol) second-guessing Astra, one round per landing. Rule: no reviewer for ordinary diffs; a fresh-context Astra review only for credentials, tokens, wipe paths, deploy scripts, schema.
4. **Read-proof rituals.** ZERO's transcript is 26 MB, most of it reading 138 JSONLs and hash-matching a corpus before touching code. Rule: one seat (SWEEP) reads everything once and writes one ranked list; nobody else reads the corpus.
5. **Receipt and ACK traffic.** Every unit emitted a handoff, a receipt commit, an evidence folder, an ACK to the coordinator. Rule: a seat writes to its handoff when something material changed and one log line when an outcome lands. Nothing else.
6. **Permissions that did not take.** Codex queue flags do not change effective permissions; only the session `/permissions` UI does. 7 seat-hours lost before anyone checked.
7. **Transport that silently failed.** On the native Codex TUI, Enter does nothing mid-turn and Tab queues; the send wrapper reported FAILED on every delivery. Seats sat idle with a directive in the composer.
8. **Infrastructure the coordinator did not check.** A raw Vite dev server hit 35 GB and kernel-panicked the Mac at 16:33 Fri, killing every seat. Fixed with a memory guard; should have been a guard from the start.

## The rules that worked (now in oracle-streaming `MASTER.md`)

- Landing = typecheck + depcruise green, no new red test vs main, one line from the builder: what it does / deliberately does not do / what breaks if wrong. Then push.
- Seats own outcomes, not units. "Proposal written" is not a terminal state.
- Give the seat the information and what we think, then let it go. Do not script its steps. (Shaan, 6 Sep: "trust the model; a lot of the admin/reviewer stuff is just not trusting the model enough.")
- Reasoning effort: medium by default for all seats; use native Luna sub-agents for bulk read/test work. xhigh was not what made the difference.
- Checkpoint on disk before any restart: the seat's own recap (asked / delivered with SHAs / wasted / open / undocumented), so a fresh context resumes from main alone.

## Instrumentation that would have caught it earlier

Per hour, three numbers: commits on main, deploys receipted, ranked rows closed. Flat for an hour = the rule is wrong, not the seat. Pane status is not a signal.
