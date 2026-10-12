# Improvement system — verified connections, 8 September 2026

The intended system improves the quality and usefulness of agent output, including
better outcomes at the same token cost. It spans history, judgment, experiments,
skills, execution and a readable front door. The pieces exist at different levels
of completion; a relationship in a catalog is not an implemented data connection.

| Component | Existing owner / entry point | Verified state |
| --- | --- | --- |
| Improvement project | Harness Lab `.agents/PAGE.md`, STATE, BACKLOG | Private durable repo, read-only local front page/JSON status, executable offline loop and regression tests; PR #1 merged into private main |
| Original conversation evidence | Private Source/recall and Session Intelligence; source-linked reports here | Existing private inputs and retrieval work; exact-locator provenance verification now works on demand, without copying raw text; no automatic ingestion |
| Judgment and experiment selection | Assigned Astra/Web UI owner, `docs/IMPROVEMENT-LOOP.md` | Agent-driven; must inspect actual requests, work and counterexamples; no background model daemon |
| Output/decision evaluation | `scripts/efficiency-loop.mjs`, `scripts/grade-outcome.mjs` | Diagnostic-preservation fixture, decision-response grader, exclusive reservation/publication and qualified owner review; none proves fleet benefit |
| Reusable behavior | Existing Skills Hub / Playbook source and install workflow | `bounded-tool-output` and `trace-to-regression` were installed previously; P6 projection repaired by Internal; no automatic experiment-to-skill promotion |
| Web UI repository work | `docs/WEB-UI-PICKUP.md` and private GitHub access | Portable assignment exists; actual model-backed acceptance is a separate test |
| ChatGPT → machines | Existing SISO Workspace / DevSpace bridge | Prior gateway/MCP tests passed; prior ChatGPT connection acceptance was blocked/unverified |
| Codex → visible ChatGPT | Installed `codex-chatgpt-control` | Current session cannot obtain extension browser after bootstrap; no visible evaluation submitted |
| Human-readable Library front door | Library Work `gls:work:1cc4c944-9351-466e-a442-9fe16ad145d1` | Local Library preview verified at port8974 with the exact Work ID; PR #21 remains open and public publication is not verified |

The Library proposal is
[PR #21](https://github.com/sisodias/great-library-of-siso/pull/21), branch
`feat/harness-lab-library-20260906`, at `c87c6a8` when inspected. It already contains
`site/works/siso-harness-lab/index.html` and a Work linking efficiency research,
Skills Hub and Session Intelligence. Those links are explicitly contextual;
the PR does not implement a shared queue, transcript ingestion, worker execution
or skill installation. The public route returned HTTP 403 to this session, which
does not establish that the page is missing. Publication belongs to the existing
Library owner; do not create another registry or edit its active source in parallel.

The private project front door is already available on
[the Harness Lab branch](https://github.com/sisodias/siso-harness-lab/blob/main/.agents/PAGE.md).
Library should link that existing project, not publish private conversation data.

## The cycle that still needs end-to-end evidence

1. Retrieve a bounded original task and its result from the existing private source.
2. Identify an actual decision/delivery failure, or a strong reusable success.
3. Freeze task acceptance and compare one proposed mechanism with a baseline.
4. Measure quality and total effort; retain failed/no-gain candidates.
5. Promote a useful change through its actual owning source, then test a new task.
6. Record the result and next experiment here; expose public-safe status through Library.

This repo supports the evidence and continuation steps. The assigned agent joins
them today; an automatically connected cross-tool improvement service has not
been demonstrated. The next trial tests unnecessary coordinator holds and the
cost/benefit of one extra instruction. There is no new scheduler, agent swarm,
global install or claim of tenfold improvement.

## Executable local entry

Run `npm run project:status` for the same JSON evidence used by
`npm run project:serve` at the private local URL `http://127.0.0.1:8947`.
The API is read-only, binds loopback, and does not serve arbitrary files.
Changed inputs/responses invalidate prior reviews; changed implementation
source invalidates its passing badge. The Library owner has the public-safe
`.agents/public-entry.json`; localhost is retained only in private handoffs.

For the four captured evaluator attempts, run
`npm run evidence:verify -- reports/2026-09-08-outcome-quality/provenance.json`.
This verifies exact source hashes, project/thread identity, recorded launch
source/provider/model/effort and deduplicated usage without returning chat text.
Missing private files return unavailable (exit2), not a passing zero-cost record.
It does not replace the Source/Session Intelligence ingestion owner.
