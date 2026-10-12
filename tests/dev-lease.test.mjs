import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync, spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/dev-lease", import.meta.url).pathname;
const fresh = () => mkdtempSync(path.join(tmpdir(), "lease-"));
const lease = (dir, ...args) => spawnSync(bin, args, { env: { ...process.env, DEV_LEASE_DIR: dir, DEV_LEASE_POLL: "0.1" }, encoding: "utf8" });

test("take, contention, renew by the holder, release, and only the holder releases", () => {
  const d = fresh();
  let r = lease(d, "take", "DEV", "--holder", "OPS-BUILD", "--until", "+30m", "--why", "board restart");
  assert.equal(r.status, 0);
  assert.match(r.stdout, /^DEV: held by OPS-BUILD until \d\d:\d\d — board restart/);
  r = lease(d, "take", "DEV", "--holder", "STREAM-A", "--until", "+10m", "--why", "x");
  assert.equal(r.status, 1);
  assert.match(r.stderr, /held by OPS-BUILD/);
  assert.equal(lease(d, "take", "DEV", "--holder", "OPS-BUILD", "--until", "+1h", "--why", "longer").status, 0);
  assert.equal(lease(d, "release", "DEV", "--holder", "STREAM-A").status, 1);
  assert.equal(lease(d, "release", "DEV", "--holder", "OPS-BUILD").stdout, "DEV: free\n");
  assert.equal(lease(d, "status").stdout, "no leases\n");
  const events = readFileSync(path.join(d, "log.jsonl"), "utf8").trim().split("\n").map(l => JSON.parse(l).event);
  assert.deepEqual(events, ["take", "renew", "release"]);
  assert.ok(!readdirSync(d).some(f => f.endsWith(".tmp")), "atomic writes leave no temp files");
  rmSync(d, { recursive: true, force: true });
});

test("an expired lease is free to take, and status says expired", () => {
  const d = fresh();
  writeFileSync(path.join(d, "DEV.json"), JSON.stringify({ res: "DEV", holder: "OLD", until: "2026-01-01T00:00:00+07:00", why: "w" }));
  assert.match(lease(d, "status", "DEV").stdout, /DEV: expired by OLD/);
  assert.equal(JSON.parse(lease(d, "status", "--json").stdout)[0].state, "expired");
  assert.equal(lease(d, "take", "DEV", "--holder", "NEW", "--until", "+5m", "--why", "x").status, 0);
  rmSync(d, { recursive: true, force: true });
});

test("wait: returns at once when free or already mine, times out with 124, wakes when the lease is released", async () => {
  const d = fresh();
  assert.equal(lease(d, "wait", "DEV").status, 0);
  lease(d, "take", "DEV", "--holder", "A", "--until", "+30m", "--why", "x");
  assert.equal(lease(d, "wait", "DEV", "--holder", "A").status, 0);
  assert.equal(lease(d, "wait", "DEV", "--timeout", "0.3").status, 124);
  const t0 = Date.now();
  const w = spawn(bin, ["wait", "DEV", "--timeout", "10"], { env: { ...process.env, DEV_LEASE_DIR: d, DEV_LEASE_POLL: "0.1" } });
  const done = new Promise(res => w.on("exit", res));
  setTimeout(() => lease(d, "release", "DEV", "--holder", "A"), 400);
  assert.equal(await done, 0);
  assert.ok(Date.now() - t0 < 3000);
  rmSync(d, { recursive: true, force: true });
});

test("bad input: HH:MM only, safe resource names", () => {
  const d = fresh();
  assert.notEqual(lease(d, "take", "DEV", "--holder", "A", "--until", "soon", "--why", "x").status, 0);
  assert.notEqual(lease(d, "take", "../etc", "--holder", "A", "--until", "+5m", "--why", "x").status, 0);
  assert.equal(lease(d, "take", "DEV", "--holder", "A", "--until", "23:59", "--why", "x").status, 0);
  rmSync(d, { recursive: true, force: true });
});

test("concurrent takes: exactly one wins", async () => {
  const d = fresh();
  const runs = ["A", "B", "C", "D", "E", "F"].map(h => new Promise(res =>
    spawn(bin, ["take", "DEV", "--holder", h, "--until", "+5m", "--why", "race"], { env: { ...process.env, DEV_LEASE_DIR: d } })
      .on("exit", res)));
  const codes = await Promise.all(runs);
  assert.equal(codes.filter(c => c === 0).length, 1);
  rmSync(d, { recursive: true, force: true });
});
