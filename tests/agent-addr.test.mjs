import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/agent-addr", import.meta.url).pathname;

// Two logins' session registries. This test process (alive) stands in for live sessions; pid 999999 is a dead one.
function fixture() {
  const base = realpathSync(mkdtempSync(path.join(tmpdir(), "agent-addr-")));
  const a = path.join(base, "siso"), b = path.join(base, "siso3");
  const put = (dir, pid, name, file = pid) => {
    mkdirSync(path.join(dir, "sessions"), { recursive: true });
    writeFileSync(path.join(dir, "sessions", `${file}.json`), JSON.stringify({ pid, name, kind: "interactive", messagingSocketPath: `/tmp/cc-socks/${file}.sock` }));
  };
  const run = (args, own = a) => spawnSync(bin, args, { encoding: "utf8",
    env: { ...process.env, AGENT_ADDR_LOGINS: `claude-siso=${a},claude-siso-3=${b}`, CLAUDE_CONFIG_DIR: own } });
  return { a, b, put, run };
}

test("agent-addr: bare name on the caller's own login, uds address on the other login, case-insensitive", () => {
  const f = fixture();
  f.put(f.a, process.pid, "A0", "100");
  f.put(f.b, process.ppid, "AGENT-BASE", "200");
  let r = f.run(["a0"]);
  assert.equal(r.status, 0, r.stderr); assert.equal(r.stdout.trim(), "A0");
  r = f.run(["agent-base"]);
  assert.equal(r.status, 0, r.stderr); assert.equal(r.stdout.trim(), "uds:/tmp/cc-socks/200.sock");
  r = f.run(["A0"], f.b);
  assert.equal(r.stdout.trim(), "uds:/tmp/cc-socks/100.sock", "seen from the other login");
  r = f.run(["--list"]);
  assert.match(r.stdout, /A0\s+claude-siso\s+uds:\/tmp\/cc-socks\/100\.sock/);
  assert.match(r.stdout, /AGENT-BASE\s+claude-siso-3\s+uds:\/tmp\/cc-socks\/200\.sock/);
});

test("agent-addr: a dead session is ignored (exit 1); two live sessions with the name on the other login are refused (exit 2), one on the caller's own login wins; a prefix is not a name", () => {
  const f = fixture();
  f.put(f.a, 999999, "GONE");
  let r = f.run(["GONE"]);
  assert.equal(r.status, 1); assert.match(r.stderr, /no live session/);
  f.put(f.b, process.pid, "TWIN", "300");
  f.put(f.b, process.ppid, "twin", "301");
  r = f.run(["twin"]);
  assert.equal(r.status, 2); assert.match(r.stderr, /2 live sessions/); assert.equal(r.stdout, "");
  assert.equal(f.run(["TWI"]).status, 1);
  const g = fixture();
  g.put(g.a, process.pid, "BOTH", "400");
  g.put(g.b, process.ppid, "BOTH", "401");
  r = g.run(["both"]);
  assert.equal(r.status, 0, "one on the caller's own login wins"); assert.equal(r.stdout.trim(), "BOTH");
});
