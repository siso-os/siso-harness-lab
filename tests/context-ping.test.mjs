import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { config, decide, run, finishedTask, boundaryText } from "../hooks/context-ping.mjs";

const cfg = { pct: 35, step: 100_000, repeat: 50_000 };

test("quiet below the line", () => {
  assert.deepEqual(decide({ pct: 20, tokens: 200_000 }, null, cfg), { text: null, state: null });
});

test("heads-up once, compact ask after step, repeat after deferral", () => {
  let r = decide({ pct: 36, tokens: 360_000 }, null, cfg);
  assert.match(r.text, /heads-up: you're at 36% context.*next 100k tokens/);
  assert.deepEqual(r.state, { first: 360_000, next: 460_000, asks: 0 });
  r = decide({ pct: 40, tokens: 400_000 }, r.state, cfg);
  assert.equal(r.text, null);
  r = decide({ pct: 46, tokens: 460_000 }, r.state, cfg);
  assert.match(r.text, /Time to compact at your next clean break.*defer.*again in about 50k/);
  assert.equal(r.state.asks, 1);
  assert.equal(r.state.next, 510_000);
  assert.equal(decide({ pct: 49, tokens: 490_000 }, r.state, cfg).text, null);
  assert.equal(decide({ pct: 51, tokens: 510_000 }, r.state, cfg).state.asks, 2);
});

test("re-arms after a compaction drops context below the line", () => {
  assert.equal(decide({ pct: 10, tokens: 100_000 }, { first: 1, next: 2, asks: 3 }, cfg).state, null);
});

test("garbage reading stays quiet and keeps state", () => {
  const prev = { first: 1, next: 2, asks: 0 };
  assert.deepEqual(decide({ pct: NaN, tokens: 5 }, prev, cfg), { text: null, state: prev });
});

test("run: reads the status line's file, skips A0, subagents and missing data", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "cping-"));
  // No status-line reading and no host record yet: quiet.
  assert.equal(run({ session_id: "s1" }, { CONTEXT_PING_STATE: dir }), null);
  mkdirSync(path.join(dir, "ctx"), { recursive: true });
  writeFileSync(path.join(dir, "ctx", "s1.json"), JSON.stringify({ used_percentage: 50, context_window_size: 1_000_000 }));
  const env = { CONTEXT_PING_STATE: dir };
  assert.equal(run({ session_id: "s1" }, { ...env, SISO_A0: "1" }), null);
  assert.equal(run({ session_id: "s1", agent_id: "a" }, env), null);
  assert.match(run({ session_id: "s1" }, env), /500k tokens/);
  assert.equal(run({ session_id: "s1" }, env), null);
  assert.ok(existsSync(path.join(dir, "pings", "s1.json")));
  writeFileSync(path.join(dir, "ctx", "s1.json"), JSON.stringify({ used_percentage: 5, context_window_size: 1_000_000 }));
  assert.equal(run({ session_id: "s1" }, env), null);
  assert.ok(!existsSync(path.join(dir, "pings", "s1.json")));
  rmSync(dir, { recursive: true, force: true });
});

test("the token line pings before the percentage on a 1M window, and re-arms below both", () => {
  const c = { pct: 35, at: 150_000, step: 100_000, repeat: 50_000 };
  assert.deepEqual(decide({ pct: 14, tokens: 140_000 }, null, c), { text: null, state: null });
  let r = decide({ pct: 15, tokens: 150_000 }, null, c);
  assert.match(r.text, /heads-up/);
  assert.equal(r.state.next, 250_000);
  r = decide({ pct: 25, tokens: 250_000 }, r.state, c);
  assert.match(r.text, /Time to compact/);
  assert.deepEqual(decide({ pct: 6, tokens: 60_000 }, r.state, c), { text: null, state: null });
});

test("config defaults the token line to 120k and reads CONTEXT_PING_AT", () => {
  assert.equal(config({}).at, 120_000);
  assert.equal(config({ CONTEXT_PING_AT: "90000" }).at, 90_000);
});

const inbox = "~/SISO_Workspace/SISO_Agents/agent-zero/siso-firstmate/.agents/a0/inbox.log";
const bash = command => ({ tool_name: "Bash", tool_input: { command } });

test("task boundary: a DONE / DEV back / PAGE POSTED append to the A0 inbox is a finished task", () => {
  assert.ok(finishedTask(bash(`echo "$(date +%H:%M) STREAM-A: DONE camsoda login" >> ${inbox}`)));
  assert.ok(finishedTask(bash(`echo "14:02 OPS-BUILD: DEV back to STREAMING" >> ${inbox}`)));
  assert.ok(finishedTask(bash(`echo "14:02 OPS-UX: PAGE POSTED http://x" >> ${inbox}`)));
  assert.ok(!finishedTask(bash(`echo "14:02 X: go board. Post done." >> ${inbox}`)), "lower-case done is an instruction, not a finish");
  assert.ok(!finishedTask(bash(`grep DONE ${inbox}`)), "reading the inbox is not reporting");
  assert.ok(!finishedTask(bash(`echo DONE >> notes.log`)), "other files don't count");
  assert.ok(!finishedTask({ tool_name: "Write", tool_input: { content: `DONE >> ${inbox}` } }));
});

test("task boundary: asks to compact only above 100k", () => {
  const c = config({});
  const done = bash(`echo "x: DONE" >> ${inbox}`);
  assert.equal(boundaryText(done, 90_000, c), null);
  assert.match(boundaryText(done, 180_000, c), /finished task at 180k tokens\. Compact now/);
  assert.equal(boundaryText(bash("ls"), 500_000, c), null);
});

test("run: the boundary line rides alongside (or without) the token pings", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "cping-"));
  mkdirSync(path.join(dir, "ctx"), { recursive: true });
  const env = { CONTEXT_PING_STATE: dir };
  const done = { session_id: "s2", ...bash(`echo "x: DONE" >> ${inbox}`) };
  writeFileSync(path.join(dir, "ctx", "s2.json"), JSON.stringify({ used_percentage: 11, context_window_size: 1_000_000 }));
  assert.match(run(done, env), /^Task boundary/);              // 110k: under the 120k token line, boundary only
  assert.equal(run({ session_id: "s2", ...bash("ls") }, env), null);
  writeFileSync(path.join(dir, "ctx", "s2.json"), JSON.stringify({ used_percentage: 13, context_window_size: 1_000_000 }));
  const both = run(done, env);                                  // 130k: heads-up and boundary together
  assert.match(both, /Context heads-up[\s\S]*\nTask boundary/);
  assert.equal(run({ ...done, agent_id: "sub" }, env), null);  // subagents stay silent
  rmSync(dir, { recursive: true, force: true });
});

test("burn samples: appended when this login's plan numbers move, once per change, A0 included", async () => {
  const { sampleBurn } = await import("../hooks/context-ping.mjs");
  const dir = mkdtempSync(path.join(tmpdir(), "cping-"));
  mkdirSync(path.join(dir, "ctx"), { recursive: true });
  const ctx = (at, h5, d7) => writeFileSync(path.join(dir, "ctx", "s.json"), JSON.stringify({
    used_percentage: 5, context_window_size: 1_000_000, profile: "/p/.claude-siso", at,
    rate_limits: { five_hour: { used_percentage: h5, resets_at: 1 }, seven_day: { used_percentage: d7, resets_at: 2 } } }));
  const cfg = { state: dir };
  ctx(1_000_000, 10, 40);
  assert.equal(sampleBurn(cfg, "s").h5, 10);
  assert.equal(sampleBurn(cfg, "s"), null, "same numbers, same time: no new sample");
  ctx(1_060_000, 11, 40);
  assert.equal(sampleBurn(cfg, "s").h5, 11);
  ctx(1_000_000 + 30 * 60_000, 11, 40);
  run({ session_id: "s" }, { CONTEXT_PING_STATE: dir, SISO_A0: "1" });     // A0's calls sample too (steady 10+ min)
  const rows = readFileSync(path.join(dir, "burn", "samples.jsonl"), "utf8").trim().split("\n").map(l => JSON.parse(l));
  assert.deepEqual(rows.map(r => r.h5), [10, 11, 11]);
  assert.equal(rows[0].profile, "/p/.claude-siso");
  rmSync(dir, { recursive: true, force: true });
});

test("live cap: the caps file is read by herdr name, registry alias, title, -n or transcript; explicit caps win", async () => {
  const { capFor, liveConfig, explicitCap } = await import("../hooks/context-ping.mjs");
  const dir = mkdtempSync(path.join(tmpdir(), "cping-cap-"));
  const caps = path.join(dir, "caps.json");
  writeFileSync(caps, JSON.stringify({ default: "220k", lead: 100000, tiers: { worker: 200000, builder: 300000, owner: 400000, heavy: 600000 },
    agents: { "AGENT-BASE": "heavy", HEALTH: "owner", EFFICIENCY: "owner", "STACK-OPT": "builder", "HUB-DESIGN": "heavy" } }));
  writeFileSync(path.join(dir, "reg.json"), JSON.stringify({ aliases: { "Shaan's Agent Base app handoff": "AGENT-BASE" } }));
  const agents = [
    { pane_id: "w1:p1", name: null, terminal_title_stripped: "Shaan's Agent Base app handoff" },
    { pane_id: "w1:p2", name: "efficiency", terminal_title_stripped: "STACK-OPT" },
    { pane_id: "w1:p3", name: null, terminal_title_stripped: "HUB-DESIGN" },
    { pane_id: "w1:p4", name: null, terminal_title_stripped: "some chat" },
  ];
  writeFileSync(path.join(dir, "agents.json"), JSON.stringify({ result: { agents } }));
  const herdr = path.join(dir, "herdr");
  writeFileSync(herdr, `#!/bin/sh\ncat "${path.join(dir, "agents.json")}"\n`, { mode: 0o755 });
  const base = { CONTEXT_PING_STATE: dir, SISO_CONTEXT_CAPS: caps, SPEND_REGISTRY: path.join(dir, "reg.json"), HERDR_BIN: herdr };
  const live = (sid, env, extra = {}) => liveConfig({ session_id: sid, ...extra }, { ...base, ...env });

  let c = live("ab", { HERDR_PANE_ID: "w1:p1" });
  assert.deepEqual([c.name, c.tier, c.at, c.step, c.pct], ["AGENT-BASE", "heavy", 500000, 100000, 80], "no -n: the title's registry alias");
  c = live("eff", { HERDR_PANE_ID: "w1:p2", SISO_AGENT_NAME: "STACK-OPT", SISO_CONTEXT_TIER: "builder", CONTEXT_PING_AT: "200000" });
  assert.deepEqual([c.name, c.at], ["efficiency", 300000], "the herdr rename beats the launch name and the launch env");
  assert.equal(live("hd", { HERDR_PANE_ID: "w1:p3", CONTEXT_PING_AT: "120000", SISO_CONTEXT_TIER: "default" }).at, 500000,
    "launched on the default before the listing: picks the listing up live");
  const tr = path.join(dir, "t.jsonl");
  writeFileSync(tr, ['{"type":"user","agentName":"OLD"}', '{"type":"user","agentName":"HEALTH"}'].join("\n") + "\n");
  assert.equal(live("he", {}, { transcript_path: tr }).at, 300000, "outside herdr: the transcript's agentName");
  const plain = live("chat", { HERDR_PANE_ID: "w1:p4" });
  assert.deepEqual([plain.at, plain.pct, plain.tier], [120000, 35, undefined], "unlisted: unchanged");
  assert.equal(live("x1", { HERDR_PANE_ID: "w1:p1", SISO_CONTEXT_SOURCE: "cap", CONTEXT_PING_AT: "50000" }).at, 50000, "--cap wins");
  assert.equal(live("x2", { HERDR_PANE_ID: "w1:p1", CONTEXT_PING_AT: "90000" }).at, 90000, "a hand-set CONTEXT_PING_AT wins");
  assert.ok(explicitCap({ SISO_CONTEXT_TIER: "custom" }) && !explicitCap({ SISO_CONTEXT_TIER: "default", CONTEXT_PING_AT: "1" }));

  // Cached per session: a herdr outage doesn't change the answer, and a caps edit applies on the next call.
  writeFileSync(herdr, "#!/bin/sh\nexit 1\n", { mode: 0o755 });
  assert.equal(live("ab", { HERDR_PANE_ID: "w1:p1" }).at, 500000);
  writeFileSync(caps, JSON.stringify({ lead: 100000, tiers: { owner: 400000 }, agents: { "AGENT-BASE": "owner" } }));
  assert.equal(live("ab", { HERDR_PANE_ID: "w1:p1" }).at, 300000);
  assert.equal(capFor(["X"], { agents: { X: "nope" }, tiers: {} }), null, "a listing with no real tier is ignored");
  rmSync(dir, { recursive: true, force: true });
});

test("run: a listed agent's heads-up waits for its cap", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "cping-run-"));
  mkdirSync(path.join(dir, "ctx"), { recursive: true });
  const caps = path.join(dir, "caps.json");
  writeFileSync(caps, JSON.stringify({ lead: 100000, tiers: { heavy: 600000 }, agents: { "AGENT-BASE": "heavy" } }));
  const env = { CONTEXT_PING_STATE: dir, SISO_CONTEXT_CAPS: caps, SISO_AGENT_NAME: "AGENT-BASE" };
  writeFileSync(path.join(dir, "ctx", "s.json"), JSON.stringify({ used_percentage: 25, context_window_size: 1_000_000 }));
  assert.equal(run({ session_id: "s" }, env), null, "250k: an unlisted agent would be pinged here");
  writeFileSync(path.join(dir, "ctx", "s.json"), JSON.stringify({ used_percentage: 50, context_window_size: 1_000_000 }));
  assert.match(run({ session_id: "s" }, env), /heads-up/);
  rmSync(dir, { recursive: true, force: true });
});

test("token ledger stamp: SISO_TASK marks the session once (again only on change), with its alloc; none without it", async () => {
  const { stampTask, parseAlloc } = await import("../hooks/context-ping.mjs");
  const dir = mkdtempSync(path.join(tmpdir(), "cping-task-"));
  const cfg = { state: dir }, marks = path.join(dir, "m", "marks.jsonl");
  const env = { SISO_TASK: "so-020", SISO_ALLOC: "credits:600", SISO_TASK_STATE: path.join(dir, "m") };
  assert.equal(stampTask({ session_id: "s" }, {}, cfg), null);
  assert.deepEqual(stampTask({ session_id: "c" }, { ...env, SISO_CHAIN: "opus:spec, luna:build" }, cfg).chain, ["opus:spec", "luna:build"]);
  assert.deepEqual(stampTask({ session_id: "s" }, env, cfg).alloc, { credits: 600 });
  assert.equal(stampTask({ session_id: "s" }, env, cfg), null, "once per session");
  assert.equal(stampTask({ session_id: "s" }, { ...env, SISO_TASK: "so-021", SISO_ALLOC: "" }, cfg).task, "so-021");
  const rows = readFileSync(marks, "utf8").trim().split("\n").map(l => JSON.parse(l));
  assert.deepEqual(rows.filter(r => r.session === "s").map(r => [r.session, r.task, r.source, r.chain]), [["s", "so-020", "env", null], ["s", "so-021", "env", null]]);
  assert.deepEqual([parseAlloc("tokens:3M"), parseAlloc("usd:2.5"), parseAlloc("lots")], [{ tokens: 3e6 }, { usd: 2.5 }, null]);
  rmSync(dir, { recursive: true, force: true });
});

test("hosted chats (Agent Base, no status line): pings and burn samples come from the host record (FLEET-COST, 7 Oct)", async () => {
  const { sampleBurn } = await import("../hooks/context-ping.mjs");
  const dir = mkdtempSync(path.join(tmpdir(), "cping-host-"));
  const hosts = path.join(dir, "hosts");
  mkdirSync(hosts, { recursive: true });
  writeFileSync(path.join(hosts, "w7_p49.json"), JSON.stringify({
    name: "OPERATOR-UI", session: "h1", configDir: "/p/claude-siso-3", ctx: { used: 394_000, window: 1_000_000, pct: 39, at: 5 },
    rateLimits: { five_hour: { used_percentage: 62, resets_at: "2026-10-06T17:09:59Z" }, seven_day: { used_percentage: 13, resets_at: "2026-10-13T12:59:59Z" }, at: 1_000 } }));
  const env = { CONTEXT_PING_STATE: dir, AB_HOSTS_DIR: hosts, SISO_CONTEXT_CAPS: path.join(dir, "none.json"), HERDR_BIN: "/nonexistent" };
  assert.match(run({ session_id: "h1" }, env), /Context heads-up: you're at 39% context \(394k tokens\)/);
  assert.equal(sampleBurn({ state: dir, hosts }, "h1"), null, "run already sampled these numbers");
  const row = JSON.parse(readFileSync(path.join(dir, "burn", "samples.jsonl"), "utf8").trim());
  assert.equal(row.h5, 62);
  assert.equal(row.profile, "/p/claude-siso-3");
  assert.equal(run({ session_id: "nobody" }, env), null, "no ctx file and no host record: quiet");
  rmSync(dir, { recursive: true, force: true });
});
