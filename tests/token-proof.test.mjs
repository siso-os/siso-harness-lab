import test from "node:test";
import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, chmodSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import path from "node:path";
import http from "node:http";

const bin = new URL("../scripts/token-proof.py", import.meta.url).pathname;
const TOKEN = "sk-ant-oat01-FAKE-SECRET-123";
const svc = d => "Claude Code-credentials-" + createHash("sha256").update(path.join(homedir(), d)).digest("hex").slice(0, 8);
const SISO = svc(".claude-siso"), SISO3 = svc(".config/claude-siso-3");

// Fake `security`: the stored setup-token for "fuzeheritage", and each login's own credential item (a JSON blob with
// accessToken LOGIN-<service>). Fake `claude`: checks it got the token from the env and a scratch CLAUDE_CONFIG_DIR.
function fixture({ window = 1000000 } = {}) {
  const base = mkdtempSync(path.join(tmpdir(), "token-proof-"));
  const fb = path.join(base, "bin"); mkdirSync(fb);
  writeFileSync(path.join(fb, "security"), `#!/bin/sh
case "$*" in
  *"-a fuzeheritage"*) echo "${TOKEN}" ;;
  *"${SISO}"*) echo '{"claudeAiOauth":{"accessToken":"LOGIN-siso"}}' ;;
  *"${SISO3}"*) echo '{"claudeAiOauth":{"accessToken":"LOGIN-siso3"}}' ;;
  *) exit 44 ;;
esac
`); chmodSync(path.join(fb, "security"), 0o755);
  writeFileSync(path.join(fb, "claude"), `#!/bin/sh
[ "$CLAUDE_CODE_OAUTH_TOKEN" = "${TOKEN}" ] || { echo '{}'; exit 1; }
case "$CLAUDE_CONFIG_DIR" in */.siso-ephemeral-token-proof.*) ;; *) echo '{}'; exit 1 ;; esac
echo "$CLAUDE_CONFIG_DIR" > "${base}/config-dir"
if [ "$1" = auth ]; then echo '{"loggedIn": true, "authMethod": "oauth_token"}'; exit 0; fi
echo '{"result":"ok","modelUsage":{"claude-opus-5-5[1m]":{"contextWindow":${window}}}}'
`); chmodSync(path.join(fb, "claude"), 0o755);
  return { base, fb };
}

// The stand-in API: /v1/messages answers with the weekly reset of the account behind the bearer token; the OAuth
// profile/usage endpoints refuse a setup-token (user:inference only) as the real one does.
function api({ tokenIs = "siso" } = {}) {
  const reset = { siso: "1791504000", siso3: "1791100000" };
  const who = auth => auth === `Bearer ${TOKEN}` ? tokenIs : auth === "Bearer LOGIN-siso" ? "siso" : auth === "Bearer LOGIN-siso3" ? "siso3" : null;
  return new Promise(res => {
    const seen = [];
    const s = http.createServer((req, rsp) => {
      seen.push(req.headers.authorization);
      const w = who(req.headers.authorization);
      if (req.url === "/v1/messages" && w) {
        rsp.setHeader("anthropic-ratelimit-unified-7d-reset", reset[w]);
        rsp.setHeader("anthropic-ratelimit-unified-5h-utilization", "0.2");
        rsp.setHeader("anthropic-ratelimit-unified-7d-utilization", "0.17");
        return rsp.end("{}");
      }
      rsp.statusCode = 403; rsp.end("{}");
    }).listen(0, "127.0.0.1", () => res({ s, seen }));
  });
}

function run(f, args, port) {
  return new Promise(res => {
    const env = { ...process.env, PATH: `${f.fb}:${process.env.PATH}`, TOKEN_PROOF_CLAUDE: path.join(f.fb, "claude"), TOKEN_PROOF_API: `http://127.0.0.1:${port}` };
    const p = spawn("python3", [bin, ...args], { env });
    let stdout = "", stderr = "";
    p.stdout.on("data", d => (stdout += d)); p.stderr.on("data", d => (stderr += d));
    p.on("close", status => res({ status, stdout, stderr }));
  });
}

test("token-proof: GREEN when auth, Opus 1M, usage headers and the account fingerprint hold; token never printed; scratch folder removed", async () => {
  const f = fixture();
  const { s } = await api();
  const r = await run(f, ["fuzeheritage"], s.address().port); s.close();
  assert.equal(r.status, 0, r.stdout + r.stderr);
  for (const c of ["auth", "opus-1m", "usage", "account"]) assert.match(r.stdout, new RegExp(`PASS ${c}`));
  assert.match(r.stdout, /info \/api\/oauth\/usage: HTTPError 403/);
  assert.match(r.stdout, /GREEN \(4\/4\)/);
  assert.ok(!(r.stdout + r.stderr).includes(TOKEN), "token never printed");
  const dir = readFileSync(path.join(f.base, "config-dir"), "utf8").trim();
  assert.equal(spawnSync("test", ["-e", dir]).status, 1, "scratch config folder removed");
});

test("token-proof: RED when the token is the other account's or the window is not 1M; exit 3 with the store command when no token exists", async () => {
  const f = fixture({ window: 200000 });
  const { s } = await api({ tokenIs: "siso3" });
  const r = await run(f, ["fuzeheritage"], s.address().port); s.close();
  assert.equal(r.status, 4, "another account's token");
  assert.match(r.stdout, /wrong-account: lordsisodia/);
  assert.match(r.stdout, /FAIL opus-1m: .*contextWindow=200000/);
  assert.match(r.stdout, /FAIL account: weekly reset matches ~\/\.claude-siso: False; matches another login: True/);
  assert.match(r.stdout, /RED/);
  const n = await run(f, ["lordsisodia"], 1);
  assert.equal(n.status, 3); assert.match(n.stderr, /security add-generic-password -U -s siso-claude-oauth -a lordsisodia -w/);
});
