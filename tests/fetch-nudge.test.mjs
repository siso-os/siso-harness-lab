// node --test tests/fetch-nudge.test.mjs
import test from "node:test";
import assert from "node:assert";
import { step } from "../hooks/fetch-nudge.mjs";

test("nudges on the 3rd fetch in a row, once per run", () => {
  let s = null, out = [];
  for (const t of ["Read", "Grep", "Read", "Read", "Bash"]) { const r = step(s, { tool_name: t }, 1000); s = r.state; out.push(r.nudge); }
  assert.deepStrictEqual(out, [false, false, true, false, false]);
});
test("an edit ends the run; no second nudge until 15 more fetches", () => {
  let s = null, n = 0;
  const seq = ["Read", "Read", "Read", "Edit", ...Array(5).fill("Read"), "Write", "Read", "Read", "Read", "Edit", ...Array(4).fill("Read"), "Edit", "Grep", "Grep", "Grep"];
  for (const t of seq) { const r = step(s, { tool_name: t }, 1000); s = r.state; n += r.nudge; }
  assert.strictEqual(n, 2);
});
test("a 10-minute gap starts afresh", () => {
  let r = step(null, { tool_name: "Read" }, 0); r = step(r.state, { tool_name: "Read" }, 1000);
  r = step(r.state, { tool_name: "Read" }, 11 * 60_000);
  assert.strictEqual(r.nudge, false); assert.strictEqual(r.state.run, 1);
});
import { turnback, BACK_AT } from "../hooks/fetch-nudge.mjs";
test("turns back the 6th fetch in a row once; the repeat goes through", () => {
  let s = null;
  for (let i = 0; i < BACK_AT - 1; i++) s = step(s, { tool_name: "Read" }, 1000).state;
  let r = turnback(s, { tool_name: "Grep" }, 1000);
  assert.strictEqual(r.back, true);
  assert.strictEqual(turnback(r.state, { tool_name: "Grep" }, 1000).back, false);
  assert.strictEqual(turnback(step(null, { tool_name: "Read" }, 1000).state, { tool_name: "Read" }, 1000).back, false);
  assert.strictEqual(turnback(s, { tool_name: "Edit" }, 1000).back, false);
});
import { isFetch } from "../hooks/fetch-nudge.mjs";
test("Bash counts as fetching only when it reads", () => {
  assert.strictEqual(isFetch({ tool_name: "Bash", tool_input: { command: "cd x && grep -n a b" } }), true);
  assert.strictEqual(isFetch({ tool_name: "Bash", tool_input: { command: "git log --oneline -3" } }), true);
  assert.strictEqual(isFetch({ tool_name: "Bash", tool_input: { command: "git commit -qm x && gh pr merge" } }), false);
  assert.strictEqual(isFetch({ tool_name: "Bash", tool_input: { command: "tools/ab-live abc" } }), false);
  assert.strictEqual(isFetch({ tool_name: "Read" }), true);
});
