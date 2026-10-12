import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/burn-rate", import.meta.url).pathname;

test("Claude % per hour from samples within the current limit window; a reset starts a new line; Codex from rollouts", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "burn-"));
  const now = Date.now();
  const iso = minAgo => new Date(now - minAgo * 60_000).toISOString();
  const prof = path.join(dir, "prof");
  mkdirSync(path.join(dir, "state", "burn"), { recursive: true });
  mkdirSync(path.join(dir, "state", "ctx"), { recursive: true });
  const row = (minAgo, h5, d7, h5r = 9e9) => JSON.stringify({ at: iso(minAgo), profile: prof, h5, h5_reset: h5r, d7, d7_reset: 8e9 });
  writeFileSync(path.join(dir, "state", "burn", "samples.jsonl"), [
    row(90, 70, 10, 1),   // previous 5h window and outside the 60 min window: ignored
    row(50, 5, 20),
    row(20, 10, 21),
  ].join("\n") + "\n");
  // A live session's latest snapshot also counts: 5h at 15%, week 22%, now.
  writeFileSync(path.join(dir, "state", "ctx", "s.json"), JSON.stringify({ at: now, profile: prof,
    rate_limits: { five_hour: { used_percentage: 15, resets_at: 9e9 }, seven_day: { used_percentage: 22, resets_at: 8e9 } } }));
  // Codex: 30 min ago, one Luna response worth 4 credits: 4 credits in the 60 min window = 4/hour.
  const cs = path.join(dir, "codex", "2026", "10", "02"); mkdirSync(cs, { recursive: true });
  writeFileSync(path.join(cs, "rollout-x.jsonl"), [
    JSON.stringify({ timestamp: iso(31), type: "turn_context", payload: { model: "gpt-6-luna" } }),
    JSON.stringify({ timestamp: iso(30), type: "token_usage_record", payload: { usage: { input_tokens: 2e6, cached_input_tokens: 1e6, output_tokens: 1e5 } } }),
  ].join("\n") + "\n");
  const env = { ...process.env, CONTEXT_PING_STATE: path.join(dir, "state"), CODEX_SESSIONS: path.join(dir, "codex"), CODEX_CREDIT_HOSTS: "" };
  const r = JSON.parse(execFileSync(bin, ["--json"], { env, encoding: "utf8" }));
  const c = r.claude.find(x => x.profile.endsWith("prof"));
  assert.equal(c.five_hour.used_pct, 15);
  assert.equal(c.five_hour.samples, 3);
  assert.ok(Math.abs(c.five_hour.pct_per_hour - 12) < 0.1, `5h: (15-5)% over 50 min = 12%/h, got ${c.five_hour.pct_per_hour}`);
  assert.ok(Math.abs(c.five_hour.hours_to_full - 85 / 12) < 0.1);
  assert.ok(Math.abs(c.seven_day.pct_per_hour - 2.4) < 0.05, "week: 2% over 50 min");
  assert.equal(c.five_hour.stale, false);
  assert.deepEqual(r.codex.credits_per_hour, [4, 4]);
  assert.equal(r.codex.by_model_per_hour["gpt-6-luna"][0], 4);
  assert.match(execFileSync(bin, [], { env, encoding: "utf8" }), /5h\s+15% used, 12(\.0)?%\/h, full in 7\.1 h/);
  rmSync(dir, { recursive: true, force: true });
});

test("burn-rate serves Codex and grants from the slow cache (FLEET-COST, 7 Oct: they took 15-50 s, Agent Base waits 30)", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "burn-slow-"));
  mkdirSync(path.join(dir, "state", "burn"), { recursive: true });
  const cached = { credits_per_hour: [1, 2], left: [3, 4], hours_left_at_rate: null, marker: "from-cache" };
  writeFileSync(path.join(dir, "state", "burn", "slow-cache.json"), JSON.stringify({ at: Date.now() / 1000, window_min: 60, codex: cached, grants: [] }));
  const env = { ...process.env, CONTEXT_PING_STATE: path.join(dir, "state"), CODEX_SESSIONS: path.join(dir, "codex"), CODEX_CREDIT_HOSTS: "" };
  const r = JSON.parse(execFileSync(bin, ["--json"], { env, encoding: "utf8" }));
  assert.equal(r.codex.marker, "from-cache");
  assert.ok(r.slow_as_of);
  rmSync(dir, { recursive: true, force: true });
});
