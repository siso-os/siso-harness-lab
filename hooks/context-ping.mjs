#!/usr/bin/env node
// context-ping.mjs — Claude Code PostToolUse hook: two gentle context pings, then the agent decides.
//
// Shaan, 1 Oct 2026: "agents should just be pinged like not too heavily but like nicely right and then just be
// told at like 40 35 just be conscious in the next 100 000 tokens you can be told to slash compact ... we kind
// of want to leave the reasoning up to the agents". DECISIONS.md (1 Oct) narrows the 4 Sep rule for this.
//
// Ping 1, the first time context use reaches PCT (35%): a heads-up that the compact ask comes in ~STEP tokens.
// Ping 2, STEP (100k) tokens after ping 1: compact at your next clean break, or defer in one line; the ask then
// repeats every REPEAT (50k) tokens. Pings only add text to the agent's context (additionalContext). They never
// compact, block or decide anything. When context falls back below PCT (a compaction), the pings re-arm.
//
// Context use comes from the status line (~/.claude/hud/siso-hud.mjs writes each session's context_window to
// STATE/ctx/<session>.json on every render), so the numbers match the footer the agent and Shaan see. Hook input
// carries no context figures (checked on 2.1.286). No status line (headless -p) means no pings.
//
// Silent for Agent Zero (SISO_A0=1), for subagents (input has agent_id), and on any error: exit 0, no output.
// A0, 2 Oct 2026, after Shaan's "optimize it a bit": ping 1 also fires at AT tokens (120k) whatever the percentage, so the ask lands ~220k.
// On 1M-context Opus, 35% is 350k, and every turn re-reads the whole context from cache: over 1-2 Oct, cache reads
// were 78% of all agents' weighted usage at an average 250-290k context per turn (90 sessions, 15,315 turns). Asking
// at ~220k instead of ~450k cuts that re-read by about a third (replay of 1-2 Oct: a 200k cap saves 37%, 150k 38%,
// 120k only 10% because compactions then dominate); the agent still decides when.
// STACK-OPT, 2 Oct 2026 (A0 brief item 2): compact at task boundaries, not only on tokens. When a Bash command appends a
// finish line (DONE, "DEV back", "PAGE POSTED") to the A0 inbox and context is over BOUNDARY (100k), add one line: the
// task is finished, compact now. The next task then starts from a small context instead of re-reading the last one.
// Burn samples (STACK-OPT, 2 Oct, for bin/burn-rate): on every call, if the status line's plan limits for this login
// (rate_limits five_hour / seven_day) moved since the last sample, append {at, profile, 5h, 7d, resets} to
// STATE/burn/samples.jsonl. That history is what turns a percentage into a percentage per hour. Runs for A0 too.
// EFFICIENCY, 2 Oct 2026 (A0 relay audit, Shaan 14:16 "I think 200 is a bit harsh ... up to like 500k"): the cap is
// looked up live, by agent name, in the caps file (config/context-caps.json) on every call. The launcher's env is fixed at
// launch, so a running agent never saw a later listing, and an agent launched without -n (AGENT-BASE) or renamed in
// herdr (STACK-OPT -> EFFICIENCY) never matched one. Names tried, first listed wins: herdr name, the registry alias of
// the herdr title, the title, SISO_AGENT_NAME (the launcher's -n), the transcript's agentName; cached per session for
// 10 min. A listed agent pings at cap - lead and is asked at the cap. An explicit --cap or CONTEXT_PING_AT still wins.
// EFFICIENCY, 2 Oct 2026 (token ledger, so-020): a session launched with SISO_TASK (claude-siso --task ID) is stamped on
// its first tool call: one {at, session, task, alloc, source:"env"} line in SISO_TASK_STATE/marks.jsonl, which
// bin/spend-ledger uses to charge the session's spend to that task instead of guessing. Runs for A0 too.
// Env (tests): SISO_TASK, SISO_ALLOC, SISO_CHAIN (opus:spec,luna:build,opus:review; so-021), SISO_TASK_STATE, SISO_CONTEXT_CAPS, SPEND_REGISTRY, HERDR_BIN, CONTEXT_PING_PCT, CONTEXT_PING_AT, CONTEXT_PING_STEP, CONTEXT_PING_REPEAT, CONTEXT_PING_BOUNDARY,
// CONTEXT_PING_STATE.

import { closeSync, existsSync, readdirSync, fstatSync, mkdirSync, openSync, readFileSync, readSync, renameSync, unlinkSync, writeFileSync, appendFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { homedir } from "node:os";
import path from "node:path";

const num = (v, d) => (Number.isFinite(Number(v)) && v !== "" && v != null ? Number(v) : d);

export function config(env = process.env) {
  return {
    pct: num(env.CONTEXT_PING_PCT, 35),
    at: num(env.CONTEXT_PING_AT, 120_000),
    step: num(env.CONTEXT_PING_STEP, 100_000),
    repeat: num(env.CONTEXT_PING_REPEAT, 50_000),
    boundary: num(env.CONTEXT_PING_BOUNDARY, 100_000),
    state: env.CONTEXT_PING_STATE || path.join(homedir(), ".local", "state", "context-ping"),
    // A test's own STATE never reads the live host records unless it names a hosts folder too.
    hosts: env.AB_HOSTS_DIR || (env.CONTEXT_PING_STATE ? null : path.join(homedir(), ".local", "state", "agent-base", "hosts")),
  };
}

const k = n => `${Math.round(n / 1000)}k`;

const HERE = path.dirname(new URL(import.meta.url).pathname);

export function capsFile(env = process.env) {
  if (env.SISO_CONTEXT_CAPS) return env.SISO_CONTEXT_CAPS;
  const mine = path.join(homedir(), ".config", "siso", "context-caps.json");
  return existsSync(mine) ? mine : path.join(HERE, "..", "config", "context-caps.json");
}

// The last agentName in the transcript's final 256 KB (claude writes it on each line of a -n session).
function transcriptName(file) {
  if (!file) return null;
  let fd;
  try {
    fd = openSync(file, "r");
    const size = fstatSync(fd).size, n = Math.min(size, 262_144), buf = Buffer.alloc(n);
    readSync(fd, buf, 0, n, size - n);
    const all = [...buf.toString("utf8").matchAll(/"agentName":"([^"]+)"/g)];
    return all.length ? all[all.length - 1][1] : null;
  } catch { return null; } finally { if (fd !== undefined) try { closeSync(fd); } catch {} }
}

function herdrNames(env) {
  if (!env.HERDR_PANE_ID) return [];
  try {
    const out = execFileSync(env.HERDR_BIN || "herdr", ["agent", "list"], { encoding: "utf8", timeout: 2000, stdio: ["ignore", "pipe", "ignore"] });
    const a = (JSON.parse(out).result?.agents || []).find(x => x.pane_id === env.HERDR_PANE_ID);
    if (!a) return [];
    const title = a.terminal_title_stripped || "";
    const reg = readJson(env.SPEND_REGISTRY || path.join(homedir(), ".local", "state", "agent-base", "registry.json"));
    return [a.name, reg?.aliases?.[title], title];
  } catch { return []; }
}

// Every name this session goes by, most current first; cached per session so herdr is asked at most every 10 min.
export function agentNames(input, env, cfg, now = Date.now()) {
  const f = path.join(cfg.state, "names", `${safeId(input.session_id)}.json`);
  const hit = readJson(f);
  if (hit && now - hit.at < 600_000) return hit.names;
  const names = [...herdrNames(env), env.SISO_AGENT_NAME, transcriptName(input.transcript_path)]
    .filter(Boolean).map(String).filter((x, i, a) => a.indexOf(x) === i);
  try { writeJson(f, { at: now, names }); } catch {}
  return names;
}

// Pure: the first listed name's tier from the caps file -> { name, tier, at, step, pct }, or null.
export function capFor(names, caps) {
  if (!caps?.agents || !caps.tiers) return null;
  const agents = Object.fromEntries(Object.entries(caps.agents).map(([n, t]) => [n.toUpperCase(), t]));
  const name = names.find(n => agents[n.toUpperCase()] in caps.tiers);
  if (!name) return null;
  const tier = agents[name.toUpperCase()], cap = Number(caps.tiers[tier]), lead = Number(caps.lead) || 100_000;
  return { name, tier, at: Math.max(cap - lead, 0), step: lead, pct: 80 };
}

// An explicit --cap N/TIER or a hand-set CONTEXT_PING_AT (no tier from the launcher) is left alone.
export function explicitCap(env) {
  return env.SISO_CONTEXT_SOURCE === "cap" || env.SISO_CONTEXT_TIER === "custom" || (!!env.CONTEXT_PING_AT && !env.SISO_CONTEXT_TIER);
}

export function liveConfig(input, env = process.env, cfg = config(env)) {
  if (explicitCap(env)) return cfg;
  const hit = capFor(agentNames(input, env, cfg), readJson(capsFile(env)));
  return hit ? { ...cfg, at: hit.at, step: hit.step, pct: hit.pct, tier: hit.tier, name: hit.name } : cfg;
}

// Pure: given the reading and the session's ping state, return { text, state } (text null = stay quiet).
export function decide(ctx, prev, cfg) {
  const { pct, tokens } = ctx;
  if (!Number.isFinite(pct) || !Number.isFinite(tokens)) return { text: null, state: prev };
  if (pct < cfg.pct && !(tokens >= cfg.at)) return { text: null, state: null }; // below both lines, or compacted since: re-arm
  if (!prev) {
    return {
      text: `Context heads-up: you're at ${Math.round(pct)}% context (${k(tokens)} tokens). Within about the next ` +
        `${k(cfg.step)} tokens you'll be asked to compact. Keep your checkpoint current and watch for a clean break. ` +
        `Nothing will compact you; you decide when.`,
      state: { first: tokens, next: tokens + cfg.step, asks: 0 },
    };
  }
  if (tokens < prev.next) return { text: null, state: prev };
  const asks = prev.asks + 1;
  return {
    text: `Context: ${Math.round(pct)}% (${k(tokens)} tokens). Time to compact at your next clean break (the ` +
      `self-compact skill). If you're mid-conversation with Shaan or in the middle of reasoning that matters, defer ` +
      `and say so in one line; you'll be asked again in about ${k(cfg.repeat)} tokens. If Shaan or Agent Zero has ` +
      `told you to compact or not to, that wins.`,
    state: { ...prev, next: tokens + cfg.repeat, asks },
  };
}

// Pure: a Bash command that appends a finish line to the A0 inbox marks a task boundary.
const FINISH = /\bDONE\b|\bDEV back\b|\bPAGE POSTED\b/; // the A0 inbox convention is upper-case DONE
export function finishedTask(input) {
  const cmd = input?.tool_name === "Bash" ? String(input.tool_input?.command || "") : "";
  return /a0\/inbox\.log/.test(cmd) && />>/.test(cmd) && FINISH.test(cmd);
}

export function boundaryText(input, tokens, cfg) {
  if (!finishedTask(input) || !(tokens > cfg.boundary)) return null;
  return `Task boundary: you just reported a finished task at ${k(tokens)} tokens. Compact now (the self-compact ` +
    `skill) so the next task starts small, unless Shaan or Agent Zero told you otherwise.`;
}

// The footer's numbers, from what the status line last saw for this session.
export function reading(file) {
  return readingOf(JSON.parse(readFileSync(file, "utf8")));
}

export function readingOf(cw) {
  const pct = Number(cw.used_percentage);
  const size = Number(cw.context_window_size);
  const u = cw.current_usage || {};
  const used = ["input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"]
    .reduce((s, f) => s + (Number(u[f]) || 0), 0);
  const tokens = used || (size ? (pct / 100) * size : NaN);
  return { pct, tokens };
}

const safeId = s => String(s).replace(/[^A-Za-z0-9_-]/g, "_");

function readJson(f) {
  try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; }
}

function writeJson(f, obj) {
  mkdirSync(path.dirname(f), { recursive: true });
  const tmp = `${f}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(obj));
  renameSync(tmp, f);
}

// FLEET-COST, 7 Oct 2026: a chat hosted by Agent Base (the SDK, no TUI) never renders the status line, so STATE/ctx/<id>.json
// is never written for it: every hosted chat got no pings and no burn samples from 3 Oct (the window of 6 Oct ran 9 Opus
// chats at 150-400k average context, unasked). The host writes the same facts to its record
// (~/.local/state/agent-base/hosts/*.json: ctx {used, window, pct}, rateLimits, configDir); read that when it is newer.
export function hostCtx(cfg, id) {
  try {
    for (const f of readdirSync(cfg.hosts)) {
      if (!f.endsWith(".json")) continue;
      const h = readJson(path.join(cfg.hosts, f));
      if (!h || safeId(h.session || "") !== id || !h.ctx) continue;
      return {
        used_percentage: h.ctx.pct, context_window_size: h.ctx.window, current_usage: { input_tokens: h.ctx.used },
        rate_limits: h.rateLimits || null, profile: h.configDir || null, at: h.rateLimits?.at || h.ctx.at || h.updatedAt || null,
      };
    }
  } catch {}
  return null;
}

// The status line's file for this session, or the Agent Base host record when that is newer (or the only one).
export function ctxFor(cfg, id) {
  let file = null;
  try { file = JSON.parse(readFileSync(path.join(cfg.state, "ctx", `${id}.json`), "utf8")); } catch {}
  const host = cfg.hosts ? hostCtx(cfg, id) : null;
  if (!host) return file;
  if (!file || (Number(host.at) || 0) > (Number(file.at) || 0)) return { ...host, rate_limits: host.rate_limits || file?.rate_limits || null };
  return file;
}

// A reset time as epoch seconds on the minute: hosts report ISO text that differs by microseconds between chats, and
// bin/burn-rate splits its rate at every distinct reset value.
export function minute(v) {
  if (v == null) return null;
  const n = typeof v === "number" ? (v > 1e11 ? v / 1000 : v) : Date.parse(v) / 1000;
  return Number.isFinite(n) ? Math.round(n / 60) * 60 : null;
}

// Append a plan-limit sample when this login's numbers moved (or every 10 min while steady). Never throws.
export function sampleBurn(cfg, id, now = Date.now()) {
  try {
    const cw = ctxFor(cfg, id);
    const rl = cw?.rate_limits;
    if (!rl || (rl.five_hour?.used_percentage == null && rl.seven_day?.used_percentage == null)) return null;
    const profile = cw.profile || "unknown";
    const row = {
      at: new Date(cw.at || now).toISOString(), profile,
      h5: rl.five_hour?.used_percentage ?? null, h5_reset: minute(rl.five_hour?.resets_at),
      d7: rl.seven_day?.used_percentage ?? null, d7_reset: minute(rl.seven_day?.resets_at),
    };
    const lastFile = path.join(cfg.state, "burn", `last-${safeId(profile)}.json`);
    const last = readJson(lastFile);
    const moved = !last || last.h5 !== row.h5 || last.d7 !== row.d7 || Date.parse(row.at) - Date.parse(last.at) >= 600_000;
    if (!moved || (last && Date.parse(row.at) <= Date.parse(last.at))) return null;
    writeJson(lastFile, row);
    appendFileSync(path.join(cfg.state, "burn", "samples.jsonl"), JSON.stringify(row) + "\n");
    return row;
  } catch { return null; }
}

// "credits:600" -> {credits: 600}; "tokens:3M" -> {tokens: 3000000}; anything else -> null (as bin/siso-task).
export function parseAlloc(s) {
  const m = /^(usd|credits|tokens):(\d+(?:\.\d+)?)([kKmM]?)$/.exec(String(s || "").trim());
  return m ? { [m[1]]: Number(m[2]) * ({ "": 1, k: 1e3, m: 1e6 })[m[3].toLowerCase()] } : null;
}

// Stamp this session with its launch task once (again only if SISO_TASK changes). Never throws.
export function stampTask(input, env, cfg, now = new Date()) {
  try {
    if (!env.SISO_TASK) return null;
    const seen = path.join(cfg.state, "tasks", `${safeId(input.session_id)}.json`);
    if (readJson(seen)?.task === env.SISO_TASK) return null;
    const dir = env.SISO_TASK_STATE || path.join(homedir(), ".local", "state", "siso-task");
    const chain = env.SISO_CHAIN ? String(env.SISO_CHAIN).split(",").map(x => x.trim().toLowerCase()).filter(Boolean) : null;
    const row = { at: now.toISOString(), session: input.session_id, task: env.SISO_TASK, alloc: parseAlloc(env.SISO_ALLOC), source: "env", chain };
    mkdirSync(dir, { recursive: true });
    appendFileSync(path.join(dir, "marks.jsonl"), JSON.stringify(row) + "\n");
    writeJson(seen, { task: env.SISO_TASK });
    return row;
  } catch { return null; }
}

export function run(input, env = process.env) {
  if (input.agent_id || !input.session_id) return null;
  let cfg = config(env);
  const id = safeId(input.session_id);
  sampleBurn(cfg, id);
  stampTask(input, env, cfg);
  if (env.SISO_A0 === "1") return null;
  try { cfg = liveConfig(input, env, cfg); } catch {}
  const cw = ctxFor(cfg, id);
  if (!cw) return null;
  const ctx = readingOf(cw);
  const pingFile = path.join(cfg.state, "pings", `${id}.json`);
  const prev = readJson(pingFile);
  const { text: ping, state } = decide(ctx, prev, cfg);
  const edge = boundaryText(input, ctx.tokens, cfg);
  const text = [ping, edge].filter(Boolean).join("\n") || null;
  if (state === null) { if (prev) try { unlinkSync(pingFile); } catch {} }
  else if (state !== prev) writeJson(pingFile, state);
  if (text) {
    try {
      appendFileSync(path.join(cfg.state, "log.jsonl"), JSON.stringify({
        ts: new Date().toISOString(), session: input.session_id, pct: ctx.pct, tokens: Math.round(ctx.tokens),
        ping: edge && !ping ? "boundary" : state?.asks ? "compact" : "heads-up", asks: state?.asks ?? 0, boundary: !!edge,
      }) + "\n");
    } catch {}
  }
  return text;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  let raw = "";
  process.stdin.on("data", c => (raw += c));
  process.stdin.on("end", () => {
    try {
      const text = run(JSON.parse(raw || "{}"));
      if (text) {
        process.stdout.write(JSON.stringify({
          hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: text },
        }));
      }
    } catch {}
    process.exit(0);
  });
}
