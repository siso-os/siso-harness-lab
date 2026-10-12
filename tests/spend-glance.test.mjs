import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { glance, window5h } from "../hooks/spend-glance.mjs";

test("spend-glance: window, rate, live Opus chats and laptop in one paragraph; never a refusal", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "glance-"));
  mkdirSync(path.join(dir, "burn")); mkdirSync(path.join(dir, "hosts"));
  const now = Date.parse("2026-10-06T16:00:00Z");
  const row = (min, h5) => JSON.stringify({ at: new Date(now - min * 60_000).toISOString(), profile: "/p", h5, h5_reset: "2026-10-06T17:09:59.5Z", d7: 10 });
  writeFileSync(path.join(dir, "burn", "samples.jsonl"), [row(60, 40), row(30, 55), row(0, 70)].join("\n") + "\n");
  writeFileSync(path.join(dir, "hosts", "a.json"), JSON.stringify({ name: "OPERATOR-UI", model: "claude-opus-5-5[1m]", child: "running", state: "working", updatedAt: now, ctx: { used: 394_000 } }));
  writeFileSync(path.join(dir, "hosts", "b.json"), JSON.stringify({ name: "PACK-NAV", model: "gpt-6.1-sol", child: "running", state: "idle", updatedAt: now, ctx: { used: 120_000 } }));
  const w = window5h(path.join(dir, "burn", "samples.jsonl"), "/p", now);
  assert.equal(w.pct, 70);
  assert.equal(w.perH, 30);
  const text = glance({ CONTEXT_PING_STATE: dir, AB_HOSTS_DIR: dir + "/hosts", CLAUDE_CONFIG_DIR: "/p" }, now, 12.5, 88);
  assert.match(text, /70% used, rising 30\.0%\/h, full in ~1h00, resets in 1h10/);
  assert.match(text, /1 Opus chats live \(1 working, 394k context/);
  assert.match(text, /load 12\.5 .* swap 88%/);
  assert.match(text, /not a cap/);
  assert.match(glance({ CONTEXT_PING_STATE: dir + "/none", AB_HOSTS_DIR: dir + "/none" }, now, 1, null), /no fresh 5-hour reading/);
  rmSync(dir, { recursive: true, force: true });
});
