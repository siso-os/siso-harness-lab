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
import { readsOnly } from "../hooks/fetch-nudge.mjs";
test("14 Oct: Bash judged piece by piece", () => {
  for (const c of ["echo '== a'; sed -n 1,20p a.ts; echo; grep -n x b.ts", "git -C repo log --oneline -5", "grep -rn foo src | sort | uniq -c | head",
    "for f in a b; do wc -l $f; done", "cat x 2>/dev/null | head", "ls -la > /dev/null", "rr 'git status -s' 'ls'", "cd /x && git --no-pager diff --stat"])
    assert.strictEqual(readsOnly(c), true, c);
  for (const c of ["echo hi > f.txt", "sed -i '' s/a/b/ f", "python3 - <<'EOF'\nprint(1)\nEOF", "git -C r commit -m x", "cat a | tee b",
    "npm test", "mkdir -p x && ls x", "heavy -- npx tsc", ""])
    assert.strictEqual(readsOnly(c), false, c);
});
test("14 Oct: TodoWrite and ToolSearch neither count nor end a run", () => {
  let s = null, out = [];
  for (const t of ["Read", "TodoWrite", "Grep", "ToolSearch", "Read"]) { const r = step(s, { tool_name: t }, 1000); s = r.state; out.push(r.nudge); }
  assert.deepStrictEqual(out, [false, false, false, false, true]);
});

test("14 Oct: gh/curl GETs, xargs and heavy wrappers are reads; code heredocs are not", async () => {
  const { readsOnly } = await import("../hooks/fetch-nudge.mjs");
  for (const c of ["gh pr view 12 --json state", "curl -s http://127.0.0.1:8891/api/x | jq .", "heavy -- rg foo src", "find . -name x | xargs grep -l y", "git log -3 2>&1 | head"])
    assert.equal(readsOnly(c), true, c);
  for (const c of ["gh api -X POST repos/x", "curl -s -d a=1 http://x", "python3 - <<'X'\nimport os\nX", "ssh vps 'make build'", "cd x && grep a b && node -e 'x'"])
    assert.equal(readsOnly(c), false, c);
});

test("15 Oct: a remote read over ssh is a read; a remote write is not", async () => {
  const { readsOnly } = await import("../hooks/fetch-nudge.mjs");
  for (const c of ["ssh vps 'cat /etc/x | head -5'", "ssh -o ConnectTimeout=5 halo-vps \"grep -n foo /srv/a.log\""])
    assert.equal(readsOnly(c), true, c);
  for (const c of ["ssh vps 'rm /tmp/x'", "ssh vps", "ssh vps 'systemctl restart x'"])
    assert.equal(readsOnly(c), false, c);
});
