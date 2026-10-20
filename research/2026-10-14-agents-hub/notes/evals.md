# Evals slice notes (2026-10-14)

Rows: `rows/evals.jsonl`, 29 rows (evals-001 to evals-029). Budget used: about 30 tool calls (6 search batches, 2 fetch batches, 1 write).

## How the boards were checked
- Searches were run for every named benchmark. Most leaderboards are client-rendered or blocked, so most numbers come from search snippets and third-party mirrors (BenchLM, Steel.dev, DataLearner, Codesota, anotherwrapper). Those rows say so in `note`.
- Fetched directly: `metr.org/time-horizons/` (chart values not rendered; page says it is no longer actively updated), `hal.cs.princeton.edu/about` (no columns or archive status on the page), `swebench.com/bash-only.html` (HTTP 404 at fetch time).
- Not reached: tbench.ai, artificialanalysis.ai, livecodebench.github.io, os-world.github.io, webarena.dev, mcp-universe.github.io, vals.ai boards, epoch.ai boards, lmarena leaderboard, scale.com board, gorilla leaderboard (client-rendered).

## Harness vs model
Boards that compare harnesses, not just models: Terminal-Bench (agent + model rows), Artificial Analysis Coding Agent Index (products), HAL (agents, cost axis), SWE-bench Bash Only (same loop for all models, a control), GAIA and BrowseComp (leaders are systems), WebArena (scaffold recorded), SkillsBench (skills as a component). Model-only in practice: BFCL, METR, Aider polyglot, LiveCodeBench.

## Strongest finds
1. HAL (hal.cs.princeton.edu): the only board that makes cost and accuracy the default axes and treats the agent as the unit. Its archive status is unclear, so check GitHub first.
2. Terminal-Bench plus AA Coding Agent Index: rows are explicitly harness + model, with same-model-across-harness comparisons possible.
3. SWE-bench Bash Only plus Scale SWE-bench Pro: a fixed-loop control and a standardized-tooling board. Scale's numbers read lower than vendor claims, a useful check on harness inflation.

## Warnings for the write-up
- Mirrors disagree on leaders for tau2, OSWorld, TB, AA index, LiveCodeBench, MCPMark. Do not quote an aggregator as the board.
- METR says it is no longer actively updated, and its own page says numbers above 16 h are unreliable.
- Multiple "KernelBench" and "SkillsBench" boards exist; the rows name which one is meant.
- Recursion: no leaderboard was found. Recursion Pharmaceuticals has no agent board; Labelbox's "Recursion" platform has no public board. The closest is AI4AI-Bench (arXiv 2608.20318, a paper, out of scope). Left out of the rows.
- Arcade's "SkillBench" (skill-quality grading of about 39k skills) is a different thing from SkillsBench. Not a row.

## Missing / next
- Live numbers from the official boards (tbench.ai, artificialanalysis.ai, scale.com, lmarena, vals.ai, os-world.github.io). A browser or steel.dev `.md` mirror pass would fill most gaps.
- SWE-bench Multimodal and Bash Only current top entries were not confirmed.
- No board found for Context Arena's official site. Check whether the DataLearner page is the only index.
