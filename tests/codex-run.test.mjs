import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const root = new URL("..", import.meta.url).pathname;

// A fake codex: records its argv, emits one usage event, writes the final message to the -o file.
function fake(dir, final, rc = 0) {
  const bin = path.join(dir, "codex");
  writeFileSync(bin, `#!/usr/bin/env bash
if [[ " $* " == *" mcp list --json "* ]]; then
  printf '%s\\n' '{"name":"ignored"}' > "${dir}/catalog-query"
  printf '%s\\n' '[{"name":"serena","enabled":true,"transport":{"type":"stdio","command":"should-never-be-forwarded"}},{"name":"plugin.only","enabled":true,"transport":{"type":"streamable_http","url":"https://server.invalid/mcp?token=keep-out-of-argv"}}]'
  exit 0
fi
printf '%s\\n' "$@" > "${dir}/argv"
while (($#)); do [[ $1 == -o ]] && out=$2; shift; done
echo '{"type":"turn.completed","usage":{"input_tokens":1000,"cached_input_tokens":400,"output_tokens":50}}'
${final === null ? "" : `printf '%b' ${JSON.stringify(final)} > "$out"`}
exit ${rc}
`, { mode: 0o755 });
  return bin;
}

function run(args, final, rc) {
  const dir = mkdtempSync(path.join(tmpdir(), "crun-"));
  const r = spawnSync(`${root}bin/codex-run`, args, {
    env: { ...process.env, CODEX_BIN: fake(dir, final, rc), CODEX_RUN_STATE: path.join(dir, "state"), CODEX_SOL_STATE: path.join(dir, "sol"), SISO_SOL_WHY: "" }, encoding: "utf8",
  });
  const log = JSON.parse(readFileSync(path.join(dir, "state", "log.jsonl"), "utf8").trim());
  const argv = readFileSync(path.join(dir, "argv"), "utf8").split("\n");
  let sol = null;
  try { sol = JSON.parse(readFileSync(path.join(dir, "sol", "log.jsonl"), "utf8").trim()); } catch {}
  let catalogQueried = false;
  try { readFileSync(path.join(dir, "catalog-query")); catalogQueried = true; } catch {}
  rmSync(dir, { recursive: true, force: true });
  return { ...r, log, argv, sol, catalogQueried };
}

test("current Sol default, effective global/plugin MCP off, RETURN contract and usage retained", () => {
  const r = run(["-C", "/tmp", "check the thing"], "RETURN\nSTATUS: done — ok\nCHANGED: nothing");
  assert.equal(r.status, 0);
  assert.match(r.stdout, /^RETURN\nSTATUS: done — ok\nCHANGED: nothing\nLOG \S+\.jsonl\n$/);
  assert.deepEqual(r.argv.slice(0, 3), ["exec", "-m", "gpt-6.1-sol"]);
  const override = r.argv.find(x => x.startsWith("mcp_servers="));
  assert.ok(r.catalogQueried);
  assert.match(override, /"serena"=\{command="false",enabled=false\}/);
  assert.match(override, /"plugin.only"=\{url="http:\/\/127.0.0.1",enabled=false\}/);
  assert.doesNotMatch(r.argv.join("\n"), /should-never-be-forwarded|keep-out-of-argv/);
  assert.ok(r.argv.includes("/tmp"));
  const prompt = r.argv.slice(r.argv.indexOf(override) + 1).join("\n");
  assert.match(prompt, /^check the thing[\s\S]*at most 200 words[\s\S]*EVIDENCE:/);
  assert.equal(r.log.model, "gpt-6.1-sol");
  assert.equal(r.log.status, "done");
  assert.equal(r.log.input_tokens, 1000);
});

test("--sol --why picks Sol and stamps the reason (Sol log + run log); --mcp keeps MCP; a failed STATUS exits 1", () => {
  const r = run(["--sol", "--why", "heavier coding: the host rewrite", "--mcp", "--task", "t-9", "x"], "RETURN\nSTATUS: failed — 3 tests red");
  assert.equal(r.status, 1);
  assert.equal(r.argv[2], "gpt-6.1-sol");
  assert.ok(!r.argv.includes("mcp_servers={}"));
  assert.ok(!r.argv.some(x => x.startsWith("mcp_servers=")));
  assert.equal(r.catalogQueried, false);
  assert.equal(r.log.status, "failed");
  assert.equal(r.log.sol_why, "heavier coding: the host rewrite");
  assert.deepEqual([r.sol.by, r.sol.name, r.sol.task, r.sol.why], ["codex-run", "codex-run t-9", "t-9", "heavier coding: the host rewrite"]);
});

test("explicit Luna selection remains available without a Sol reason", () => {
  const r = run(["-m", "gpt-6-luna", "x"], "RETURN\nSTATUS: done — ok");
  assert.equal(r.status, 0);
  assert.equal(r.argv[2], "gpt-6-luna");
  assert.equal(r.log.sol_why, undefined);
  assert.equal(r.sol, null);
});

test("unreadable effective MCP catalog stops before launching the worker", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "crun-"));
  const broken = path.join(dir, "codex");
  writeFileSync(broken, `#!/usr/bin/env bash\nif [[ " $* " == *" mcp list --json "* ]]; then echo 'not JSON'; exit 0; fi\nprintf started > "${dir}/argv"\n`, { mode: 0o755 });
  const r = spawnSync(`${root}bin/codex-run`, ["x"], { env: { ...process.env, CODEX_BIN: broken, CODEX_RUN_STATE: path.join(dir, "state"), CODEX_SOL_STATE: path.join(dir, "sol"), SISO_SOL_WHY: "" }, encoding: "utf8" });
  assert.equal(r.status, 2);
  assert.match(r.stderr, /MCP catalog unavailable/);
  assert.throws(() => readFileSync(path.join(dir, "argv")), "worker never ran");
  rmSync(dir, { recursive: true, force: true });
});

test("no final message: prints a blocked RETURN and exits 1", () => {
  const r = run(["x"], null, 3);
  assert.equal(r.status, 1);
  assert.match(r.stdout, /STATUS: blocked — codex exited 3/);
  assert.equal(r.log.exit, 3);
});

test("usage error exits 2", () => {
  assert.equal(spawnSync(`${root}bin/codex-run`, [], { encoding: "utf8" }).status, 2);
});
