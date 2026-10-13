#!/usr/bin/env node
// fetch-nudge: PostToolUse hook. When a main chat (not a sub-agent) makes its 3rd read/search/command call in a row,
// it is told once, in two lines, to hand the rest of the digging to a Haiku 5.5 scout. Any other tool (Edit, Write,
// Agent, ...) ends the run; a gap of 10 minutes does too. One nudge per run, at most one per 15 fetch calls.
// Why: Opus fetching for itself was 70% of list-price spend over 72 h (scripts/token-where.py, 12 Oct); the lean
// prompt alone moved it only 9-16%. Measure with token-where's "Opus fetch loops" line before and after.
// Second stage (PreToolUse, same file, 13 Oct): the nudge alone moved little (49 nudges in 6 h, the next call was a
// sub-agent 3 times in 25), so the 4th fetch in a row (6th until 14 Oct) is turned back once with the same advice; repeating the call goes
// through, so it never stops work (the read-gate pattern, which Haiku and Opus both followed). At most once per 20 fetches.
// Any error prints nothing. FETCH_NUDGE=0 turns both off; FETCH_TURNBACK=0 only the second. State: ~/.local/state/fetch-nudge/<session>.json
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

export const FETCH = new Set(["Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch", "LSP"]);
export const AT = 3, GAP_MS = 10 * 60_000, EVERY = 15, BACK_AT = 4, BACK_EVERY = 20; // BACK_AT 6 -> 4 on 14 Oct: reading loops 8% in the 20 h after the restarts (line was 5%)
export const TEXT = "You have made 3 read/search/command calls in a row yourself. If more digging is needed, give it to the " +
  "scout agent (Haiku 5.5, ~40x cheaper per token; or any sub-agent with model haiku) as one precise question asking for " +
  "a short answer with file:line, and work from its return; several questions go to several scouts in one message " +
  "(skill haiku-leverage has the patterns). Keep judgement and the build yourself.";

// Pure: next state and whether to nudge.
// Bash counts as fetching only when it reads (13 Oct: a deploy/commit chain was turned back as "digging").
const READ_CMD = /^\s*(cd [^;&|]+(&&|;)\s*)?(cat|head|tail|sed -n|grep|rg|ugrep|ls|find|fd|wc|git (log|show|diff|status|grep|blame)|jq|awk|tree|stat|file)\b/;
export const isFetch = (input) => FETCH.has(input.tool_name) && (input.tool_name !== "Bash" || READ_CMD.test(input.tool_input?.command ?? ""));

export function step(prev, input, now = Date.now()) {
  const s = prev && now - prev.at < GAP_MS ? { ...prev } : { run: 0, since: EVERY };
  s.at = now;
  if (!isFetch(input)) return { state: { ...s, run: 0 }, nudge: false };
  s.run += 1;
  s.since += 1;
  const nudge = s.run === AT && s.since >= EVERY;
  if (nudge) s.since = 0;
  return { state: s, nudge };
}

export const BACK = "This would be your 4th read/search call in a row. Hand the rest of this digging to a Haiku " +
  "sub-agent now (Agent tool: scout if listed, else general-purpose with model haiku) as one precise question asking for a " +
  "short answer with file:line, and work from its return; several questions go to several scouts in one message (skill " +
  "haiku-leverage). If this one call is all you still need, repeat it and it will go through.";

// Pure (PreToolUse): turn this call back? Only the BACK_AT-th fetch of a live run, once per run, at most once per BACK_EVERY fetches.
export function turnback(state, input, now = Date.now()) {
  if (!isFetch(input) || !state || now - state.at >= GAP_MS) return { state, back: false };
  const s = { ...state };
  const back = s.run === BACK_AT - 1 && !s.backRun && (s.sinceBack ?? BACK_EVERY) >= BACK_EVERY;
  if (back) { s.backRun = true; s.sinceBack = 0; }
  return { state: s, back };
}

async function main() {
  if (process.env.FETCH_NUDGE === "0") return;
  let raw = "";
  for await (const c of process.stdin) raw += c;
  const input = JSON.parse(raw);
  if (input.agent_id || !input.session_id) return; // sub-agents are the hands already
  const dir = process.env.FETCH_NUDGE_STATE || path.join(homedir(), ".local", "state", "fetch-nudge");
  const file = path.join(dir, `${input.session_id}.json`);
  let prev = null;
  try { prev = JSON.parse(readFileSync(file, "utf8")); } catch {}
  mkdirSync(dir, { recursive: true });
  if (input.hook_event_name === "PreToolUse") {
    if (process.env.FETCH_TURNBACK === "0") return;
    const { state, back } = turnback(prev, input);
    if (!back) return;
    writeFileSync(file, JSON.stringify(state));
    process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: BACK } }));
    return;
  }
  const { state, nudge } = step(prev, input);
  if (!isFetch(input)) state.backRun = false; // a new run may be turned back again
  else state.sinceBack = (state.sinceBack ?? BACK_EVERY) + 1;
  writeFileSync(file, JSON.stringify(state));
  if (nudge) process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: TEXT } }));
}

if (import.meta.url === `file://${process.argv[1]}`) main().catch(() => {});
