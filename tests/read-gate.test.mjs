// node --test tests/read-gate.test.mjs
import test from "node:test";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { gate, MIN } from "../hooks/read-gate.mjs";

test("gates only whole reads of big text files, once per file", () => {
  assert.strictEqual(gate({ file_path: "/a.ts" }, MIN, []), true);
  assert.strictEqual(gate({ file_path: "/a.ts" }, MIN - 1, []), false);
  assert.strictEqual(gate({ file_path: "/a.ts" }, MIN, ["/a.ts"]), false);
  assert.strictEqual(gate({ file_path: "/a.ts", limit: 100 }, MIN * 4, []), false);
  assert.strictEqual(gate({ file_path: "/a.ts", offset: 0 }, MIN * 4, []), false);
  assert.strictEqual(gate({ file_path: "/a.pdf" }, MIN * 4, []), false);
});
test("hook denies the first whole read, lets the second through, ignores sub-agents", () => {
  const d = mkdtempSync(path.join(tmpdir(), "rg-")), f = path.join(d, "big.ts");
  writeFileSync(f, "const x = 1;\n".repeat(4000));
  const env = { ...process.env, READ_GATE_STATE: d };
  const run = o => execFileSync("node", ["hooks/read-gate.mjs"], { input: JSON.stringify(o), encoding: "utf8", env });
  const sub = run({ session_id: "s", agent_id: "a", tool_name: "Read", tool_input: { file_path: f } });
  assert.strictEqual(sub, "");
  const first = JSON.parse(run({ session_id: "s", tool_name: "Read", tool_input: { file_path: f } })).hookSpecificOutput;
  assert.strictEqual(first.permissionDecision, "deny"); assert.match(first.permissionDecisionReason, /big\.ts is 51 KB, 4001 lines/);
  assert.strictEqual(run({ session_id: "s", tool_name: "Read", tool_input: { file_path: f } }), "");
  assert.strictEqual(run({ session_id: "s", tool_name: "Read", tool_input: { file_path: path.join(d, "missing.ts") } }), "");
});
