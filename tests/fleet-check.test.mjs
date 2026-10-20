// fleet-check: runs read-only against the live SISO Code state; skips where that state is not on this machine.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';

const db = `${homedir()}/.local/state/siso-code/userdata/statev2.sqlite`;
const seats = `${homedir()}/.local/state/agent-base/t3-seats.json`;
const fleet = new URL('../bin/fleet-check', import.meta.url).pathname;
const fresh = new URL('../bin/seat-fresh-t3', import.meta.url).pathname;

function fixture(t, count = 801) {
  const dir = mkdtempSync(join(tmpdir(), 'seat-fresh-test-'));
  t.after(() => rmSync(dir, { recursive: true }));
  const database = join(dir, 'state.sqlite');
  const map = join(dir, 'seats.json');
  const old = {
    id: 'old', title: 'TOKENS', projectId: 'project',
    modelSelection: { instanceId: 'claude-fuze', model: 'fixture-model', options: [{ id: 'effort', value: 'high' }] },
    runtimeMode: 'full-access', interactionMode: 'default',
    worktreePath: '/fixture/worktree', branch: 'siso/seat', archivedAt: null,
  };
  writeFileSync(map, JSON.stringify({ TOKENS: { thread: 'old', cwd: '/fixture/project', note: 'keep me' }, OTHER: { thread: 'other', cwd: '/other' } }));
  execFileSync('python3', ['-c', `
import sqlite3,sys,json
c=sqlite3.connect(sys.argv[1])
c.executescript('''
create table orchestration_v2_projection_threads (thread_id text, title text, payload_json text);
create table orchestration_v2_projection_turn_items (thread_id text, turn_item_id text);
create table orchestration_v2_projection_runs (thread_id text,run_id text,ordinal integer,status text,requested_at text,completed_at text,payload_json text);
create table orchestration_v2_projection_messages (thread_id text,message_id text,run_id text,role text,streaming integer,created_at text,payload_json text);
create table orchestration_events (aggregate_kind text,stream_id text,occurred_at text,sequence integer);
create table orchestration_v2_projection_run_attempts (run_id text,attempt_ordinal integer,payload_json text);
''')
c.execute('insert into orchestration_v2_projection_threads values (?,?,?)',('old','TOKENS',sys.argv[2]))
c.executemany('insert into orchestration_v2_projection_turn_items values (?,?)',[('old',str(i)) for i in range(int(sys.argv[3]))])
c.execute('insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)',('old','message','previous-run','assistant',0,'2026-10-15T10:00:00Z',json.dumps({'text':'Last completed answer.\\nPreserve the second line.'})))
c.execute('insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)',('old','partial','current-run','assistant',1,'2026-10-16T10:00:00Z',json.dumps({'text':'Partial streaming answer'})))
c.commit()
`, database, JSON.stringify(old), String(count)]);
  const sql = (query, params = []) => execFileSync('python3', ['-c',
    'import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1]); c.execute(sys.argv[2],json.loads(sys.argv[3])); c.commit()',
    database, query, JSON.stringify(params)]);
  const flags = ['--db', database, '--seats', map];
  const run = (bin, args) => JSON.parse(execFileSync(bin, [...args, ...flags], { encoding: 'utf8' }));
  return { dir, database, map, old, sql, flags, run };
}

test('LONG is off by default; --long-items N flags at N items, inclusive (Shaan 17 Oct: item count costs nothing)', (t) => {
  const f = fixture(t);
  const row = f.run(fleet, ['--json']).find(r => r.seat === 'TOKENS');
  assert.equal(row.items, 801);
  assert.ok(!row.problems.join('\n').includes('LONG'));
  assert.equal(f.run(fleet, ['--json', '--long-items', '802'])[0].problems.length, 0);
  assert.match(f.run(fleet, ['--json', '--long-items', '801'])[0].problems[0], /^LONG 801 items \(limit 801\)/);
  const printed = execFileSync(fleet, ['--problems', '--long-items', '799', ...f.flags], { encoding: 'utf8' });
  assert.match(printed, /ITEMS/);
  assert.match(printed, /LONG 801/);
  assert.throws(() => execFileSync(fleet, ['--long-items', '-1', ...f.flags], { stdio: 'pipe' }), /0 \(off\) or positive/);
});

test('fresh dry run preserves project, provider options, modes, workspace, and last completed message without writes', (t) => {
  const f = fixture(t);
  const beforeMap = readFileSync(f.map);
  const beforeDB = readFileSync(f.database);
  const plan = f.run(fresh, ['tokens', '--dry-run']);
  assert.equal(plan.mode, 'mcp-plan');
  assert.deepEqual(plan.steps[0], { tool: 't3_thread_configuration', arguments: { threadId: 'old' } });
  const launch = plan.steps[1].arguments;
  for (const key of ['projectId', 'modelSelection', 'runtimeMode', 'interactionMode']) assert.deepEqual(launch[key], f.old[key]);
  assert.deepEqual(launch.workspaceStrategy, { type: 'existing_worktree', worktreePath: '/fixture/worktree', branch: 'siso/seat' });
  assert.match(launch.message, /\/fixture\/project\/\.agents\/HANDOFF.md/);
  assert.match(launch.message, /\/fixture\/project\/AGENTS.md/);
  assert.match(launch.message, /t3_thread_read\(\{"threadId": "old"\}\)/);
  assert.match(launch.message, /Last completed answer.\nPreserve the second line./);
  assert.doesNotMatch(launch.message, /Partial streaming answer/);
  assert.deepEqual(plan.steps[3].arguments, { threadId: 'old', action: 'archive' });
  assert.deepEqual(readFileSync(f.map), beforeMap);
  assert.deepEqual(readFileSync(f.database), beforeDB);
  assert.equal(existsSync(f.map + '.lock'), false);
  assert.equal(plan.reason, 'Dry run only; normal execution uses authenticated MCP.');
});

test('Agent Zero and AGENT-BASE use the same plan path; active runs are reported and root workspace retained', (t) => {
  const f = fixture(t);
  f.old.worktreePath = null;
  f.old.branch = 'main';
  f.sql('update orchestration_v2_projection_threads set payload_json=?', [JSON.stringify(f.old)]);
  f.sql('insert into orchestration_v2_projection_runs values (?,?,?,?,?,?,?)', ['old', 'busy', 1, 'running', '2026-10-16T00:00:00Z', null, '{}']);
  for (const name of ['Agent Zero', 'AGENT-BASE']) {
    writeFileSync(f.map, JSON.stringify({ [name]: { thread: 'old', cwd: '/fixture/project' } }));
    const p = f.run(fresh, [name, '--dry-run']);
    assert.equal(p.seat, name);
    assert.deepEqual(p.activeRunIds, ['busy']);
    assert.deepEqual(p.steps[1].arguments.workspaceStrategy, { type: 'root', branch: 'main' });
  }
});

test('adoption refuses unsafe transitions, then preserves unrelated metadata and is retry-safe', (t) => {
  const f = fixture(t);
  const args = ['TOKENS', '--adopt', 'new', '--expected-thread', 'old'];
  const before = readFileSync(f.map);
  const replacement = { ...f.old, id: 'new' };
  f.sql('insert into orchestration_v2_projection_threads values (?,?,?)', ['new', 'TOKENS', JSON.stringify(replacement)]);
  assert.throws(() => f.run(fresh, args), /Old thread must be archived/);
  f.old.archivedAt = '2026-10-16T10:00:00Z';
  f.sql('update orchestration_v2_projection_threads set payload_json=? where thread_id=?', [JSON.stringify(f.old), 'old']);
  replacement.modelSelection = { instanceId: 'wrong-login', model: 'wrong-model' };
  f.sql('update orchestration_v2_projection_threads set payload_json=? where thread_id=?', [JSON.stringify(replacement), 'new']);
  assert.throws(() => f.run(fresh, args), /settings or workspace differ/);
  replacement.modelSelection = f.old.modelSelection;
  f.sql('update orchestration_v2_projection_threads set payload_json=? where thread_id=?', [JSON.stringify(replacement), 'new']);
  f.sql('insert into orchestration_v2_projection_runs values (?,?,?,?,?,?,?)', ['old', 'queued', 1, 'queued', '2026-10-16T00:00:00Z', null, '{}']);
  assert.throws(() => f.run(fresh, args), /active\/queued runs/);
  assert.deepEqual(readFileSync(f.map), before);
  f.sql('delete from orchestration_v2_projection_runs');
  assert.throws(() => f.run(fresh, [...args, '--dry-run']), /cannot be combined/);
  assert.equal(f.run(fresh, args).status, 'adopted');
  const map = JSON.parse(readFileSync(f.map, 'utf8'));
  assert.deepEqual(map.TOKENS, { thread: 'new', previous_thread: 'old', cwd: '/fixture/project', note: 'keep me' });
  assert.deepEqual(map.OTHER, JSON.parse(before).OTHER);
  assert.equal(f.run(fresh, args).status, 'already-adopted');
  assert.throws(() => f.run(fresh, ['TOKENS', '--adopt', 'different', '--expected-thread', 'old']), /Seat changed/);
});

test('fleet-check --json lists seats with status and problems', { skip: !existsSync(db) || !existsSync(seats) }, () => {
  const rows = JSON.parse(execFileSync(fleet, ['--json'], { encoding: 'utf8' }));
  assert.ok(Array.isArray(rows) && rows.length > 0);
  for (const r of rows) {
    assert.equal(typeof r.seat, 'string');
    assert.equal(typeof r.status, 'string');
    assert.ok(Array.isArray(r.problems));
    assert.equal(typeof r.items, 'number');
  }
});

test('a seat with runsOn mini is read from the mini over one ssh call; ssh down shows unreachable, not no runs', (t) => {
  const f = fixture(t);
  const home = join(f.dir, 'minihome');
  const remoteDb = join(home, '.local/state/siso-code/userdata/statev2.sqlite');
  mkdirSync(join(home, '.local/state/siso-code/userdata'), { recursive: true });
  const live = fixture(t, 3);
  writeFileSync(remoteDb, readFileSync(live.database));
  const sql = (query, params) => execFileSync('python3', ['-c',
    'import sqlite3,sys,json; c=sqlite3.connect(sys.argv[1]); c.execute(sys.argv[2],json.loads(sys.argv[3])); c.commit()', remoteDb, query, JSON.stringify(params)]);
  sql('insert into orchestration_v2_projection_runs values (?,?,?,?,?,?,?)', ['old', 'r1', 1, 'completed', '2026-10-16T00:00:00Z', '2026-10-16T00:05:00Z', '{}']);
  sql('insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)', ['old', 'm', 'r1', 'assistant', 0, '2026-10-16T00:05:00Z', JSON.stringify({ text: 'Mini seat is working.' })]);
  // laptop DB: TOKENS has a STOP-class last turn; the mini seat's thread is not in it
  f.sql('insert into orchestration_v2_projection_runs values (?,?,?,?,?,?,?)', ['old', 'lr', 1, 'completed', '2026-10-16T00:00:00Z', '2026-10-16T00:05:00Z', '{}']);
  f.sql('insert into orchestration_v2_projection_messages values (?,?,?,?,?,?,?)', ['old', 'lm', 'lr', 'assistant', 0, '2026-10-16T00:06:00Z', JSON.stringify({ text: 'I build the scorecard, then the gold brief.' })]);
  writeFileSync(f.map, JSON.stringify({ TOKENS: { thread: 'old', cwd: '/x' }, 'AGENT-BASE': { thread: 'old', cwd: '/y', runsOn: 'mini' } }));
  const calls = join(f.dir, 'ssh-calls');
  const ssh = join(f.dir, 'ssh');
  writeFileSync(ssh, `#!/bin/sh\necho "$*" >> ${calls}\n[ -n "$FAKE_SSH_DOWN" ] && { echo 'ssh: connect timed out' >&2; exit 255; }\nHOME=${home} exec python3 -\n`);
  chmodSync(ssh, 0o755);
  const run = (env) => JSON.parse(execFileSync(fleet, ['--json', ...f.flags], { encoding: 'utf8', env: { ...process.env, FLEET_CHECK_SSH: ssh, ...env } }));

  const rows = run({});
  const mini = rows.find(r => r.seat === 'AGENT-BASE');
  assert.equal(mini.status, 'completed');
  assert.equal(mini.said, 'Mini seat is working.');
  assert.equal(mini.problems.length, 0);
  assert.match(readFileSync(calls, 'utf8'), /^-o RemoteCommand=none -o RequestTTY=no -o ConnectTimeout=5 mini-fast python3 -\n$/);

  const down = run({ FAKE_SSH_DOWN: '1' });
  const gone = down.find(r => r.seat === 'AGENT-BASE');
  assert.equal(gone.status, 'unreachable (mini)');
  assert.match(gone.problems[0], /^UNREACHABLE mini: ssh: connect timed out/);
  assert.equal(down.find(r => r.seat === 'TOKENS').status, 'completed');

  // a warning prints under its own seat, tagged with that seat's name
  const printed = execFileSync(fleet, [...f.flags], { encoding: 'utf8', env: { ...process.env, FLEET_CHECK_SSH: ssh, FAKE_SSH_DOWN: '1' } }).split('\n');
  for (const [i, line] of printed.entries()) {
    if (!line.includes('! [')) continue;
    const owner = line.match(/! \[([^\]]+)\]/)[1];
    const head = printed.slice(0, i).reverse().find(l => !l.includes('! ['));
    assert.ok(head.startsWith(owner), `${line} printed under ${head}`);
  }
});
