// node --test tests/test-filter.test.mjs
import test from "node:test";
import assert from "node:assert";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { wrap } from "../hooks/test-filter.mjs";

test("wraps bare test runs only", () => {
  for (const c of ["npm test", "npm run test:unit", "bun run test", "pnpm test", "pnpm run test:unit", "heavy -- pnpm vitest run", "node --test tests/*.test.mjs",
    "node services/host/test/host-flags.mjs", "cd services/node && node --test", "python3 -m pytest -q", "cargo test", "go test ./..."])
    assert.ok(wrap(c), c);
  for (const c of ["npm test | tail -5", "npm test > out.txt", "npm test; echo hi", "cd a && npm test && npm run build", "ls tests",
    "node script.mjs", "npm install", "git status", "npm test # full", "echo $(npm test)", "cat tests/a.test.mjs"])
    assert.strictEqual(wrap(c), null, c);
});
test("keeps the exit code; a pass shows the end, a fail shows the failing lines", () => {
  const d = mkdtempSync(path.join(tmpdir(), "tf-"));
  writeFileSync(path.join(d, "ok.test.mjs"), "for (let i = 0; i < 200; i++) console.log('ok ' + i);\n");
  writeFileSync(path.join(d, "bad.test.mjs"), "for (let i = 0; i < 200; i++) console.log('ok ' + i);\nconsole.log('not ok 201 - adds');\nprocess.exit(3);\n");
  const ok = spawnSync("bash", ["-c", wrap("node ok.test.mjs")], { cwd: d, encoding: "utf8" });
  assert.strictEqual(ok.status, 0);
  assert.ok(ok.stdout.split("\n").length < 10 && ok.stdout.includes("ok 199") && ok.stdout.includes("200 lines"), ok.stdout);
  const bad = spawnSync("bash", ["-c", wrap("node bad.test.mjs")], { cwd: d, encoding: "utf8" });
  assert.strictEqual(bad.status, 3);
  assert.ok(bad.stdout.includes("not ok 201") && bad.stdout.includes("exit 3") && bad.stdout.split("\n").length < 30, bad.stdout);
});
test("hook prints updatedInput with the other fields kept, nothing for sub-agents", () => {
  const run = o => execFileSync("node", ["hooks/test-filter.mjs"], { input: JSON.stringify(o), encoding: "utf8" });
  const out = JSON.parse(run({ session_id: "s", tool_name: "Bash", tool_input: { command: "npm test", timeout: 9000, description: "d" } }));
  const u = out.hookSpecificOutput.updatedInput;
  assert.strictEqual(u.timeout, 9000); assert.strictEqual(u.description, "d"); assert.ok(u.command.includes("bash -c 'npm test'"));
  assert.strictEqual(out.hookSpecificOutput.permissionDecision, undefined);
  assert.strictEqual(run({ session_id: "s", agent_id: "a", tool_name: "Bash", tool_input: { command: "npm test" } }), "");
});
