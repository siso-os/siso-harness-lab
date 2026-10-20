# tokens/: TOKENS, the token tracker

Owner: the TOKENS seat (Agent Infrastructure, beside ESTATE and CAMS-LAPTOP). Shaan, 14 Oct: "track like where all
our tokens went ... in 24 hours we spend 30% of our weekly plan".

| File | |
|---|---|
| `ledger.py` | The one script. `python3 tokens/ledger.py --hours 24` = by seat, main vs sub, model, login, top sessions, context size, hour, waste. `--day D`, `--json OUT`, `--daily` (a day into LEDGER.md). Counts only, never message text. |
| `LEDGER.md` | One line per day, written on demand (`ledger.py --daily --day D`); nothing scheduled (Shaan, 14 Oct). History in `data/daily.jsonl`. |
| `fill.py` | What fills an Opus context, by block type and tool. |
| `loops.py` | Were the Opus reads needed: read-only calls by kind, single vs batched, runs of 3+, and the batch / Haiku counterfactuals. |
| `FINDINGS.md` | The biggest wastes, each with its number and the fix; lines for other owners go through Agent Zero. |
| `HANDOFF.md` | Where the work stands, newest first. |

Rules: measure with scripts, not tokens (TOKENS must be the cheapest seat). Run heavy jobs as `heavy -- ...`.
Prices come from `scripts/token-where.py` RATES; seat names from `~/.local/state/agent-base/t3-seats.json`, SISO Code
`statev2.sqlite` and Agent Base host records; a name in brackets is the repo folder when no seat is known.
`~/.claude-siso/projects` links to `~/.claude/projects`, so fuzeheritage and the default login are one row.
