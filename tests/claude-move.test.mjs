import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/claude-move", import.meta.url).pathname;
const ID = "11111111-2222-3333-4444-555555555555";

// A fake herdr: the pane shows a prompt until /exit is typed, then Claude's exit line; typing the resume command makes
// the agent answer (an assistant line in $ANSWER) unless ANSWER is empty. process-info reports $FAKE_PGID as the pane.
function fixture({ pgid = 999999, answer = true, menu = false, noOption2 = false, model = null } = {}) {
  const home = mkdtempSync(path.join(tmpdir(), "claude-move-"));
  const src = path.join(home, ".config", "claude-siso-3", "projects", "-x"); mkdirSync(path.join(src, ID), { recursive: true });
  writeFileSync(path.join(src, ID + ".jsonl"), JSON.stringify({ type: "assistant", message: { ...(model ? { model } : {}), content: "before" } }) + "\n");
  const fb = path.join(home, "bin"); mkdirSync(fb);
  const dstFile = path.join(home, ".claude", "projects", "-x", ID + ".jsonl");
  writeFileSync(path.join(fb, "herdr"), `#!/bin/sh
echo "$*" >> "${home}/herdr.log"
case "$1 $2" in
  "pane process-info") echo '{"result":{"process_info":{"foreground_process_group_id":${pgid},"foreground_processes":[]}}}' ;;
  "pane read") if [ -f "${home}/exited" ]; then echo "Resume this session with: claude --resume x";
    elif [ -f "${home}/backgrounded" ]; then echo "backgrounded · ab12cd34"; echo "  claude attach ab12cd34";
    elif [ -f "${home}/menu" ]; then printf '   Background work is running\\n   The following will stop when you exit:\\n\\n   shell · sleep 900\\n   monitor · tail -f x\\n\\n   ❯ 1. Exit and stop tasks\\n${noOption2 ? "" : "     2. Move to background and exit\\n"}     3. Stay\\n'; else echo "❯ "; fi ;;
  "pane send-keys") echo "$4" >> "${home}/keys"; [ "$4" = 2 ] && touch "${home}/backgrounded" ;;
  "pane run") case "$4" in /exit) ${menu ? `touch "${home}/menu"` : `touch "${home}/exited"`} ;; *) ${answer ? `echo '{"type":"assistant","message":{"content":"back"}}' >> "${dstFile}"` : ":"} ;; esac ;;
esac
`, { mode: 0o755 });
  const env = { ...process.env, HOME: home, PATH: `${fb}:${process.env.PATH}`, CLAUDE_MOVE_WAIT: "3" };
  delete env.HERDR_PANE_ID; delete env.HERDR_PANE;
  const run = (e = {}, to = "claude-siso") => spawnSync(bin, ["PROBE", "w9:p1", ID, to], { env: { ...env, ...e }, encoding: "utf8" });
  const typed = () => (existsSync(path.join(home, "herdr.log")) ? readFileSync(path.join(home, "herdr.log"), "utf8") : "").split("\n").filter(l => l.startsWith("pane run"));
  const keys = () => (existsSync(path.join(home, "keys")) ? readFileSync(path.join(home, "keys"), "utf8").trim() : "");
  return { home, src, dstFile, run, typed, keys, env };
}

test("claude-move refuses the caller's own pane (env or process ancestry) and plain claude, typing nothing", () => {
  const a = fixture();
  let r = a.run({ HERDR_PANE_ID: "w9:p1" });
  assert.equal(r.status, 2, r.stderr); assert.match(r.stderr, /your own pane/); assert.deepEqual(a.typed(), []);
  const b = fixture({ pgid: process.pid });  // the test runner is an ancestor of claude-move: the caller lives in that pane
  r = b.run();
  assert.equal(r.status, 2, r.stderr); assert.match(r.stderr, /your own pane/); assert.deepEqual(b.typed(), []);
  r = a.run({}, "claude");
  assert.equal(r.status, 2); assert.match(r.stderr, /Fahmy/); assert.deepEqual(a.typed(), []);
});

test("claude-move retires the source copy as <id>.jsonl.moved-to-<login>-<date> once the resumed agent answers", () => {
  const f = fixture();
  const r = f.run();
  assert.equal(r.status, 0, r.stderr);
  const day = new Date().toLocaleDateString("en-CA");
  assert.deepEqual(readdirSync(f.src).sort(), [`${ID}.jsonl.moved-to-claude-siso-${day}`, `${ID}.moved-to-claude-siso-${day}`]);
  assert.match(readFileSync(f.dstFile, "utf8"), /"back"/);
  assert.equal(f.typed().length, 2, "/exit, then the resume command");
});

test("claude-move keeps the source copy and exits 5 when the resumed agent never answers", () => {
  const f = fixture({ answer: false });
  const r = f.run();
  assert.equal(r.status, 5, r.stderr); assert.match(r.stderr, /source copy kept/);
  assert.ok(existsSync(path.join(f.src, ID + ".jsonl")));
});

test("claude-move answers the 'Background work is running' menu with 2, reports what moved, and resumes on the model the agent was running", () => {
  const f = fixture({ menu: true, model: "claude-sonnet-5-5" });
  const r = f.run();
  assert.equal(r.status, 0, r.stderr);
  assert.equal(f.keys(), "2", "only option 2 was pressed, never 1");
  assert.match(r.stdout, /background work \(shell · sleep 900; monitor · tail -f x\); moved to background session ab12cd34/);
  const resume = f.typed().at(-1);
  assert.match(resume, /--model claude-sonnet-5-5 /, "the session's own model, not a fixed Opus");
  assert.match(resume, new RegExp("--resume " + ID), "resumes the same session");
  const g = fixture({ model: "claude-sonnet-5-5" });
  assert.equal(g.run({}, "claude-siso").status, 0);
  assert.match(g.typed().at(-1), /--model claude-sonnet-5-5 /);
});

test("claude-move --model overrides the default; with no model in the transcript it falls back to Opus", () => {
  const a = fixture({ model: "claude-sonnet-5-5" });
  const r = spawnSync(bin, ["--model", "claude-haiku-4-5", "PROBE", "w9:p1", ID, "claude-siso"], { env: a.env, encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr); assert.match(a.typed().at(-1), /--model claude-haiku-4-5 /);
  const b = fixture();
  assert.equal(b.run().status, 0); assert.match(b.typed().at(-1), /--model claude-opus-5-5 /);
});

test("claude-move never presses 1: a background-work menu without option 2 stops it (exit 4)", () => {
  const f = fixture({ menu: true, noOption2: true });
  const r = f.run();
  assert.equal(r.status, 4, r.stderr); assert.match(r.stderr, /not stopping its tasks/); assert.equal(f.keys(), "");
});
