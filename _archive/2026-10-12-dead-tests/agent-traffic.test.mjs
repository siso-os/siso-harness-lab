import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../scripts/agent-traffic.py", import.meta.url).pathname;
const day = new Date().toLocaleDateString("en-CA");
const at = h => new Date(`${day}T${h}:00`).toISOString();  // local time today

// One session: a typed agent message (1 model call: short), a peer message (5 calls: real work), an event (2 calls),
// and Shaan's own turn (not counted). One a0-task reached live today.
function fixture() {
  const home = mkdtempSync(path.join(tmpdir(), "traffic-"));
  const dir = path.join(home, ".claude", "projects", "-x"); mkdirSync(dir, { recursive: true });
  const u = (h, content, origin) => JSON.stringify({ type: "user", timestamp: at(h), message: { content }, ...(origin ? { origin } : {}) });
  let id = 0;
  const a = (h, tok) => JSON.stringify({ type: "assistant", timestamp: at(h), message: { id: `m${id++}`, usage: { input_tokens: tok, cache_read_input_tokens: 0, cache_creation_input_tokens: 0, output_tokens: 0 } } });
  const lines = [
    JSON.stringify({ type: "agent-name", agentName: "OWNER" }),
    u("10:00", "A0 → OWNER: please do the thing", { kind: "human" }), a("10:00", 100),
    u("10:05", "hello", { kind: "peer" }), a("10:05", 200), a("10:05", 10), a("10:05", 10), a("10:05", 10), a("10:05", 10),
    u("10:10", "<task-notification>done</task-notification>", { kind: "task-notification" }), a("10:10", 300), a("10:10", 5),
    u("10:20", "Shaan asks for X", { kind: "human" }), a("10:20", 999),
  ];
  writeFileSync(path.join(dir, "s1.jsonl"), lines.join("\n") + "\n");
  const tasks = path.join(home, "SISO_Workspace/SISO_Agents/agent-zero/siso-firstmate/.agents/a0/tasks"); mkdirSync(tasks, { recursive: true });
  writeFileSync(path.join(tasks, "t-1.json"), JSON.stringify({ id: "t-1", history: [{ at: at("09:00"), stage: "live" }] }));
  return args => spawnSync("python3", args, { env: { ...process.env, HOME: home }, encoding: "utf8" });
}

test("agent-traffic: classifies typed, peer and event turns, sums floor and short-turn tokens, divides by shipped", () => {
  const run = fixture();
  const r = run([bin, "--days", "1", "--json"]);
  assert.equal(r.status, 0, r.stderr);
  const d = JSON.parse(r.stdout).find(x => x.day === day);
  assert.deepEqual([d.typed.n, d.peer.n, d.event.n], [1, 1, 1]);
  assert.equal(d.message_floor_tokens, 100 + 200, "first call of each message turn");
  assert.equal(d.short_message_turns, 1, "the typed one (1 call); the peer turn did real work (5 calls)");
  assert.equal(d.event.first_call_tokens, 300); assert.equal(d.event.short_turn_tokens, 305);
  assert.equal(d.shipped, 1); assert.equal(d.messages_per_shipped, 2);
  assert.equal(d.message_tokens, 100 + 240, "Shaan's own turn is not counted");
});

test("agent-traffic --sessions: overhead by session name", () => {
  const run = fixture();
  const r = run([bin, "--sessions", "--day", day, "--json"]);
  assert.equal(r.status, 0, r.stderr);
  const [row] = JSON.parse(r.stdout);
  assert.equal(row.session, "OWNER");
  assert.deepEqual([row.event_turns, row.message_turns], [1, 2]);
  assert.equal(row.overhead_tokens, 300 + 305 + 100 + 200 + 100, "event floor+short, message floors, short message turn");
});
