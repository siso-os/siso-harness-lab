# The recursive efficiency-improvement loop

September8 budget override: `.agents/EFFICIENCY-RESET-20260908.md` and the current
handoff take precedence. Use existing evidence first; no automatic replay, worker
allocation or fresh experiment merely to complete this historical cycle checklist.

The optimizing agent is the assigned Web UI/Codex/Claude session. This repository
is its durable project base and executable experiment ledger. It is not a model
trainer or a daemon that can run without an agent. The loop can improve its own
measurement and operating rules, but the same evidence gates apply to those edits.

## What efficiency means

The objective is useful, accepted output per unit of total effort. A win can be
the same accepted outcome for fewer tokens, or a materially better outcome for
comparable tokens. Lower token use with worse work is a rejection. More valuable
work at the same cost is a valid improvement even when no token count falls.
The user's 10x target is an ambition, not a score to manufacture.

Before a comparison, define task-specific acceptance: user intent preserved,
correct behavior, relevant completeness, and any required safety/quality checks.
Judge the actual deliverable against that rubric. Commits, response length, green
tests and tool-output bytes cannot stand in for outcome value. Include the parent,
workers, retries, review and rework in cost; unknown usage remains unknown.

Candidates may add, remove or narrow instructions/skills, improve evidence
retrieval, change task decomposition, or use bounded workers where that helps.
Do not presume more instructions or more delegation improves the result. Keep
consequential judgment with the owner and test one mechanism at a time.

## One cycle

1. Read `loop:next` and the referenced backlog/evidence only. Select a concrete
   failure, not a hypothetical best practice. Write the claim and write fence in
   the existing handoff before editing shared sources.
2. Reproduce the failure. Separate cached/uncached input, output, elapsed time,
   retries and accepted outcome. Missing measurements are unknown, not zero.
3. Change one causal mechanism. Reuse the existing owner/source: Skills Hub for
   skills, harness code for transport failures, project-local facts locally.
4. Test the original failure, a neighboring case that must still work, malformed
   input, and a held-out case not used to design the change. Required evidence and
   safety must survive. Fewer characters without correctness is a rejection.
5. Run `npm test` and `loop:cycle`. The runner records source fingerprints,
   per-case before/after sizes, checks and its predecessor; identical inputs do
   not create repeated success records. Results are immutable and single-writer.
6. Write the lesson, limits, rollback and next experiment into the existing
   STATE/HANDOFF/BACKLOG surfaces. Commit the exact verified changes. Continue
   with the next unblocked experiment within the assigned session budget.

No status-polling loop. No new evidence or candidate means no repeated measurement
claim: select a different existing unblocked problem or stop with the missing
input. Rejected candidates stay recorded. Do not optimize a benchmark by removing
failing cases or revising completed receipts. Keep fresh hold-outs for later work;
the committed seed hold-out becomes known after its first inspection.

## First executable experiment

`experiments/output-retrieval.json` and `scripts/output-policies.mjs` compare a
full diagnostic payload, a naive 4,096-character cut and a structured projection.
The unit is UTF-8 bytes/characters, **not model tokens**. One fixture places the
failure after the cut; another includes image data; another needs producer exit
status. This guards against calling blind truncation an efficiency win.

`loop:cycle` writes a unique JSON receipt under `reports/efficiency-loop/` with
`promotion: fixture_only`. It never edits global settings or installs a skill.
`loop:check` recomputes the current suite without writing. `loop:next` is read-only.
Fixtures are sanitized synthetic examples; real paired agent behavior is the next
gate, not implied by passing fixtures. Existing report findings are evidence leads,
not automatic permission to apply the eight older proposals.

## Outcome-quality trial

`experiments/owner-continuation-cases.json` is a separate bounded decision trial
derived from the September 5 coordinator failure: a request for explanation
became an unnecessary hold on existing owners. Frozen baseline/candidate briefs
live in `reports/2026-09-08-outcome-quality/`. They differ by one small instruction;
neither authorizes live actions. Independent visible evaluations must use the
same verified model/effort and isolated contexts. No self-spawn is implied.

`npm run outcome:grade -- RESPONSE.json` checks every required decision against
the frozen rubric and rejects missing/duplicate cases and broken stop boundaries.
It measures decision-response correctness, not completed project work. Report
actual usage separately; a single pair does not establish a model ranking or
fleet multiplier. If the extra instruction does not improve quality, reject its
promotion rather than install another rule. Designer-known reserved cases are
not an independently blind hold-out. Future natural-task acceptance is required.

The [system map](SYSTEM-MAP.md) distinguishes functioning components from proposed
connections, the Library front door and the unavailable live Web UI gate.

## Continuation and authority

The September 6 user request authorizes this persistent agent-driven loop and
repository delivery. The September 4 prohibition on scheduled compute remains:
no cron, launchd, scheduled GitHub Actions or self-spawning agent swarm. CI runs
only for pushes, pull requests or explicit manual dispatch, with read-only repo
permissions. A future unattended runtime needs an explicit host, cadence and
spending limit; the current Web UI is the intended reasoning host.

Sandbox/repository improvements are in scope. Global instruction rewrites, live
owner restarts, model/provider changes, raw transcript uploads and safety-control
removal still require their specific authority. Preserve backups for setup edits.
The library carries public-safe metadata only; private evidence stays here/local.

## Existing work, not a second system

GQ-012 (context) and GQ-021 (knowledge to behavior) supply the research questions.
The existing Harness Lab backlog remains the only task list. `experiments/` and
immutable receipts are evidence, not another task scheduler. Session Intelligence
and private Source/recall remain the ingestion/retrieval owners. Skills Hub owns
the `bounded-tool-output` and `trace-to-regression` skill sources. This project
tests whether those interventions earn their maintenance and context cost.

## Reservation, publication and source checks

The completed owner-continuation pilot must not be rerun. Its four overlapping
attempts and both candidate payloads remain preserved; the canonical responses
match the native-role workers, but the protocol is not a clean cost comparison.

The current trial publisher is scoped to that declared run. It now supports
`npm run outcome:grade -- claim baseline OWNER_ID` before allocating work, then
`npm run outcome:grade -- record baseline INPUT.json` to publish. A completed
arm refuses a claim. A reservation cannot be stolen or repeated by the same
owner. Publication uses exclusive creation and retains well-formed wrong answers.
There is no automatic cleanup/retry or dispatch; direct filesystem writes can
bypass the workflow, so future packets must use the publication command. Admit
a fresh run and its task-specific rubric before extending this declared trial;
do not repurpose completed filenames or frozen briefs.

Use `npm run evidence:verify -- RECEIPT.json` for supported Codex-attempt
provenance. It reads only explicit, project-scoped locators up to8MiB per source,
returns metadata verdicts only, and distinguishes unavailable from mismatch.
This is source verification, not a new transcript store or proof of live routing.
The private source checks are optional for portable synthetic work, but mandatory
before claiming those particular private-source results were independently verified.
