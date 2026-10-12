# Decisions (Shaan's standing rulings)

Newest first. A ruling here binds every agent working in this repo. To change one, Shaan
says so; then add a new dated entry that supersedes, never edit the old one.

## 2026-10-01

- **Context pings that inform are allowed; nothing may compact, block or nag.** *"agents should
  just be pinged like not too heavily but like nicely right and then just be told at like 40 35
  just be conscious in the next 100 000 tokens you can be told to slash compact ... i was talking
  to an agent base and mid-conversation he started slash compacting i bet he didn't know that was
  happening and we were cooking ... we kind of want to leave the reasoning up to the agents"*
  (1 Oct, ~19:05, after a forced 45% auto-compact hit an agent mid-conversation). Narrows the
  2026-09-04 "no hooks that block, warn, or inject on context size": `hooks/context-ping.mjs` adds
  two notes to a Claude agent's context (heads-up at ~35%, a compact ask ~100k tokens later,
  repeated every ~50k while the agent defers) and nothing else. No forced early compaction
  (`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` unset; Claude Code's ~95% is the only net). The agent decides:
  compact at a clean break, defer mid-conversation with Shaan or mid-critical reasoning; Shaan or
  Agent Zero saying otherwise wins. Agent Zero gets no pings.

## 2026-09-11

- **The first mate owns decisions; Shaan takes advice, not decision requests.** *"you are the
  full ceo your full authority you come back to me with the things that you have done not
  decisions needed and bullshit if you need advice that's fine you can come back for advice but
  don't come back for decisions you own all the decisions"* (2026-09-11, later). Flag destructive
  or outward-facing actions once, then do them.
- **Two repos per project team, everything in them.** A versioned template
  (`siso-project-team`) and one agent-space repo per project (`siso-internal-labs-agents`,
  like Oracle's companion) holding *"conversation history my words everything all also linked
  together"*. Transcripts go in redacted (`tools/sessions-import`); `intent/` and `sessions/`
  are never published.
- **Learn from Oracle, both ways.** *"by far the project that we've spent the most tokens on …
  take good infrastructure and bad infrastructure from there note it down"* — the study lives at
  the template's `docs/lessons-from-oracle.html` and feeds the skills.

- **One Agent Zero per project, under a personal Agent Zero.** *"there's a whole agent's
  agent zero … my personal agent for the whole infrastructure, then there's one per project.
  The SISO internal is a project so it needs its own agent zero and then owners inside of
  it."* The personal Agent Zero (`siso-agent-zero-protocol`) reads digests; it does not run
  a project's fleet. Supersedes the 2026-09-10 "do NOT create a new Agent Zero per project"
  note in `PROJECT-ESTATE.md` — there is still one *repo* (`sisodias/siso-project-team`),
  with one `teams/<code>/` per project.
- **Harness by role.** Opus brain and owners run on Claude Code (*"opus is running their
  harness because they're the best in it"*). Qwen and Luna arms run on the **Codex**
  harness, spawned by herdr, and message back when done (*"we'll have qwen running in codex
  for now and luna running in codex … herder can just spawn them … it will message it back
  to the agent anyways"*). For arms this supersedes 2026-09-03 "never spawn via herdr".
  Owners with no arms available do the work themselves or use built-in sub-agents.
- **The team is a repackageable box.** *"we need like a repackageable skill that can be
  used for every new project team … any feedback and improvements actually stick with a
  repo."* Role skills (`project-agent-zero`, `project-owner`, `project-worker`) live in
  `sisodias/siso-project-team`; a nice README and a Cloudflare front end are part of it.
- **Every word to an Agent Zero is captured verbatim and viewable** (*"every single word
  I've said to the agent zero is viewable and any future agent can go through it to see
  what we missed"*). `bin/intent-capture` in the team repo; his words verbatim or absent.

## 2026-09-08

- **Astra reasons; Luna executes substantial work.** Reuse the existing God Questions
  and brain/worker contract. Prefer one continuing Luna executor, not a new
  orchestration tier or a quota of tiny delegations.
- **Separate compaction policy.** Shaan approved Astra around300–400k, then asked
  to compare272k/350k with a usage graph. Initial adopted base-Astra trigger350k;
  do not impose it on Luna or pretend a trigger shrinks true model capacity.
  Larger Luna context needs supported capacity. No live restart, context-size
  hooks, replay campaign or billing/savings guarantee is implied.

## 2026-09-04

- **No hooks that block, warn, or inject on context size.** "You can't stop context turns
  over 200k... one prompt, boom, it's at 400k. Leave it to me." Keep context guidance as
  prose only. Spend effort on boot cost, dead catalogs, worker quality, wake paths.
- **Nothing runs on a schedule.** No cron, no launchd loops, no recurring audits that burn
  compute. Audits and cleanups are on-demand commands (`console-audit [DAYS]`).
- **Unlimited agents are over; back to reserve and usage.** Six concurrent Opus workers
  hit the session limit mid-run. Next waves: one worker at a time, or wait for spare
  compute. When a new model drops (Astra), point it here.
- **Explicit model override is allowed for a domain review** by putting `ROUTE-OVERRIDE:
  opus|sonnet|haiku` at the top of the prompt. Without it, `luna-route.mjs` pins gpt-luna
  (work) or gpt-sol (explicit review only). Fable is never a worker.
- **Skill source of truth is UNDECIDED.** Shaan said Agent_Base is where skills are
  authored; `SISO_Agent_Base/MANIFEST.yaml` says it was retired 2026-08-09 with
  `siso-skills-hub` as successor, and every live port points at the hub. Decision card open
  on the console. No sync in either direction until answered.
- **The other Claude session (`shaansisodia-69`) owns the Codex Fable lane**: the
  normalizer, `~/.codex/fable*.config.toml`, `~/bin/codex-fable`. Read them, do not edit.

## 2026-09-03

- **No Claude artifacts.** Visual deliverables go to a local URL or Cloudflare Pages.
- **Act, don't ask.** Flag destructive or outward-facing actions once. Commit `~/.claude`
  only when asked (never so far).
- **Terminal output short: answer, then evidence.** Anything Shaan must look at goes to the
  console as a card or URL.
- **Claude workers are `gpt-luna` via the Agent tool; `gpt-sol` only for a cold review.**
  Never spawn via herdr. Built-in Explore/Plan are fine for read-only sweeps.
- **Never message a running worker for status.** It re-sends its return when it finishes.
- **Interactive first-mate session stays in Claude Code** (console, hooks, subagents,
  cross-session messaging live there). Codex-hosted Fable is for background lanes, and its
  per-turn advantage is unproven (the cited 99-turn session was Sol).

## 2026-10-03 — Context caps are hard (supersedes the 1 Oct ping-only rule for the cap itself)

Shaan, 3 Oct ~17:00: "auto compacting at certain things ... if it's souls let it run up to like four or five hundred k if
it's opuses if their owners maybe five hundred k normally three hundred k though like that nine hundred k thing shouldn't
have happened". EFFICIENCY reached 902k on the ping-only cap. Measured 2-3 Oct: 53% of 8.2 B tokens were model calls made
with more than 300k in context (siso-firstmate .agents/a0/specs/2026-10-03-stack-first-principles/).
Now: tiers worker 200k, builder/default 300k, owner 500k, heavy 500k; bin/context-cap.sh exports
CLAUDE_AUTOCOMPACT_PCT_OVERRIDE = cap / 1M window, so Claude Code compacts at the cap. The context-ping heads-up still comes
100k earlier so an agent can checkpoint first. Codex: model_auto_compact_token_limit 450000. SISO_CONTEXT_HARD=0 = ping-only.
Applies at each agent's next launch. Owner: Agent Zero (took the stack over from EFFICIENCY on Shaan's word, 3 Oct ~17:00).
