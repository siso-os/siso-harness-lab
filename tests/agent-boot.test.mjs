import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("agent-boot.json: Artifact off, only valid listing values, brain-named skills stay on", () => {
  const p = JSON.parse(readFileSync(new URL("../config/agent-boot.json", import.meta.url), "utf8"));
  assert.equal(p.enableArtifact, false);
  for (const [k, v] of Object.entries(p.skillOverrides)) assert.ok(["name-only", "user-invocable-only", "off", "on"].includes(v), k);
  assert.ok(!Object.values(p.skillOverrides).includes("off"), "nothing is hidden outright: an agent can still roll a skill in");
  for (const s of ["self-compact", "shaan-report", "adhd-agent-output"]) assert.equal(p.skillOverrides[s], undefined, s);
});
