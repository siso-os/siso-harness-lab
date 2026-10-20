// node --test tests/lane-model.test.mjs
import test from "node:test";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
import { retarget, SONNET } from "../hooks/lane-model.mjs";

test("an Opus or unnamed Claude lane goes to Sonnet, everything else kept", () => {
  assert.strictEqual(retarget({ task: "build K5" }).target.model, SONNET);
  const u = retarget({ task: "x", mode: "async", target: { providerInstanceId: "claudeAgent", model: "claude-opus-5-5", options: { effort: "high" } } });
  assert.deepStrictEqual(u, { task: "x", mode: "async", target: { providerInstanceId: "claudeAgent", model: SONNET, options: { effort: "high" } } });
});
test("left alone: [opus], other providers, explicit Sonnet or Haiku", () => {
  for (const ti of [{ task: "hard proof [opus]" }, { task: "x", title: "Lane 9 [Opus]" },
    { task: "x", target: { providerInstanceId: "codex", model: "gpt-5.5" } },
    { task: "x", target: { model: "claude-haiku-5-5" } }, { task: "x", target: { model: SONNET } }])
    assert.strictEqual(retarget(ti), null, JSON.stringify(ti));
});
test("hook prints updatedInput for delegate_task only; off switch", () => {
  const run = (o, env = {}) => execFileSync("node", ["hooks/lane-model.mjs"], { input: JSON.stringify(o), encoding: "utf8", env: { ...process.env, ...env } });
  const nudge = JSON.parse(run({ tool_name: "mcp__t3-code__delegate_task", tool_input: { task: "x" } }));
  assert.strictEqual(nudge.hookSpecificOutput.updatedInput, undefined);
  assert.ok(nudge.hookSpecificOutput.additionalContext.includes("Pick per task"));
  for (const ti of [{ task: "x", target: { model: "claude-opus-5-5" } }, { task: "x", target: { providerInstanceId: "codex" } }])
    assert.strictEqual(run({ tool_name: "mcp__t3-code__delegate_task", tool_input: ti }), "");
  const out = JSON.parse(run({ tool_name: "mcp__t3-code__delegate_task", tool_input: { task: "x", clientRequestId: "r1" } }, { LANE_MODEL: "force" }));
  assert.strictEqual(out.hookSpecificOutput.updatedInput.target.model, SONNET);
  assert.strictEqual(out.hookSpecificOutput.updatedInput.clientRequestId, "r1");
  assert.strictEqual(out.hookSpecificOutput.permissionDecision, undefined);
  assert.strictEqual(run({ tool_name: "Bash", tool_input: { command: "ls" } }), "");
  assert.strictEqual(run({ tool_name: "mcp__t3-code__delegate_task", tool_input: { task: "x" } }, { LANE_MODEL: "0" }), "");
  assert.strictEqual(execFileSync("node", ["hooks/lane-model.mjs"], { input: "{bad", encoding: "utf8" }), "");
});
