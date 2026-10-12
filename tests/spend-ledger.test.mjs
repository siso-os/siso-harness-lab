import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const root = new URL("..", import.meta.url).pathname;
const bin = `${root}bin/spend-ledger`;
const DAY = "2026-10-02";
const at = h => `${DAY}T${String(h).padStart(2, "0")}:00:00Z`; // 05:00Z is midday on the day in any zone from -5 to +14
const J = x => x.map(o => JSON.stringify(o)).join("\n") + "\n";

function fixture() {
  const home = mkdtempSync(path.join(tmpdir(), "ledger-"));
  const proj = path.join(home, "claude", "-x"); mkdirSync(proj, { recursive: true });
  const asst = (h, id, model, u) => ({ type: "assistant", timestamp: at(h), message: { id, model, usage: u } });
  const U = { input_tokens: 1000, cache_creation_input_tokens: 10_000, cache_read_input_tokens: 100_000, output_tokens: 2000,
    cache_creation: { ephemeral_1h_input_tokens: 10_000, ephemeral_5m_input_tokens: 0 } };
  // S1: launched with SISO_TASK=test-ledger-2, spawns two sub-agents.
  writeFileSync(path.join(proj, "s1.jsonl"), J([
    { type: "user", timestamp: at(4), agentName: "BUILDER", cwd: "/w/siso-internal-labs/x", message: { content: "build it" } },
    asst(4, "m1", "claude-opus-5-5", U), asst(5, "m1", "claude-opus-5-5", U), asst(5, "m2", "claude-opus-5-5", U)]));
  const subs = path.join(proj, "s1", "subagents"); mkdirSync(subs, { recursive: true });
  for (const [i, desc] of [["a1", "Mine Whitebox for hub ideas"], ["a2", "Check the tests"]]) {
    writeFileSync(path.join(subs, `agent-${i}.jsonl`), J([asst(5, `sub-${i}`, "claude-sonnet-5-5", { input_tokens: 500, output_tokens: 100 })]));
    writeFileSync(path.join(subs, `agent-${i}.meta.json`), JSON.stringify({ agentType: "general-purpose", description: desc, model: "sonnet" }));
  }
  // S1 also appears under an old folder name (a link in real life; a copy here): its messages count once.
  mkdirSync(path.join(home, "claude", "-old")); writeFileSync(path.join(home, "claude", "-old", "s1.jsonl"), readFileSync(path.join(proj, "s1.jsonl")));
  // S2: an owner that declares a task mid-session; S3: an agent whose later inbox line names a plan id; S4: nothing.
  writeFileSync(path.join(proj, "s2.jsonl"), J([{ type: "user", timestamp: at(4), agentName: "OWNER", message: { content: "hi" } },
    asst(4, "o1", "claude-opus-5-5", U), asst(6, "o2", "claude-opus-5-5", U)]));
  writeFileSync(path.join(proj, "s3.jsonl"), J([{ type: "user", timestamp: at(4), agentName: "GUESSY", message: { content: "go" } },
    asst(4, "g1", "claude-opus-5-5", U)]));
  writeFileSync(path.join(proj, "s4.jsonl"), J([{ type: "user", timestamp: at(4), cwd: "/w/partners/halo/x", message: { content: "go" } },
    asst(4, "n1", "claude-opus-5-5", U)]));
  // A Codex worker whose brief starts "TASK: test-ledger-1".
  const cs = path.join(home, "codex", "2026", "10", "02"); mkdirSync(cs, { recursive: true });
  writeFileSync(path.join(cs, "rollout-2026-10-02T12-00-00-th1.jsonl"), J([
    { timestamp: at(4), type: "session_meta", payload: { id: "th1", cwd: "/w/x" } },
    { timestamp: at(4), type: "turn_context", payload: { model: "gpt-6-luna", cwd: "/w/x" } },
    { timestamp: at(4), type: "response_item", payload: { type: "message", role: "user", content: [{ type: "input_text", text: "# AGENTS.md instructions" }] } },
    { timestamp: at(4), type: "response_item", payload: { type: "message", role: "user", content: [{ type: "input_text", text: "TASK: test-ledger-1\nCHAIN: opus:spec,luna:build,opus:review\n\nDo it" }] } },
    { timestamp: at(5), type: "token_usage_record", payload: { usage: { input_tokens: 100_000, cached_input_tokens: 80_000, output_tokens: 4000, reasoning_output_tokens: 1000 } } }]));
  // An a0-team worker (named a0-<tier>-<task> at launch) from before briefs carried a TASK line.
  writeFileSync(path.join(cs, "rollout-2026-10-02T12-00-00-th2.jsonl"), J([
    { timestamp: at(4), type: "session_meta", payload: { id: "th2", cwd: "/w/x" } },
    { timestamp: at(4), type: "turn_context", payload: { model: "gpt-6.1-sol", cwd: "/w/x" } },
    { timestamp: at(5), type: "token_usage_record", payload: { usage: { input_tokens: 1000, cached_input_tokens: 0, output_tokens: 10 } } }]));
  mkdirSync(path.join(home, "sr")); writeFileSync(path.join(home, "sr", "session-names.json"), JSON.stringify({ th2: "a0-sol-ab-9" }));
  const state = path.join(home, "task"); mkdirSync(state);
  writeFileSync(path.join(state, "marks.jsonl"), J([
    { at: at(4), session: "s1", task: "test-ledger-2", alloc: { usd: 1 }, source: "env", chain: ["opus:spec", "sonnet:research", "opus:review"] },
    { at: `${DAY}T05:30:00Z`, session: "s2", task: "so-020", alloc: null, source: "declared" }]));
  const plans = path.join(home, "repo", ".agents", "plan"); mkdirSync(plans, { recursive: true });
  writeFileSync(path.join(plans, "OWNER.json"), JSON.stringify({ owner: "OWNER", project: "LABS", items: [
    { id: "so-020", title: "Token ledger", status: "building" }, { id: "so-007", title: "Old", status: "checked", alloc: { tokens: 100000 } }] }, null, 2));
  const inbox = path.join(home, "inbox.log");
  writeFileSync(inbox, `${DAY} 23:50 +0700 GUESSY: so-007 shipped\n`);
  const out = path.join(home, "out"); mkdirSync(out);
  writeFileSync(path.join(out, "LEDGER.jsonl"), "");
  const env = { ...process.env, PLAN_REPORT_ROOTS: path.join(home, "claude"), CODEX_SESSIONS: path.join(home, "codex"),
    SPEND_LEDGER_DIR: out, SISO_TASK_STATE: state, SPEND_REGISTRY: path.join(home, "none.json"), SPEND_INBOXES: inbox,
    SPEND_PLANS: path.join(plans, "*.json"), SPEND_STATE: path.join(home, "sr"), SPEND_A0_TASKS: path.join(home, "none.json") };
  return { home, env, out, plans };
}

const run = (env, ...a) => spawnSync(bin, a, { env, encoding: "utf8" });
const rows = out => readFileSync(path.join(out, "spend.jsonl"), "utf8").trim().split("\n").map(l => JSON.parse(l));

test("build: stamped Claude task with its two sub-agents as rows, a TASK-line Codex run, a mid-session switch, guessed and none", () => {
  const { env, out } = fixture();
  const r = run(env, "build", "--day", DAY, "--json");
  assert.equal(r.status, 0, r.stderr);
  const all = rows(out);
  const t2 = all.filter(x => x.task === "test-ledger-2");
  assert.equal(t2.length, 3, "parent + 2 sub-agents under one task");
  assert.deepEqual(t2.map(x => x.kind).sort(), ["main", "subagent", "subagent"]);
  assert.ok(t2.every(x => x.attribution === "stamped" && x.actor === "BUILDER"));
  const main = t2.find(x => x.kind === "main");
  assert.equal(main.steps, 2, "message m1 is written twice and the transcript is under two folders: counted once each");
  // Opus 5.5 per step: 1000*4 + 10000*8 (1h write) + 100000*0.2 + 2000*20 = 144,000 / 1e6 = $0.144
  assert.equal(main.cost.usd_equiv, 0.288);
  assert.deepEqual(main.alloc, { usd: 1 });
  const subs = t2.filter(x => x.kind === "subagent");
  assert.deepEqual(subs.map(x => x.sub.description).sort(), ["Check the tests", "Mine Whitebox for hub ideas"]);
  assert.ok(subs.every(x => x.model === "claude-sonnet-5-5" && x.parent === "s1" && x.cost.usd_equiv === 0.002));
  const cx = all.find(x => x.task === "test-ledger-1");
  assert.equal(cx.attribution, "stamped");
  assert.equal(cx.model, "gpt-6-luna");
  assert.deepEqual(cx.tokens, { in: 20000, cw: 0, cr: 80000, out: 4000, reasoning: 1000 });
  assert.deepEqual(cx.cost.credits, [0.12, 0.12], "20k*2.5 + 80k*0.25 + 4k*12.5 = 120,000 / 1e6");
  const owner = all.filter(x => x.actor === "OWNER").map(x => [x.task, x.attribution]).sort();
  assert.deepEqual(owner, [["so-020", "stamped"], ["unattributed:Unassigned", "none"]].sort(), "the switch applies from its time");
  assert.deepEqual(all.filter(x => x.actor === "GUESSY").map(x => [x.task, x.attribution]), [["so-007", "guessed"]]);
  assert.equal(all.find(x => x.session === "s4").task, "unattributed:HALO");
  assert.deepEqual(t2.map(x => x.chain.join(">")), Array(3).fill("opus:spec>sonnet:research>opus:review"), "chain from the stamp");
  assert.deepEqual(cx.chain, ["opus:spec", "luna:build", "opus:review"], "chain from the brief's CHAIN: line");
  assert.deepEqual(all.find(x => x.session === "th2").chain, ["opus:spec", "sol:build", "opus:review"], "a0-team's chain");
  assert.equal(all.find(x => x.session === "s4").chain, null);
  assert.deepEqual(["task", "attribution", "actor"].map(k => all.find(x => x.session === "th2")[k]), ["ab-9", "stamped", "a0-sol-ab-9"]);
  run(env, "build", "--day", DAY);
  assert.equal(rows(out).length, all.length, "a rebuild replaces the day's rows");
});

test("verdicts: bad needs a fix and files it (LEDGER row + plan item); good needs a standard; the widget lists them", () => {
  const { env, out, plans } = fixture();
  run(env, "build", "--day", DAY);
  assert.notEqual(run(env, "verdict", "so-007", "--verdict", "bad", "--outcome", "reworked", "--why", "x").status, 0, "bad without --fix");
  assert.notEqual(run(env, "verdict", "test-ledger-2", "--verdict", "good", "--outcome", "done", "--why", "x").status, 0, "good without --standard");
  let r = run(env, "verdict", "so-007", "--verdict", "bad", "--outcome", "reworked", "--why", "Luna missed the look twice",
    "--fix", "brief must name the reference screenshot", "--plan", path.join(plans, "OWNER.json"), "--by", "A0", "--json");
  assert.equal(r.status, 0, r.stderr);
  const v = JSON.parse(r.stdout);
  assert.equal(v.vs_alloc, 1.13, "113,000 tokens against an alloc of 100,000 on the plan item");
  assert.equal(v.plan_ref, "OWNER.json#so-021");
  const fix = JSON.parse(readFileSync(path.join(out, "LEDGER.jsonl"), "utf8").trim());
  assert.deepEqual([fix.task, fix.status, fix.fix], ["so-007", "open", "brief must name the reference screenshot"]);
  const plan = JSON.parse(readFileSync(path.join(plans, "OWNER.json"), "utf8"));
  assert.equal(plan.items.at(-1).status, "asked");
  r = run(env, "verdict", "test-ledger-2", "--verdict", "good", "--outcome", "done", "--why", "two cheap Sonnet sub-agents did the sweep",
    "--standard", "sweeps go to Sonnet sub-agents", "--link", "brain/estate.md", "--by", "A0", "--kind", "asap-judgment", "--json");
  assert.equal(JSON.parse(r.stdout).vs_alloc, 0.29, "$0.292 against usd:1 from the launch stamp");
  assert.deepEqual(JSON.parse(r.stdout).chain, ["opus:spec", "sonnet:research", "opus:review"], "verdict takes the stamped chain");
  assert.notEqual(run(env, "verdict", "test-ledger-1", "--verdict", "ok", "--outcome", "done", "--why", "x", "--kind", "someday").status, 0);
  run(env, "verdict", "test-ledger-1", "--verdict", "ok", "--outcome", "done", "--why", "fine", "--kind", "asap-spec", "--chain", "luna:build,opus:review");
  const ch = JSON.parse(run(env, "chains", "--days", "3650", "--json").stdout).chains;
  assert.deepEqual(ch.map(c => [c.kind, c.chain, c.tasks, c.good, c.bad]), [
    ["asap-judgment", "opus:spec > sonnet:research > opus:review", 1, 1, 0], ["asap-spec", "luna:build > opus:review", 1, 0, 0],
    ["unknown", "unstamped", 1, 0, 1]]);
  const w = JSON.parse(run(env, "widget", "--days", "3650", "--json").stdout);
  assert.equal(w.chains.length, 3);
  assert.equal(w.worst[0].task, "so-007", "a bad verdict ranks first");
  assert.equal(w.worst.find(c => c.task === "test-ledger-2").subagents, 2);
  assert.deepEqual(w.standardized.map(s => s.what), ["sweeps go to Sonnet sub-agents"]);
  assert.deepEqual(w.open_fixes.map(f => f.task), ["so-007"]);
  assert.ok(w.worst.every(c => !c.task.startsWith("unattributed:")));
});

test("siso-task start/stop write marks for this Claude session; a bad alloc is refused", () => {
  const { env, home } = fixture();
  const st = (...a) => spawnSync(`${root}bin/siso-task`, a, { env: { ...env, CLAUDE_CODE_SESSION_ID: "sx" }, encoding: "utf8" });
  assert.equal(st("start", "so-020", "--alloc", "credits:600").status, 0);
  assert.equal(st("start", "so-020", "--alloc", "lots").status, 2);
  assert.equal(st("stop").status, 0);
  const m = readFileSync(path.join(home, "task", "marks.jsonl"), "utf8").trim().split("\n").map(l => JSON.parse(l)).filter(x => x.session === "sx");
  assert.deepEqual(m.map(x => [x.task, x.alloc, x.source]), [["so-020", { credits: 600 }, "declared"], [null, null, "declared"]]);
  assert.equal(spawnSync(`${root}bin/siso-task`, ["show"], { env: { ...env, CLAUDE_CODE_SESSION_ID: "", HERDR_PANE_ID: "" }, encoding: "utf8" }).status, 3);
});

test("codex-run --task: the brief starts TASK:, the thread is marked, the log row carries task, alloc and thread", () => {
  const { home } = fixture();
  const fake = path.join(home, "codex-bin");
  writeFileSync(fake, `#!/bin/sh\nfor a; do last="$a"; done\nprintf '%s' "$last" > "${home}/brief.txt"\necho "$SISO_TASK" > "${home}/env.txt"\n` +
    `while [ "$1" != "-o" ]; do shift; done\nprintf 'RETURN\\nSTATUS: done - ok\\n' > "$2"\n` +
    `echo '{"type":"thread.started","thread_id":"th-9"}'\necho '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}'\n`, { mode: 0o755 });
  const env = { ...process.env, CODEX_BIN: fake, CODEX_RUN_STATE: path.join(home, "cr"), SISO_TASK_STATE: path.join(home, "task") };
  const r = spawnSync(`${root}bin/codex-run`, ["--task", "test-ledger-1", "--alloc", "credits:50", "--chain", "opus:spec,luna:build", "do the thing"], { env, encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(readFileSync(path.join(home, "brief.txt"), "utf8"), /^TASK: test-ledger-1\n\ndo the thing/);
  assert.equal(readFileSync(path.join(home, "env.txt"), "utf8").trim(), "test-ledger-1");
  const log = JSON.parse(readFileSync(path.join(home, "cr", "log.jsonl"), "utf8").trim());
  assert.deepEqual([log.task, log.alloc, log.thread, log.input_tokens], ["test-ledger-1", { credits: 50 }, "th-9", 10]);
  const mark = readFileSync(path.join(home, "task", "marks.jsonl"), "utf8").trim().split("\n").map(l => JSON.parse(l)).find(m => m.session === "th-9");
  assert.deepEqual([mark.task, mark.source, mark.chain], ["test-ledger-1", "codex-run", ["opus:spec", "luna:build"]]);
  assert.deepEqual(log.chain, ["opus:spec", "luna:build"]);
  const plain = spawnSync(`${root}bin/codex-run`, ["no task"], { env: { ...env, SISO_TASK: "" }, encoding: "utf8" });
  assert.equal(plain.status, 0);
  assert.equal(readFileSync(path.join(home, "brief.txt"), "utf8").startsWith("no task"), true, "no TASK line without a task");
});

test("plan-report prices from the one table: Opus 5.5 at 4/8/0.2/20, aliases mapped", () => {
  const py = `import importlib.machinery as m, importlib.util as u
l=m.SourceFileLoader('pr','${root}scripts/plan-report.py');x=u.module_from_spec(u.spec_from_loader('pr',l));l.exec_module(x)
print(x.PRICE[x.family('claude-opus-5-5')], x.PRICE[x.family('sonnet')])`;
  assert.equal(execFileSync("python3", ["-c", py], { encoding: "utf8" }).trim(), "(4, 8, 0.2, 20) (2, 4, 0.2, 10)");
  assert.ok(existsSync(`${root}config/prices.json`));
});

test("split: Codex credits per model for a day against the 80/20 target, with who spent each", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "split-"));
  const row = (model, actor, lo, hi, day = "2026-10-02") => JSON.stringify({ day, harness: "codex", model, actor, task: "t", cost: { usd_equiv: 0, credits: [lo, hi] } });
  writeFileSync(path.join(dir, "spend.jsonl"), [row("gpt-6.1-sol", "sol-a", 300, 400), row("gpt-6.1-sol", "sol-b", 10, 20),
    row("gpt-6-luna", "luna-a", 100, 100), row("gpt-6-luna", "luna-a", 9, 9, "2026-10-01"),
    JSON.stringify({ day: "2026-10-02", harness: "claude", model: "claude-opus-5-5", actor: "x", task: "t", cost: { usd_equiv: 5, credits: [0, 0] } })].join("\n") + "\n");
  writeFileSync(path.join(dir, "sol.jsonl"), JSON.stringify({ at: "2026-10-02T21:00:00+07:00", by: "codex-run", name: "sol-a", why: "heavier coding" }) + "\n"
    + JSON.stringify({ at: "2026-10-01T21:00:00+07:00", by: "hand", name: "old", why: "yesterday" }) + "\n");
  mkdirSync(path.join(dir, "solstate"), { recursive: true });
  writeFileSync(path.join(dir, "solstate", "log.jsonl"), readFileSync(path.join(dir, "sol.jsonl")));
  const r = spawnSync(bin, ["split", "--day", "2026-10-02", "--json"], { env: { ...process.env, SPEND_LEDGER_DIR: dir, CODEX_SOL_STATE: path.join(dir, "solstate") }, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  const v = JSON.parse(r.stdout);
  assert.deepEqual(v.credits, [410, 520], "that day's Codex rows only");
  assert.deepEqual(v.models["gpt-6.1-sol"].credits, [310, 420]);
  assert.equal(v.models["gpt-6.1-sol"].target, 0.2); assert.equal(v.models["gpt-6-luna"].target, 0.8);
  assert.equal(v.models["gpt-6.1-sol"].share, 0.78, "mid of the range: 365 / 465");
  assert.deepEqual(v.models["gpt-6.1-sol"].top[0], ["sol-a", 400]);
  assert.deepEqual(v.sol_reasons, [{ name: "sol-a", by: "codex-run", task: null, why: "heavier coding" }], "that day's reasons only");
});
