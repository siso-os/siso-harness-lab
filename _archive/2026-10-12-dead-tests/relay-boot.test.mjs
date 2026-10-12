import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, chmodSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/relay-boot", import.meta.url).pathname;

// The "mini" is this machine with a different HOME: a fake ssh runs the remote command locally, a fake herdr records what is
// asked of it, a fake `claude` reports the sign-in state, and `pane run` of the launcher makes the "agent" answer the token.
function fixture({ loggedIn = true, repoOnMini = true, answers = true } = {}) {
  const base = realpathSync(mkdtempSync(path.join(tmpdir(), "relay-")));
  const home = path.join(base, "home"), mini = path.join(base, "mini");   // the mini's HOME is a different folder
  const repo = path.join(home, "work", "proj");
  mkdirSync(path.join(repo, ".agents"), { recursive: true });
  writeFileSync(path.join(repo, ".agents", "HANDOFF.md"), "# checkpoint\nnext: ship it\n");
  mkdirSync(path.join(mini, ".claude-siso", "projects", "-x"), { recursive: true });
  if (repoOnMini) mkdirSync(path.join(mini, "work", "proj"), { recursive: true });
  const fb = path.join(base, "bin"); mkdirSync(fb);
  const mb = path.join(mini, ".local", "bin"); mkdirSync(mb, { recursive: true });   // first on the remote PATH
  const sh = (n, body) => { const d = n === "ssh" ? fb : mb; writeFileSync(path.join(d, n), "#!/bin/sh\n" + body); chmodSync(path.join(d, n), 0o755); };
  sh("ssh", `while [ "$1" = -o ]; do shift 2; done; shift; HOME="${mini}" exec sh -c "$1"\n`);
  sh("claude", `echo '{"loggedIn": ${loggedIn}}'\n`);
  sh("herdr", `echo "$*" >> "${base}/herdr.log"
case "$3 $4" in
  "status server") echo "status: running" ;;
  "workspace list") echo '{"result":{"workspaces":[{"label":"SISO Labs","workspace_id":"w1"}]}}' ;;
  "tab create") echo '{"result":{"root_pane":{"pane_id":"w1-9"},"tab":{"tab_id":"w1:9"}}}' ;;
  "pane run") ${answers ? `tok=$(printf '%s' "$6" | sed -n 's/.*READY \\(R[0-9a-f]*\\).*/\\1/p'); echo "{\\"type\\":\\"assistant\\",\\"message\\":{\\"content\\":\\"READY $tok: next\\"}}" > "${mini}/.claude-siso/projects/-x/sess-1234.jsonl"` : ":"}; echo '{"result":{}}' ;;
esac\n`);
  const env = { ...process.env, HOME: realpathSync(home), PATH: `${fb}:${process.env.PATH}`, RELAY_BOOT_STATE: path.join(base, "state") };
  const run = (...a) => spawnSync(bin, a, { env, encoding: "utf8" });
  const log = () => (existsSync(path.join(base, "herdr.log")) ? readFileSync(path.join(base, "herdr.log"), "utf8") : "");
  return { repo, mini, base, run, log, ck: path.join(repo, ".agents", "HANDOFF.md") };
}

test("relay-boot: copies only the checkpoint, opens a tab in the repo, starts the launcher, and reports READY from the token", () => {
  const f = fixture();
  const r = f.run("AGENT-BASE", "--repo", f.repo, "--checkpoint", f.ck, "--login", "claude-siso-3", "--cap", "heavy", "--task", "ab-1",
    "--chain", "opus:run", "--wait", "20");
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /READY AGENT-BASE session=sess-1234 pane=w1-9 host=mac-mini login=claude-siso-3/);
  assert.equal(readFileSync(path.join(f.mini, "work", "proj", ".agents", "HANDOFF.md"), "utf8"), "# checkpoint\nnext: ship it\n");
  const run = f.log().split("\n").find(l => l.includes("pane run"));
  assert.match(run, /claude-siso-3 --model claude-opus-5-5 --effort high --cap heavy --task ab-1 --chain opus:run --dangerously-skip-permissions -n AGENT-BASE/);
  assert.match(run, /Read .*HANDOFF\.md/);
  assert.match(f.log(), /tab create --workspace w1 --cwd .*proj --label AGENT-BASE/);
  const row = JSON.parse(readFileSync(path.join(f.base, "state", "log.jsonl"), "utf8").trim());
  assert.deepEqual([row.ready, row.session, row.pane, row.task], [true, "sess-1234", "w1-9", "ab-1"]);
});

test("relay-boot refuses before starting anything: plain claude, a file outside the repo, an empty checkpoint, not signed in, repo missing on the mini", () => {
  const f = fixture();
  let r = f.run("X", "--repo", f.repo, "--checkpoint", f.ck, "--login", "claude");
  assert.equal(r.status, 2); assert.match(r.stderr, /Fahmy/);
  writeFileSync(path.join(f.base, "outside.md"), "x");
  r = f.run("X", "--repo", f.repo, "--checkpoint", path.join(f.base, "outside.md"));
  assert.equal(r.status, 2); assert.match(r.stderr, /not inside the repo/);
  writeFileSync(path.join(f.repo, "empty.md"), "");
  r = f.run("X", "--repo", f.repo, "--checkpoint", path.join(f.repo, "empty.md"));
  assert.equal(r.status, 2); assert.match(r.stderr, /empty/);
  const g = fixture({ loggedIn: false });
  r = g.run("X", "--repo", g.repo, "--checkpoint", g.ck);
  assert.equal(r.status, 3); assert.match(r.stderr, /mini-login claude-siso/);
  const h = fixture({ repoOnMini: false });
  r = h.run("X", "--repo", h.repo, "--checkpoint", h.ck);
  assert.equal(r.status, 4); assert.match(r.stderr, /not on the mac-mini/);
  for (const x of [f, g, h]) assert.equal(x.log(), "", "nothing was sent to herdr");
});

test("relay-boot --dry-run prints the plan and changes nothing; no READY within --wait exits 5 and names the pane", () => {
  const f = fixture();
  const d = f.run("X", "--repo", f.repo, "--checkpoint", f.ck, "--dry-run");
  assert.equal(d.status, 0, d.stderr); assert.match(d.stdout, /would copy 1 file/);
  assert.ok(!existsSync(path.join(f.mini, "work", "proj", ".agents", "HANDOFF.md")));
  const g = fixture({ answers: false });
  const r = g.run("X", "--repo", g.repo, "--checkpoint", g.ck, "--wait", "1");
  assert.equal(r.status, 5, r.stderr); assert.match(r.stderr, /pane w1-9/);
});
