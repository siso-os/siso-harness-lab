// node --test tests/slow-bg.test.mjs
import test from "node:test";
import assert from "node:assert";
import { execFileSync } from "node:child_process";
import { slow } from "../hooks/slow-bg.mjs";

test("flags commands that take minutes, leaves quick ones", () => {
  for (const c of ["cd ~ && heavy -- du -xhd1 ~ | sort -rh", "du -sh ~", "du -xhd1 / 2>/dev/null", "du -sk ~/Library",
    "find ~ -name '*.tmp'", "pnpm build", "cd apps/web && npm run build", "vp build", "pnpm install", "npm ci",
    "brew upgrade", "npx wrangler pages deploy dist", "bash v2/deploy-dev.sh", "git clone https://github.com/a/b",
    "time heavy -- python3 tools/storage-map.py", "npx playwright test"])
    assert.ok(slow(c), c);
  for (const c of ["git status", "heavy --class quick -- du -sk .[!.]*", "du -sh node_modules", "du -sk ~/SISO_Workspace/x",
    "find . -name a", "find ~/SISO_Workspace/a -maxdepth 1", "pnpm test", "ls ~/build", "cat deploy.md",
    "pnpm build # fg", "echo heavy", "git add v2 && git commit -m x"])
    assert.strictEqual(slow(c), null, c);
});
test("ignores heredoc bodies and quoted text", () => {
  for (const c of ["python3 - <<'EOF'\ns = 'pnpm build'\nEOF", "git commit -m \"run pnpm build in the background\"",
    "echo 'du -sh ~'", "cat > a.py <<EOF\nos.system('git clone x')\nEOF\nnode a.mjs"])
    assert.strictEqual(slow(c), null, c);
  assert.ok(slow("cat <<'EOF' > a\nhi\nEOF\npnpm build"));
});
test("hook moves a foreground slow command to the background, passes background runs and sub-agents", () => {
  const run = o => execFileSync("node", ["hooks/slow-bg.mjs"], { input: JSON.stringify(o), encoding: "utf8" });
  const out = JSON.parse(run({ tool_name: "Bash", tool_input: { command: "pnpm build", description: "d" } }));
  assert.deepStrictEqual(out.hookSpecificOutput.updatedInput, { command: "pnpm build", description: "d", run_in_background: true });
  assert.strictEqual(out.hookSpecificOutput.permissionDecision, undefined);
  assert.strictEqual(run({ tool_name: "Bash", tool_input: { command: "pnpm build", run_in_background: true } }), "");
  assert.strictEqual(run({ tool_name: "Bash", agent_id: "a1", tool_input: { command: "pnpm build" } }), "");
  assert.strictEqual(run({ tool_name: "Bash", tool_input: { command: "git status" } }), "");
});
