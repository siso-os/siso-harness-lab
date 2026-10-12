import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/spend-report", import.meta.url).pathname;

test("spend goes project -> owner -> agent -> the plan item named in the agent's next report; the rest stays visible", () => {
  const d = mkdtempSync(path.join(tmpdir(), "spend-"));
  const day = "2026-10-02";
  const at = hhmm => `${day}T${hhmm}:00+07:00`;
  // Claude: STREAM-B (worker of STREAMING-CLAUDE, HALO) spends two Opus steps, one before each report.
  mkdirSync(path.join(d, "claude", "proj"), { recursive: true });
  const step = (hhmm, id, cr) => JSON.stringify({ type: "assistant", timestamp: at(hhmm), agentName: "STREAM-B", cwd: "/x/partners/halo/oracle",
    message: { id, model: "claude-opus-5-5", usage: { cache_read_input_tokens: cr } } });
  writeFileSync(path.join(d, "claude", "proj", "s1.jsonl"), [step("10:00", "m1", 1e6), step("11:00", "m2", 2e6), step("13:00", "m3", 1e6)].join("\n") + "\n");
  // Plans and reports: 10:30 names sgl-001 and is DONE; 11:30 names sgl-002 (not finished); nothing after 13:00.
  mkdirSync(path.join(d, "plan"));
  writeFileSync(path.join(d, "plan", "streaming.json"), JSON.stringify({ owner: "STREAMING-CLAUDE", project: "HALO",
    items: [{ id: "sgl-001", title: "first" }, { id: "sgl-002", title: "second" }] }));
  writeFileSync(path.join(d, "inbox.log"), [
    `${day} 10:30 +0700 STREAM-B: sgl-001 DONE, proofs attached`,
    `${day} 11:30 +0700 STREAM-B → STREAMING-CLAUDE: sgl-002 halfway; ab-999 is not a plan id`,
  ].join("\n") + "\n");
  writeFileSync(path.join(d, "registry.json"), JSON.stringify({ agents: { "STREAM-B": { project: "HALO", owner: "STREAMING-CLAUDE", kind: "worker" } } }));
  mkdirSync(path.join(d, "codex"));
  const env = { ...process.env, TZ: "Asia/Ho_Chi_Minh", PLAN_REPORT_ROOTS: path.join(d, "claude"), CODEX_SESSIONS: path.join(d, "codex"),
    SPEND_REGISTRY: path.join(d, "registry.json"), SPEND_INBOXES: path.join(d, "inbox.log"), SPEND_PLANS: path.join(d, "plan", "*.json"),
    SPEND_A0_TASKS: path.join(d, "none.json"), SPEND_STATE: path.join(d, "state"), PATH: `${d}/nobin:/usr/bin:/bin` };
  const r = JSON.parse(execFileSync(bin, ["--day", day, "--json"], { env, encoding: "utf8" }));
  assert.equal(r.claude_usd_equiv, 0.8);                       // 4M cache-read tokens x $0.2/M (Opus 5.5, config/prices.json)
  const halo = r.projects.find(p => p.project === "HALO");
  assert.equal(halo.owners[0].owner, "STREAMING-CLAUDE");
  assert.equal(halo.owners[0].agents[0].agent, "STREAM-B");
  assert.equal(halo.finished, 1);
  const item = id => r.plan_items.find(x => x.id === id);
  assert.equal(item("sgl-001").claude_usd_equiv, 0.2);         // the 10:00 step
  assert.equal(item("sgl-001").finished, true);
  assert.equal(item("sgl-002").claude_usd_equiv, 0.4);           // the 11:00 step
  assert.equal(item("sgl-002").finished, false);
  assert.equal(item("unattributed:HALO").claude_usd_equiv, 0.2); // 13:00: no later report, shown, not dropped
  assert.equal(r.attributed_to_plan_items, 0.75);
  rmSync(d, { recursive: true, force: true });
});
