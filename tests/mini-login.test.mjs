import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/mini-login", import.meta.url).pathname;

// A fake herdr: the sign-in tab shows "Paste code here" until text is typed into it, then the CLI's success line (or a rejection).
function fixture({ tab = true, accept = true } = {}) {
  const d = mkdtempSync(path.join(tmpdir(), "minilogin-"));
  const h = path.join(d, "herdr");
  writeFileSync(h, `#!/bin/sh
echo "$*" >> "${d}/herdr.log"
case "$1 $2" in
  "tab list") echo '{"result":{"tabs":[${tab ? `{"tab_id":"t9","label":"SIGN IN person@example.com on the mini"}` : ""}]}}' ;;
  "pane list") echo '{"result":{"panes":[{"pane_id":"p9","tab_id":"t9"}]}}' ;;
  "pane read") if [ -f "${d}/typed" ]; then ${accept ? 'echo "Paste code here if prompted > "; echo "Login successful."' : 'echo "Paste code here if prompted > "; echo "Invalid code"'}; else echo "Paste code here if prompted >"; fi ;;
  "pane send-text") touch "${d}/typed"; echo "$4" > "${d}/code" ;;
esac
`);
  chmodSync(h, 0o755);
  const logins = path.join(d, "logins.json");
  writeFileSync(logins, JSON.stringify({ "claude-siso": "person@example.com" }));
  const run = (...a) => spawnSync(bin, a, { env: { ...process.env, HERDR_BIN: h, SISO_CLAUDE_LOGINS: logins }, encoding: "utf8" });
  return { d, run };
}

test("mini-login --code types the code into the account's waiting tab and reports success", () => {
  const f = fixture();
  const r = f.run("--code", "claude-siso", "abc-123_XYZ");
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /person@example.com: signed in/);
  assert.equal(readFileSync(path.join(f.d, "code"), "utf8").trim(), "abc-123_XYZ");
  assert.match(readFileSync(path.join(f.d, "herdr.log"), "utf8"), /pane send-keys p9 enter/);
});

test("mini-login --code: no waiting tab is exit 1 and types nothing; a rejected code is exit 3; plain claude is refused", () => {
  const f = fixture({ tab: false });
  assert.equal(f.run("--code", "claude-siso", "x").status, 1);
  assert.ok(!existsSync(path.join(f.d, "code")));
  const g = fixture({ accept: false });
  const r = g.run("--code", "claude-siso", "bad");
  assert.equal(r.status, 3, r.stderr); assert.match(r.stderr, /did not report success/);
  assert.equal(f.run("--code", "claude", "x").status, 2);
});
