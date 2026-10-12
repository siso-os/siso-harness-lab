import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/claude-token-login", import.meta.url).pathname;
const TOKEN = "sk-ant-oat01-" + "Ab3_x-".repeat(15) + "ZZ";

// A fake `claude setup-token`: shows the URL and the paste prompt, reads the code, then prints the token split across
// several writes (so masking must hold a partial token back). A fake `security -i` records what it was given.
function fixture({ prints = true, proofExit = 0 } = {}) {
  const base = mkdtempSync(path.join(tmpdir(), "token-login-"));
  const fb = path.join(base, "bin"); mkdirSync(fb);
  writeFileSync(path.join(fb, "claude"), `#!/usr/bin/env python3
import os, sys, time
assert sys.argv[1:] == ["setup-token"], sys.argv
assert "/.siso-ephemeral-token-login." in os.environ["CLAUDE_CONFIG_DIR"]
open(${JSON.stringify(path.join(base, "home"))}, "w").write(os.environ["CLAUDE_CONFIG_DIR"])
def w(s): os.write(1, s.encode()); time.sleep(0.05)
w("Browser didn't open? https://claude.com/cai/oauth/authorize?code=true\\r\\nPaste code here if prompted > ")
code = sys.stdin.readline().strip()
w("\\r\\ncode " + code + " accepted\\r\\n")
${prints ? `t = ${JSON.stringify(TOKEN)}
w("Your OAuth token (valid for 1 year):\\r\\n\\r\\n" + t[:9]); w(t[9:40]); w(t[40:] + "\\r\\n\\r\\nStore this token securely.\\r\\n")` : `w("Login failed\\r\\n"); sys.exit(1)`}
`); chmodSync(path.join(fb, "claude"), 0o755);
  writeFileSync(path.join(fb, "security"), `#!/bin/sh
if [ "$1" = -i ]; then cat > "${base}/security-in"; exit 0; fi
if [ "$1" = delete-generic-password ]; then echo "$*" > "${base}/security-deleted"; exit 0; fi
sed -n 's/.* -w \\(.*\\)$/\\1/p' "${base}/security-in" 2>/dev/null
`); chmodSync(path.join(fb, "security"), 0o755);
  writeFileSync(path.join(fb, "proof"), proofExit === 4 ? `#!/bin/sh\necho "FAIL account"; echo "wrong-account: fuzeheritage"; exit 4\n` : `#!/bin/sh\necho "token-proof: GREEN (4/4) for $1"\n`); chmodSync(path.join(fb, "proof"), 0o755);
  const env = { ...process.env, PATH: `${fb}:${process.env.PATH}`, CLAUDE_TOKEN_LOGIN_CLAUDE: path.join(fb, "claude"),
    CLAUDE_TOKEN_LOGIN_PROOF: path.join(fb, "proof"), CLAUDE_TOKEN_LOGIN_STATE: path.join(base, "state"), CLAUDE_TOKEN_LOGIN_BROWSER: "/usr/bin/true" };
  const run = (args, input = "CODE-42\n") => spawnSync(bin, args, { env, input, encoding: "utf8", timeout: 20000 });
  return { base, run };
}

test("claude-token-login: the token goes to the Keychain via security -i, never to the screen or argv; the proof runs; the scratch home is gone", () => {
  const f = fixture();
  const r = f.run(["--here", "fuzeheritage"]);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.ok(!(r.stdout + r.stderr).includes(TOKEN.slice(12)), "no part of the token after its prefix is shown");
  assert.match(r.stdout, /sk-ant-oat\.\.\. \[saved to the Keychain, hidden\]/);
  assert.match(r.stdout, /Paste code here if prompted/, "the prompt reaches Shaan");
  assert.match(r.stdout, /code CODE-42 accepted/, "his pasted code reaches setup-token");
  assert.equal(readFileSync(path.join(f.base, "security-in"), "utf8"), `add-generic-password -U -s siso-claude-oauth -a fuzeheritage -w ${TOKEN}\n`);
  assert.match(r.stdout, /GREEN \(4\/4\) for fuzeheritage/);
  assert.ok(!existsSync(readFileSync(path.join(f.base, "home"), "utf8")), "scratch CLAUDE_CONFIG_DIR removed");
  const log = readFileSync(path.join(f.base, "state", "log.jsonl"), "utf8");
  assert.ok(!log.includes("sk-ant"), "the log holds no token");
});

test("claude-token-login: no token printed -> exit 1, nothing stored; plain claude and unknown accounts are refused", () => {
  const f = fixture({ prints: false });
  const r = f.run(["--here", "lordsisodia"]);
  assert.equal(r.status, 1); assert.match(r.stdout, /nothing was saved/);
  assert.ok(!existsSync(path.join(f.base, "security-in")));
  for (const a of ["claude", "fahmy", "x"]) {
    const n = f.run(["--here", a]);
    assert.equal(n.status, 2); assert.match(n.stderr, /refused/);
  }
});

test("claude-token-login: a token for the wrong account is thrown away and the tab says which account the browser was on", () => {
  const f = fixture({ proofExit: 4 });
  const r = f.run(["--here", "lordsisodia"]);
  assert.equal(r.status, 1);
  assert.match(r.stdout, /signed in to fuzeheritage, not lordsisodia/);
  assert.match(readFileSync(path.join(f.base, "security-deleted"), "utf8"), /-s siso-claude-oauth -a lordsisodia/);
});
