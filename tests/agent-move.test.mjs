import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, chmodSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/agent-move", import.meta.url).pathname;
const SID = "11111111-2222-3333-4444-555555555555";
const CID = "01a0fbb8-883a-75a0-bf82-f45a95928ab9";

function fixture() {
  const home = mkdtempSync(path.join(tmpdir(), "agent-move-"));
  const proj = path.join(home, ".claude", "projects", "-x"); mkdirSync(proj, { recursive: true });
  const ts = m => `2026-10-02T07:${String(m).padStart(2, "0")}:00Z`;
  const L = [
    { type: "user", timestamp: ts(1), cwd: "/nowhere", agentName: "PROBE", message: { content: "You are PROBE. Budget is 4,730 credits." } },
    { type: "user", isMeta: true, timestamp: ts(2), message: { content: "<local-command-caveat>meta</local-command-caveat>" } },
    { type: "assistant", timestamp: ts(3), message: { id: "a1", model: "claude-opus-5-5", usage: { input_tokens: 10, cache_read_input_tokens: 5000 },
      content: [{ type: "text", text: "Noted the budget." }, { type: "tool_use", name: "Write", input: { file_path: "/tmp/probe-note.txt" } }] } },
    { type: "user", timestamp: ts(4), message: { content: [{ type: "tool_result", content: "TOOL OUTPUT SHOULD NOT MOVE" }] } },
    { type: "user", timestamp: ts(5), message: { content: "<task-notification>bg done</task-notification>" } },
    { type: "user", timestamp: ts(6), message: { content: "Stop hook feedback:\nnot a person" } },
    { timestamp: ts(7), attachment: { type: "queued_command", prompt: "A0: mid-turn ask, codename Juniper" } },
    { type: "user", isCompactSummary: true, timestamp: ts(8), message: { content: "SUMMARY: the reviewer is Okonkwo" } },
    { type: "user", timestamp: ts(9), message: { content: [{ type: "text", text: "Key is sk-abcdefghijklmnopqrstuvwxyz123456 <system-reminder>noise</system-reminder>" }] } },
    { type: "assistant", timestamp: ts(10), message: { id: "a2", model: "claude-opus-5-5", content: [{ type: "text", text: "Next: email Priya." }] } },
  ];
  writeFileSync(path.join(proj, SID + ".jsonl"), L.map(x => JSON.stringify(x)).join("\n") + "\n");
  const cs = path.join(home, ".codex", "sessions", "2026", "10", "02"); mkdirSync(cs, { recursive: true });
  const C = [
    { timestamp: ts(1), type: "session_meta", payload: { cwd: "/nowhere" } },
    { timestamp: ts(1), type: "turn_context", payload: { model: "gpt-6-luna", cwd: "/nowhere" } },
    { timestamp: ts(2), type: "response_item", payload: { type: "message", role: "user", content: [{ type: "input_text", text: "# AGENTS.md instructions for /x" }] } },
    { timestamp: ts(3), type: "response_item", payload: { type: "message", role: "user", content: [{ type: "input_text", text: "Fix the tally, keep out of quarry" }] } },
    { timestamp: ts(4), type: "response_item", payload: { type: "custom_tool_call", name: "apply_patch", input: "*** Begin Patch\n*** Update File: src/a.ts\n" } },
    { timestamp: ts(5), type: "response_item", payload: { type: "message", role: "assistant", content: [{ type: "output_text", text: "Patched src/a.ts" }] } },
  ];
  writeFileSync(path.join(cs, `rollout-2026-10-02T07-00-00-${CID}.jsonl`), C.map(x => JSON.stringify(x)).join("\n") + "\n");
  writeFileSync(path.join(home, "registry.json"), JSON.stringify({ agents: { PROBE: { role: "test seat", project: "LABS", owner: "A0" } } }));
  const agents = [
    { agent: "claude", name: "probe", pane_id: "w1:p1", tab_id: "w1:t1", workspace_id: "w1", cwd: "/nowhere", agent_status: "idle",
      terminal_title_stripped: "PROBE", agent_session: { kind: "id", value: SID } },
    { agent: "codex", name: "busy-one", pane_id: "w1:p2", tab_id: "w1:t2", workspace_id: "w1", agent_status: "working",
      agent_session: { kind: "id", value: CID } },
  ];
  writeFileSync(path.join(home, "agents.json"), JSON.stringify({ result: { agents } }));
  const herdr = path.join(home, "herdr");
  writeFileSync(herdr, `#!/bin/sh\n[ "$1 $2" = "agent list" ] && exec cat "${path.join(home, "agents.json")}"\necho '{}'\n`);
  chmodSync(herdr, 0o755);
  const env = { ...process.env, HOME: home, HERDR_BIN: herdr, SPEND_REGISTRY: path.join(home, "registry.json"),
    AGENT_MOVE_STATE: path.join(home, "state"), DEV_LEASE_DIR: path.join(home, "leases") };
  return { home, env };
}

test("Claude passport: every person's ask incl. mid-turn ones, the summary, replies and files; no tool output, hooks or secrets", () => {
  const { env } = fixture();
  const r = JSON.parse(execFileSync(bin, ["passport", "probe", "--json"], { env, encoding: "utf8" }));
  assert.equal(r.asks, 3, "first ask, the queued mid-turn ask, the later typed ask");
  assert.equal(statSync(r.passport).mode & 0o777, 0o600);
  const md = readFileSync(r.passport, "utf8");
  assert.match(md, /^# Passport: PROBE/, "herdr's lower-case name resolves to the registry's spelling");
  assert.match(md, /test seat \(project LABS, reports to A0\)/);
  for (const want of ["Budget is 4,730 credits", "codename Juniper", "SUMMARY: the reviewer is Okonkwo", "Next: email Priya", "/tmp/probe-note.txt", "claude-opus-5-5"])
    assert.ok(md.includes(want), `missing ${want}`);
  for (const not of ["TOOL OUTPUT SHOULD NOT MOVE", "bg done", "not a person", "noise", "local-command-caveat", "abcdefghijklmnopqrstuvwxyz123456"])
    assert.ok(!md.includes(not), `leaked ${not}`);
  assert.match(md, /sk-abc…\[masked\]/);
});

test("Codex passport: user asks without the AGENTS.md preamble, assistant text, patched files", () => {
  const { home, env } = fixture();
  const f = path.join(home, ".codex", "sessions", "2026", "10", "02", `rollout-2026-10-02T07-00-00-${CID}.jsonl`);
  const r = JSON.parse(execFileSync(bin, ["passport", "--transcript", f, "--json"], { env, encoding: "utf8" }));
  const md = readFileSync(r.passport, "utf8");
  assert.equal(r.asks, 1);
  assert.match(md, /^# Passport: 01a0fbb8/);
  assert.match(md, /keep out of quarry/);
  assert.match(md, /Patched src\/a\.ts/);
  assert.match(md, /- src\/a\.ts/);
  assert.ok(!md.includes("AGENTS.md instructions"));
});

test("budget: the Markdown fits; replies go first, then the middle asks; the first and newest asks stay", () => {
  const { home, env } = fixture();
  const proj = path.join(home, ".claude", "projects", "-x", SID + ".jsonl");
  const big = "x".repeat(1800);
  const extra = [];
  for (let i = 0; i < 40; i++) extra.push({ type: "user", timestamp: `2026-10-02T08:${String(i).padStart(2, "0")}:00Z`, message: { content: `ask ${i} ${big}` } },
    { type: "assistant", timestamp: `2026-10-02T08:${String(i).padStart(2, "0")}:30Z`, message: { id: "b" + i, content: [{ type: "text", text: `reply ${i} ${big}` }] } });
  writeFileSync(proj, readFileSync(proj, "utf8") + extra.map(x => JSON.stringify(x)).join("\n") + "\n");
  const r = JSON.parse(execFileSync(bin, ["passport", "probe", "--budget", "16", "--json"], { env, encoding: "utf8" }));
  assert.ok(r.bytes <= 16 * 1024, `bytes ${r.bytes}`);
  const md = readFileSync(r.passport, "utf8");
  assert.match(md, /Budget is 4,730 credits/, "the first ask (the assignment) stays");
  assert.match(md, /ask 39 /, "the newest ask stays");
  assert.match(md, /older asks trimmed for size/);
  assert.ok(!/reply 0 /.test(md), "old replies trimmed before asks");
});

test("dry run prints the launch per target; same harness resumes; a working agent is refused", () => {
  const { env } = fixture();
  const run = (...a) => spawnSync(bin, a, { env, encoding: "utf8" });
  let r = JSON.parse(run("probe", "--to", "luna", "--dry-run", "--json").stdout);
  assert.equal(r.kind, "passport");
  assert.match(r.command, /^codex -m gpt-6-luna -c model_reasoning_effort=medium 'You are PROBE, moved here from claude claude-opus-5-5/);
  assert.ok(r.passport_bytes <= 32 * 1024);
  r = JSON.parse(run("probe", "--to", "deepseek", "--dry-run", "--json").stdout);
  assert.match(r.command, /^omp --model smol /);
  r = JSON.parse(run("probe", "--to", "fable", "--dry-run", "--json").stdout);
  assert.equal(r.kind, "resume");
  assert.match(r.command, new RegExp(`^claude-siso --model claude-fable-5-1 --effort high --dangerously-skip-permissions -n PROBE --resume ${SID} `));
  const busy = run("busy-one", "--to", "sol", "--json");
  assert.equal(busy.status, 3);
  assert.equal(run("probe", "--to", "gemini").status, 2);
  assert.equal(run("probe", "--to", "opus", "--login", "claude", "--dry-run").status, 2, "plain claude (Fahmy's) is refused");
  assert.equal(JSON.parse(run("targets", "--json").stdout).length, 6);
});

test("Agent Zero seat transfer: boot, high effort, identity, reply-before-close, stale seat and same-harness resume", () => {
  const { home, env } = fixture();
  const seat = path.join(home, 'seat.json');
  writeFileSync(seat, JSON.stringify({ session: SID, pane: 'w1:p1', login_launcher: 'claude-siso' }));
  const code = `
import importlib.machinery, importlib.util, json, os
loader=importlib.machinery.SourceFileLoader('move_test', ${JSON.stringify(bin)})
m=importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,loader));loader.exec_module(m)
events=[]
rows=m.agents()
m.agents=lambda:rows[:1]
old=json.load(open(m.SEAT))
# Claude wrapper seats use the transcript type and resume the same conversation.
rows[0]['agent']='siso'
code,r=m.move('Agent Zero','sonnet',dry=True)
assert code==0 and r['kind']=='resume' and r['from']['harness']=='claude'
assert '--resume ${SID}' in r['command'] and '--effort high' in r['command']
rows[0]['agent']='claude'
def herdr(*args):
    events.append(args)
    if args[:2]==('tab','create'):
        assert args[args.index('--label')+1]=='Agent Zero'
        return {'result':{'root_pane':{'pane_id':'w1:p3'},'tab':{'tab_id':'w1:t3'}}}
    if args[:2]==('pane','run'):
        assert args[2]=='w1:p3'
        assert 'env SISO_A0=1 ' in args[3]
        assert 'model_reasoning_effort=high' in args[3]
    if args[:2]==('tab','close'):
        assert events[-2][:2]==('agent','rename')
        assert json.load(open(m.SEAT))['session']==${JSON.stringify(CID)}
        assert ('answered',) in events
    return {}
m.herdr=herdr
m.time.sleep=lambda _:None
m.wait_reply=lambda *args,**kwargs: (events.append(('answered',)) or ${JSON.stringify(CID)})
code,r=m.move('Agent Zero','sol')
assert code==0 and r['name']=='agent-zero'
md=open(r['passport']).read()
for file in ('AGENTS.md','PRINCIPLES.md','.agents/HANDOFF.md'):
    assert file in md
assert stat_mode:= (os.stat(m.SEAT).st_mode & 0o777)==0o600
assert ('agent','rename','w1:p3','agent-zero') in events
# A stale seat cannot select the real named row as a fallback.
assert m.find_agent('Agent Zero')==[]
# Codex -> Sol resumes the existing seat conversation and waits beyond existing replies.
a={'agent':'codex','name':'probe','pane_id':'w1:p2','tab_id':'w1:t2','workspace_id':'w1','cwd':'/nowhere','agent_status':'idle','agent_session':{'value':${JSON.stringify(CID)}}}
m.agents=lambda:[a]
json.dump({'session':${JSON.stringify(CID)},'pane':'w1:p2'},open(m.SEAT,'w'))
code,r=m.move('Agent Zero','sol',dry=True)
assert r['kind']=='resume' and 'codex resume ${CID}' in r['command']
# A locked Codex resume falls back to a passport without closing the old tab first.
events.clear()
def locked_then_answered(*args,**kwargs):
    if kwargs.get('session'):
        raise m.ResumeLocked('locked')
    events.append(('answered',))
    return 'fresh-codex-session'
m.wait_reply=locked_then_answered
# Fixture allocates unique tabs for the refused resume and fresh launch.
def fallback_herdr(*args):
    events.append(args)
    if args[:2]==('tab','create'):
        n=sum(e[:2]==('tab','create') for e in events)
        return {'result':{'root_pane':{'pane_id':f'w1:p{n+2}'},'tab':{'tab_id':f'w1:t{n+2}'}}}
    if args[:2]==('tab','close'):
        assert ('answered',) in events
        assert json.load(open(m.SEAT))['session']=='fresh-codex-session'
    return {}
m.herdr=fallback_herdr
code,r=m.move('Agent Zero','sol')
assert code==0 and r['fallback']=='resume-locked' and r['kind']=='passport'
assert events[-1][:2]==('agent','rename'), 'name restored after closing old tabs'
assert 'codex resume' not in r['command'] and 'SISO_A0=1' in r['command']
assert 'Boot first' in open(r['passport']).read()
# Failure after fallback keeps the seat and old tab untouched.
json.dump({'session':${JSON.stringify(CID)},'pane':'w1:p2'},open(m.SEAT,'w'))
events.clear()
def locked_then_failed(*args,**kwargs):
    if kwargs.get('session'):
        raise m.ResumeLocked('locked')
    return None
m.wait_reply=locked_then_failed
code,r=m.move('Agent Zero','sol')
assert code==1 and 'old one is untouched' in r['error']
assert json.load(open(m.SEAT))['session']==${JSON.stringify(CID)}
assert not any(e[:2]==('tab','close') for e in events)
m.herdr=herdr
# Changing the seat while the new process starts preserves the old tab.
json.dump(old,open(m.SEAT,'w'))
m.agents=lambda:[{'agent':'claude','name':'probe','pane_id':'w1:p1','tab_id':'w1:t1','workspace_id':'w1','cwd':'/nowhere','agent_status':'idle','agent_session':{'value':${JSON.stringify(SID)}}}]
events.clear()
def raced(*args,**kwargs):
    json.dump({'session':'relay','pane':'elsewhere'},open(m.SEAT,'w'))
    return ${JSON.stringify(CID)}
m.wait_reply=raced
code,r=m.move('Agent Zero','sol')
assert code==1 and 'seat changed' in r['error']
assert not any(e[:2]==('tab','close') for e in events)
print('PASS seat, boot, high effort, reply-before-close, resume, concurrent relay retention')
`.replace('assert stat_mode:= ', 'assert ');
  const result = spawnSync('python3', ['-c', code], { env: { ...env, AB_A0_SEAT: seat }, encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr || result.stdout);
});
