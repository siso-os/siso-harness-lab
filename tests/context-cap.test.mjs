import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const root = new URL("..", import.meta.url).pathname;
const dir = mkdtempSync(path.join(tmpdir(), "ccap-"));
const caps = path.join(dir, "caps.json");
writeFileSync(caps, JSON.stringify({
  default: "220k", lead: 100000,
  tiers: { worker: 200000, builder: 300000, owner: 400000, heavy: 600000 },
  agents: { "AUTO-VIEWER": "worker", "OPS-UX": "owner" },
}));

// Source the launcher helper the way claude-siso does and print what claude would get.
function cap(args, env = {}) {
  const script = `source "${root}bin/context-cap.sh"; siso_context_cap "$@"; ` +
    `printf '%s|' "\${CONTEXT_PING_AT:-}" "\${SISO_CONTEXT_CAP:-}" "\${SISO_CONTEXT_TIER:-}" "\${CONTEXT_PING_PCT:-}"; ` +
    `for a in \${SISO_ARGS[@]+"\${SISO_ARGS[@]}"}; do printf '<%s>' "$a"; done`;
  // Hermetic: the session running the tests was itself launched with a cap (SISO_CONTEXT_CAP/TIER/SOURCE, CONTEXT_PING_*).
  const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(CONTEXT_PING|SISO_CONTEXT|SISO_AGENT_NAME)/.test(k)));
  return execFileSync("bash", ["-c", script, "x", ...args], { env: { ...clean, SISO_CONTEXT_CAPS: caps, ...env }, encoding: "utf8" });
}

test("an agent's name picks its tier; the heads-up lands lead tokens before the cap", () => {
  assert.equal(cap(["-n", "AUTO-VIEWER", "--resume", "id"]), "100000|200000|worker|80|<-n><AUTO-VIEWER><--resume><id>");
  assert.equal(cap(["--name", "ops-ux"]), "300000|400000|owner|80|<--name><ops-ux>", "names match case-insensitively");
});

test("unknown or missing name gets the default 220k", () => {
  assert.equal(cap(["-n", "NEW-AGENT"]), "120000|220000|default|80|<-n><NEW-AGENT>");
  assert.equal(cap([]), "120000|220000|default|80|");
});

test("--cap TIER or tokens overrides the name and is not passed to claude", () => {
  assert.equal(cap(["-n", "AUTO-VIEWER", "--cap", "heavy", "hi"]), "500000|600000|heavy|80|<-n><AUTO-VIEWER><hi>");
  assert.equal(cap(["--cap=450k"]), "350000|450000|custom|80|");
  assert.equal(cap(["--cap", "250000"]), "150000|250000|custom|80|");
});

test("an explicit CONTEXT_PING_AT wins; a bad cap or missing file changes nothing and never fails the launch", () => {
  assert.equal(cap(["-n", "OPS-UX"], { CONTEXT_PING_AT: "90000" }), "90000||||<-n><OPS-UX>");
  assert.equal(cap(["--cap", "lots", "-p", "q"]), "||||<-p><q>");
  assert.equal(cap(["-n", "OPS-UX"], { SISO_CONTEXT_CAPS: path.join(dir, "none.json"), HOME: dir }).split("|")[1], "500000",
    "falls back to the repo's caps file, where OPS-UX is an owner");
});

test("--task and --alloc export the ledger stamp and are not passed to claude", () => {
  const script = `source "${root}bin/context-cap.sh"; siso_context_cap "$@"; printf '%s|%s|%s|' "$SISO_TASK" "$SISO_ALLOC" "$SISO_CHAIN"; ` +
    `for a in \${SISO_ARGS[@]+"\${SISO_ARGS[@]}"}; do printf '<%s>' "$a"; done`;
  const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(CONTEXT_PING|SISO_)/.test(k)));
  const out = execFileSync("bash", ["-c", script, "x", "-n", "B", "--task", "so-020", "--alloc=usd:5", "--chain", "opus:spec,luna:build", "-p", "hi"],
    { env: { ...clean, SISO_CONTEXT_CAPS: caps }, encoding: "utf8" });
  assert.equal(out, "so-020|usd:5|opus:spec,luna:build|<-n><B><-p><hi>");
});

test("the repo caps file parses and every agent names a real tier", () => {
  const c = JSON.parse(execFileSync("cat", [`${root}config/context-caps.json`], { encoding: "utf8" }));
  for (const [a, t] of Object.entries(c.agents)) assert.ok(t in c.tiers, `${a} -> ${t}`);
  assert.equal(c.tiers.worker, 200000);
  assert.equal(c.tiers.heavy, 500000);
  assert.equal(c.tiers.owner, 500000);
  assert.equal(c.tiers.builder, 300000);
  assert.equal(c.default, "300k");
});

test.after(() => rmSync(dir, { recursive: true, force: true }));

test("claude-siso and claude-siso-3 hand claude the cap env and strip --cap", () => {
  const home = mkdtempSync(path.join(tmpdir(), "ccap-home-"));
  execFileSync("mkdir", ["-p", `${home}/.local/bin`]);
  writeFileSync(`${home}/.local/bin/claude`, `#!/bin/sh\necho "$CONTEXT_PING_AT $SISO_CONTEXT_TIER $*"\n`, { mode: 0o755 });
  // SISO_ONE_HOME=0: this checks caps; the one-home token path has its own test (one-home.test.mjs) and needs the real Keychain.
  const clean = { ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(CONTEXT_PING|SISO_CONTEXT|CLAUDE_CODE_SUBAGENT)/.test(k))), SISO_ONE_HOME: "0", SISO_STACK_PLUGIN: "" };
  for (const l of ["claude-siso", "claude-siso-3"]) {
    const out = execFileSync(`${root}bin/${l}`, ["-n", "AUTO-VIEWER", "--cap", "heavy", "--resume", "x"],
      { env: { ...clean, HOME: home, SISO_FULL_BOOT: "1" }, encoding: "utf8" }).trim();
    assert.equal(out, "450000 heavy -n AUTO-VIEWER --resume x", l);
    const lean = execFileSync(`${root}bin/${l}`, ["-n", "OPS-UX"], { env: { ...clean, HOME: home }, encoding: "utf8" }).trim();
    assert.equal(lean, `450000 owner --no-chrome --settings ${root}config/agent-boot.json -n OPS-UX`, `${l} lean boot`);
    const own = execFileSync(`${root}bin/${l}`, ["--chrome", "--settings", "s.json"], { env: { ...clean, HOME: home }, encoding: "utf8" }).trim();
    assert.equal(own, "250000 default --chrome --settings s.json", "the caller's --chrome/--settings win");
  }
  rmSync(home, { recursive: true, force: true });
});

// 3 Oct (Shaan: "that nine hundred k thing shouldn't have happened"): the cap is hard. Claude Code auto-compacts at
// CLAUDE_AUTOCOMPACT_PCT_OVERRIDE percent of a 1M window; SISO_CONTEXT_HARD=0 goes back to ping-only.
test("the cap is a hard auto-compact point: 300k default = 30%, owner 500k = 50%, worker 200k = 20%, off with SISO_CONTEXT_HARD=0", () => {
  const run = (args, env = {}) => execFileSync("bash", ["-c", `source ${root}bin/context-cap.sh; siso_context_cap "$@"; echo "\${CLAUDE_AUTOCOMPACT_PCT_OVERRIDE:-none}"`, "x", ...args],
    { env: { ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(CONTEXT_PING|SISO_CONTEXT|CLAUDE_AUTOCOMPACT)/.test(k))), ...env }, encoding: "utf8" }).trim();
  assert.equal(run([]), "30");
  assert.equal(run(["-n", "EFFICIENCY"]), "50");
  assert.equal(run(["-n", "AUTO-VIEWER"]), "20");
  assert.equal(run(["--cap", "450k"]), "45");
  assert.equal(run(["-n", "EFFICIENCY"], { SISO_CONTEXT_HARD: "0" }), "none");
  assert.equal(run(["--cap", "300k"], { SISO_CONTEXT_WINDOW: "200000" }), "95", "a 200k model never gets a cap past its window");
});
