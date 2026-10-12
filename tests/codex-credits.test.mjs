import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, utimesSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/codex-credits", import.meta.url).pathname;
const tc = model => JSON.stringify({ timestamp: "2026-10-02T01:00:00Z", type: "turn_context", payload: { model } });
const rec = (ts, input, cached, output) => JSON.stringify({ timestamp: ts, type: "token_usage_record",
  payload: { usage: { input_tokens: input, cached_input_tokens: cached, output_tokens: output } } });

test("prices each response by its turn's exact model and its own local day; Sol shows both cached rates", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "cc-"));
  mkdirSync(path.join(dir, "2026", "10", "01"), { recursive: true });
  // One long session started 1 Oct: Luna, then Sol, then an unpriced model, with usage on 1 Oct (before the budget) and 2 Oct.
  writeFileSync(path.join(dir, "2026", "10", "01", "rollout-a.jsonl"), [
    tc("gpt-6-luna"),
    rec("2026-10-01T10:00:00Z", 9_000_000, 0, 0),                  // 1 Oct 17:00 +07: before since, ignored
    rec("2026-10-02T02:00:00Z", 2_000_000, 1_000_000, 100_000),   // Luna: 1M x 2.5 + 1M x 0.25 + 0.1M x 12.5 = 4.0
    tc("gpt-6.1-sol"),
    rec("2026-10-02T03:00:00Z", 1_000_000, 1_000_000, 10_000),    // Sol: 0 + 1M x (2.5|5) + 0.01M x 250 = 5.0|7.5
    tc("gpt-5.6-luna"),
    rec("2026-10-02T04:00:00Z", 500_000, 0, 1_000),                // unpriced: not "Luna" by substring
  ].join("\n") + "\n");
  const env = { ...process.env, CODEX_SESSIONS: dir, TZ: "Asia/Ho_Chi_Minh", CODEX_CREDIT_HOSTS: "" };
  const r = JSON.parse(execFileSync(bin, ["--json"], { env, encoding: "utf8" }));
  assert.deepEqual(r.by_model["gpt-6-luna"].credits, [4, 4]);
  assert.deepEqual(r.by_model["gpt-6.1-sol"].credits, [5, 7.5]);
  assert.equal(r.by_model["gpt-5.6-luna"].credits, null);
  assert.deepEqual(r.unpriced, ["gpt-5.6-luna"]);
  assert.deepEqual(r.to_date_credits, [9, 11.5]);
  assert.deepEqual(r.left, [59988.5, 59991]);
  const text = execFileSync(bin, [], { env, encoding: "utf8" });
  assert.match(text, /to date 9\.0-11\.5 of 60,000/);
  assert.match(text, /Sol\s+5\.0-7\.5 credits/);
  assert.match(text, /unpriced models .*gpt-5\.6-luna/);
  rmSync(dir, { recursive: true, force: true });
});

const bal = (ts, b) => JSON.stringify({ timestamp: ts, type: "event_msg", payload: { type: "token_count",
  rate_limits: { primary: { used_percent: 100 }, credits: { has_credits: true, balance: String(b) }, plan_type: "pro" } } });

test("the real balance: newest sample from any machine; a day's spend is its drop; staleness is not a top-up; an overnight drop is a gap", () => {
  const home = mkdtempSync(path.join(tmpdir(), "ccb-"));
  const mk = (name, lines) => { const d = path.join(home, name, "2026", "10", "02"); mkdirSync(d, { recursive: true });
    writeFileSync(path.join(d, "rollout-x.jsonl"), lines.join("\n") + "\n"); return path.join(home, name); };
  // Laptop: 1 Oct 22:00 +07 at 1000; nothing overnight; 2 Oct 14:00 at 900, 15:00 at 880. The mini (via ssh): 14:30 at 895
  // (stale by a few credits after the laptop's 900? no: lower, real), 15:10 at 884 (stale: above the laptop's 880 at 15:00, ignored),
  // 15:30 at 850 with Sol tokens. Today's spend = 900 - 850 = 50; the 100 between 1 Oct 22:00 and 2 Oct 14:00 is a gap.
  const local = mk("laptop", [bal("2026-10-01T15:00:00Z", 1000), tc("gpt-6-luna"), bal("2026-10-02T07:00:00Z", 900),
    rec("2026-10-02T07:00:00Z", 1_000_000, 0, 0), bal("2026-10-02T08:00:00Z", 880)]);
  const mini = mk("mini", [tc("gpt-6.1-sol"), bal("2026-10-02T07:30:00Z", 895), bal("2026-10-02T08:10:00Z", 884),
    rec("2026-10-02T08:30:00Z", 0, 0, 1_000), bal("2026-10-02T08:30:00Z", 850)]);
  const fb = path.join(home, "bin"); mkdirSync(fb);
  // A fake ssh: runs the shipped script (stdin) here, with the mini's sessions, exactly as the real host would.
  writeFileSync(path.join(fb, "ssh"), `#!/bin/sh\nwhile [ "$1" != python3 ]; do shift; done; shift\nCODEX_SESSIONS="${mini}" exec python3 "$@"\n`);
  chmodSync(path.join(fb, "ssh"), 0o755);
  for (const f of [local, mini]) utimesSync(path.join(f, "2026", "10", "02", "rollout-x.jsonl"), new Date(), new Date());
  const env = { ...process.env, CODEX_SESSIONS: local, TZ: "Asia/Ho_Chi_Minh", CODEX_CREDIT_HOSTS: "mini", PATH: `${fb}:${process.env.PATH}` };
  const r = JSON.parse(execFileSync(bin, ["--json"], { env, encoding: "utf8" }));
  const b = r.balance;
  assert.equal(b.now, 850); assert.equal(b.from, "mini");
  assert.equal(b.by_day["2026-10-02"], 50);
  assert.deepEqual(b.gaps, [{ from: "2026-10-01T15:00:00Z", to: "2026-10-02T07:00:00Z", credits: 100 }]);
  assert.deepEqual(b.rises, []);
  assert.deepEqual(r.machines.map(m => [m.host, m.error]), [["local", null], ["mini", null]]);
  assert.ok(r.by_model["gpt-6.1-sol"], "the mini's Sol tokens are counted");
  const local1 = JSON.parse(execFileSync(bin, ["--json", "--local"], { env, encoding: "utf8" }));
  assert.equal(local1.balance.now, 880); assert.equal(local1.by_model["gpt-6.1-sol"], undefined);
  rmSync(home, { recursive: true, force: true });
});
