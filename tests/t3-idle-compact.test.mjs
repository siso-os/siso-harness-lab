import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, existsSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/t3-idle-compact.mjs", import.meta.url).pathname;
const NOW = "2026-10-16T12:00:00.000Z";
const ago = min => new Date(Date.parse(NOW) - min * 60_000).toISOString();

const SCHEMA = `
CREATE TABLE projection_threads (thread_id TEXT PRIMARY KEY, title TEXT, archived_at TEXT, deleted_at TEXT, pinned_at TEXT,
  settled_at TEXT, settled_override TEXT, pending_approval_count INTEGER DEFAULT 0, pending_user_input_count INTEGER DEFAULT 0);
CREATE TABLE projection_thread_sessions (thread_id TEXT PRIMARY KEY, status TEXT);
CREATE TABLE projection_turns (row_id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, state TEXT, requested_at TEXT, completed_at TEXT);
CREATE TABLE projection_thread_activities (activity_id TEXT PRIMARY KEY, thread_id TEXT, kind TEXT, payload_json TEXT, created_at TEXT);`;

// Builds a fixture state.sqlite and a stub t3ctl that records what it was asked to send.
function fixture(chats) {
  const dir = mkdtempSync(path.join(tmpdir(), "t3ic-"));
  const db = path.join(dir, "state.sqlite");
  let sql = SCHEMA, n = 0;
  for (const c of chats) {
    const q = s => `'${String(s).replace(/'/g, "''")}'`;
    sql += `INSERT INTO projection_threads (thread_id,title,pinned_at,settled_at,settled_override,pending_approval_count) VALUES (${q(c.id)},${q(c.title ?? "chat " + c.id)},${c.pinned ? q(ago(500)) : "NULL"},${c.settled ? q(ago(500)) : "NULL"},${c.settled ? "'settled'" : "NULL"},${c.approvals ?? 0});`;
    sql += `INSERT INTO projection_thread_sessions VALUES (${q(c.id)},${q(c.session ?? "stopped")});`;
    const state = c.state ?? "completed";
    const done = state === "completed" ? q(ago(c.idle ?? 120)) : "NULL";
    sql += `INSERT INTO projection_turns (thread_id,state,requested_at,completed_at) VALUES (${q(c.id)},${q(state)},${q(ago((c.idle ?? 120) + 1))},${done});`;
    if (c.queued) sql += `INSERT INTO projection_turns (thread_id,state,requested_at,completed_at) VALUES (${q(c.id)},'pending',${q(ago(1))},NULL);`;
    if (c.ctx != null) sql += `INSERT INTO projection_thread_activities VALUES ('a${n++}',${q(c.id)},'context-window.updated','{"usedTokens":${c.ctx}}',${q(ago((c.idle ?? 120) + 1))});`;
  }
  execFileSync("sqlite3", [db, sql]);
  const sent = path.join(dir, "sent.txt");
  const stub = path.join(dir, "t3ctl");
  writeFileSync(stub, `#!/bin/sh\necho "$@" >> "${sent}"\necho sent\n`);
  chmodSync(stub, 0o755);
  return { dir, db, sent, stub, spell: path.join(dir, "spell.json") };
}
const run = (f, ...extra) => execFileSync("node", [bin, "--state", f.db, "--t3ctl", f.stub, "--spell-file", f.spell, "--now", NOW, ...extra], { encoding: "utf8" });
const sentIds = f => existsSync(f.sent) ? readFileSync(f.sent, "utf8").trim().split("\n").map(l => l.split(" ")[1]) : [];

test("idle and big is compacted; every skip case is skipped with its reason", () => {
  const f = fixture([
    { id: "bigidle1", ctx: 150_000, idle: 120 },
    { id: "running1", ctx: 150_000, state: "running" },
    { id: "session1", ctx: 150_000, session: "running" },
    { id: "queued01", ctx: 150_000, queued: true },
    { id: "recent01", ctx: 150_000, idle: 20 },
    { id: "small001", ctx: 40_000, idle: 120 },
    { id: "nocontex", idle: 120 },
    { id: "pinned01", ctx: 150_000, pinned: true },
    { id: "settled1", ctx: 150_000, settled: true },
    { id: "stale001", ctx: 150_000, idle: 3000 },
    { id: "approval", ctx: 150_000, approvals: 1 },
    { id: "import:claudeAgent:zzz", title: "Agent Zero", ctx: 900_000 },
    { id: "azero002", title: "agent zero", ctx: 900_000 },
  ]);
  const out = run(f, "--all");
  assert.deepEqual(sentIds(f), ["bigidle1"]);
  assert.match(out, /bigidle1\s+idle 120 min\s+context 150k\s+COMPACT/);
  assert.match(out, /running1.*skip: running or queued/);
  assert.match(out, /session1.*skip: running or queued/);
  assert.match(out, /queued01.*skip: running or queued/);
  assert.match(out, /recent01.*skip: recent \(20 min\)/);
  assert.match(out, /small001.*skip: small \(40k\)/);
  assert.match(out, /nocontex.*skip: no context reading/);
  assert.match(out, /pinned01.*skip: pinned/);
  assert.match(out, /settled1.*skip: settled/);
  assert.match(out, /stale001.*skip: idle too long \(50 h\)/);
  assert.match(out, /approval.*skip: waiting on a person/);
  assert.match(out, /import:c .*skip: agent zero/);
  assert.match(out, /azero002.*skip: agent zero/);
});

test("once per idle spell: skipped after our compact, picked again once a person has used the chat and it is idle and big again", () => {
  const f = fixture([{ id: "bigidle1", ctx: 150_000, idle: 120 }]);
  run(f);
  assert.deepEqual(sentIds(f), ["bigidle1"]);
  const sentAt = JSON.parse(readFileSync(f.spell, "utf8")).bigidle1.sentAt;
  assert.ok(sentAt);
  // Same spell: the latest turn was requested before (or within seconds of) our send.
  const again = run(f, "--all");
  assert.match(again, /already compacted this spell/);
  assert.deepEqual(sentIds(f), ["bigidle1"]);
  // A person writes later: a turn requested well after our send, then idle and big again.
  writeFileSync(f.spell, JSON.stringify({ bigidle1: { sentAt: ago(300) } }));
  run(f);
  assert.deepEqual(sentIds(f), ["bigidle1", "bigidle1"]);
});

test("at most 2 per sweep, biggest first; the other two wait for the next sweep", () => {
  const f = fixture([
    { id: "chat0001", ctx: 120_000 }, { id: "chat0002", ctx: 400_000 }, { id: "chat0003", ctx: 250_000 }, { id: "chat0004", ctx: 300_000 },
  ]);
  const out = run(f);
  assert.deepEqual(sentIds(f), ["chat0002", "chat0004"]);
  assert.match(out, /chat0003.*skip: over the 2 per sweep/);
  const next = run(f, "--all");
  assert.deepEqual(sentIds(f), ["chat0002", "chat0004", "chat0003", "chat0001"]);
  assert.match(next, /chat0002.*already compacted/);
});

test("--dry-run sends nothing and writes no state; flags change the thresholds; compaction lowers the reading", () => {
  const f = fixture([{ id: "bigidle1", ctx: 60_000, idle: 45 }]);
  const dry = run(f, "--dry-run", "--min-context", "50000", "--idle-min", "30");
  assert.match(dry, /dry run/);
  assert.match(dry, /bigidle1.*COMPACT/);
  assert.deepEqual(sentIds(f), []);
  assert.equal(existsSync(f.spell), false);
  // A context-compaction newer than the last reading means the chat is now small.
  const g = fixture([{ id: "bigidle1", ctx: 150_000, idle: 120 }]);
  execFileSync("sqlite3", [g.db, `INSERT INTO projection_thread_activities VALUES ('c1','bigidle1','context-compaction','{"afterTokens":12000}','${ago(100)}')`]);
  assert.match(run(g, "--all"), /small \(12k\)/);
  assert.deepEqual(sentIds(g), []);
});
