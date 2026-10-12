import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { parse, send } from '../scripts/herdr-send.mjs';

const thread = '11111111-1111-4111-8111-111111111111';
const queue = '22222222-2222-4222-8222-222222222222';
function fixture(t, overrides = {}) {
  const root = mkdtempSync(join(tmpdir(), 'harness-sender-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const calls = [], draft = 'UNSENT USER DRAFT\nline two';
  let reads = 0;
  const agent = { name: 'OWNER', label: 'OWNER', terminal_id: 'term_stable', pane_id: 'pane-1', cwd: '/fixture',
    agent: overrides.agent ?? 'codex', agent_status: overrides.busy ? 'working' : 'idle',
    agent_session: { kind: 'id', value: thread, agent: overrides.agent ?? 'codex' } };
  const run = (file, args) => {
    calls.push([file, ...args]);
    if (file === 'herdr' && args[0] === 'session') return { status: 0, stdout: JSON.stringify({ sessions: [
      { name: 'default', running: !overrides.down, socket_path: '/fixture/default.sock' },
      { name: 'other', running: true, socket_path: '/fixture/other.sock' },
    ] }) };
    if (file === 'herdr' && args[2] === 'agent' && args[3] === 'list') {
      reads++;
      const a = structuredClone(agent);
      if (reads > 1 && overrides.reflow) a.pane_id = 'pane-99';
      if (reads > 1 && overrides.replaced) a.agent_session.value = queue;
      return { status: 0, stdout: JSON.stringify({ result: { agents: overrides.ambiguous ? [a, { ...a, terminal_id: 'term_other' }] : [a] } }) };
    }
    if (file === 'codex') {
      assert.deepEqual(args.slice(0, 4), ['queue', '--thread', thread, '--message']);
      if (overrides.throw) throw new Error('interrupted; PRIVATE MESSAGE');
      return overrides.queueResult ?? { status: 0, stdout: `Queued message ${queue} for thread ${thread}.\n` };
    }
    throw new Error('Forbidden composer/key/read operation ' + JSON.stringify([file, ...args]));
  };
  return { root, calls, draft, options: { run, receiptDir: join(root, 'receipts') }, agent };
}
const queueCalls = f => f.calls.filter(c => c[0] === 'codex');

test('both legacy CLI contracts resolve to the same request; multiline/file bytes survive', t => {
  const f = fixture(t), text = 'quotes " and $shell\nsecond line\n';
  const path = join(f.root, 'message'); writeFileSync(path, text);
  const a = send(parse(['OWNER', text]), f.options);
  const b = send(parse(['--to', 'OWNER', '--file', path, '--expect-identity', 'OWNER']), f.options);
  assert.equal(a.state, 'queued'); assert.equal(a.processed, false);
  assert.equal(b.exitCode, 5); assert.equal(b.queueId, a.queueId);
  assert.equal(queueCalls(f).length, 1); assert.equal(queueCalls(f)[0].at(-1), text);
  assert.ok(!readFileSync(a.receiptPath, 'utf8').includes(text));
});

for (const busy of [false, true]) for (const agent of ['codex', 'claude']) {
  test(`${busy ? 'busy' : 'idle'} ${agent}: existing draft untouched; no status-as-delivery proof`, t => {
    const f = fixture(t, { busy, agent });
    const result = send(parse(['OWNER', 'message']), f.options);
    assert.equal(result.state, agent === 'codex' ? 'queued' : 'unsupported');
    assert.equal(result.processed, false);
    assert.equal(queueCalls(f).length, agent === 'codex' ? 1 : 0);
    assert.equal(f.draft, 'UNSENT USER DRAFT\nline two');
    assert.ok(f.calls.every(c => !c.includes('send-keys') && !c.includes('send-text') && !c.includes('read')));
  });
}

test('pane reflow keeps pinned session, but session replacement refuses submission', t => {
  const f = fixture(t, { reflow: true });
  assert.equal(send(parse(['OWNER', 'hello']), f.options).state, 'queued');
  const other = fixture(t, { replaced: true });
  assert.equal(send(parse(['OWNER', 'hello']), other.options).state, 'unconfirmed');
  assert.equal(queueCalls(other).length, 0);
});

for (const changes of [{ ambiguous: true }, { down: true }]) {
  test(`refuses bad target/server ${JSON.stringify(changes)}`, t => {
    const f = fixture(t, changes);
    assert.throws(() => send(parse(['OWNER', 'hello']), f.options));
    assert.equal(queueCalls(f).length, 0);
  });
}

test('wrong server and identity expression fail without typing; force cannot bypass identity', t => {
  const f = fixture(t);
  assert.throws(() => send(parse(['OWNER', 'hello', '--session', 'missing']), f.options));
  assert.throws(() => send(parse(['--to', 'OWNER', '--text', 'hello', '--expect-identity', '^OTHER$', '--force']), f.options));
  assert.equal(queueCalls(f).length, 0);
});

for (const queueResult of [
  { status: 7, stdout: '' }, { status: 0, stdout: 'working' },
  { status: 0, stdout: `Queued message ${queue} for thread ${queue}.` },
  { status: null, error: { code: 'ETIMEDOUT' }, stdout: '' },
]) {
  test(`unconfirmed transport never resends: ${JSON.stringify(queueResult)}`, t => {
    const f = fixture(t, { queueResult });
    const opts = parse(['OWNER', 'hello', '--retries', '50']);
    assert.equal(send(opts, f.options).state, 'unconfirmed');
    assert.equal(send(opts, f.options).exitCode, 70);
    assert.equal(queueCalls(f).length, 1);
  });
}

test('throw/crash reservation refuses a retry, and fingerprint payload collision is rejected', t => {
  const f = fixture(t, { throw: true });
  const a = send(parse(['OWNER', 'hello', '--fingerprint', 'one']), f.options);
  assert.equal(a.state, 'unconfirmed');
  assert.throws(() => send(parse(['OWNER', 'different', '--fingerprint', 'one']), f.options));
  assert.equal(queueCalls(f).length, 1);
});

test('dry-run does not reserve delivery; legacy sent audit prevents unsafe resend', t => {
  const f = fixture(t), audit = join(f.root, 'audit.jsonl');
  const opts = ['OWNER', 'hello', '--audit', audit, '--fingerprint', 'once'];
  assert.equal(send(parse([...opts, '--dry-run']), f.options).state, 'dry-run');
  assert.equal(queueCalls(f).length, 0);
  writeFileSync(audit, JSON.stringify({ fingerprint: 'once', outcome: 'DRY_RUN' }) + '\n');
  assert.equal(send(parse(opts), f.options).state, 'queued');
  assert.equal(send(parse(opts), f.options).exitCode, 5);
  assert.equal(queueCalls(f).length, 1);
});

test('legacy SENT audit is not upgraded to proof or resent after migration', t => {
  const f = fixture(t), audit = join(f.root, 'old-audit');
  writeFileSync(audit, JSON.stringify({ fingerprint: 'old', outcome: 'SENT' }) + '\n');
  const r = send(parse(['OWNER', 'hello', '--audit', audit, '--fingerprint', 'old']), f.options);
  assert.equal(r.state, 'unconfirmed'); assert.equal(r.processed, false);
  assert.equal(queueCalls(f).length, 0);
});

test('unavailable/malformed inventory and corrupt/symlink receipt fail closed', t => {
  const f = fixture(t);
  assert.throws(() => send(parse(['OWNER', 'hello']), { ...f.options, run: () => ({ status: 0, stdout: '{}' }) }));
  const preview = send(parse(['OWNER', 'hello', '--dry-run']), f.options);
  mkdirSync(join(f.root, 'receipts'));
  const unrelated = join(f.root, 'user-file'); writeFileSync(unrelated, 'preserve');
  symlinkSync(unrelated, preview.receiptPath);
  assert.throws(() => send(parse(['OWNER', 'hello']), f.options));
  assert.equal(readFileSync(unrelated, 'utf8'), 'preserve');
  assert.equal(queueCalls(f).length, 0);
});

test('argument mistakes never reach transport', () => {
  for (const args of [['--to'], ['--to', 'X', '--text', 'a', '--file', 'b'], ['X'], ['--to', 'X', '--text', 'a', '--unknown'], ['X', 'a', '--session', 'a', '--session', 'b']]) assert.throws(() => parse(args));
});

test('compatibility: leading dashes in message text remain literal in both forms', t => {
  const f = fixture(t);
  const text = '--not-a-flag\nnext line';
  assert.equal(send(parse(['OWNER', text]), f.options).state, 'queued');
  assert.equal(send(parse(['--to', 'OWNER', '--text', text]), f.options).exitCode, 5);
  assert.equal(queueCalls(f)[0].at(-1), text);
});

test('held-out: concurrent processes make only one queue attempt', async t => {
  const f = fixture(t), journal = join(f.root, 'queue-calls');
  const core = new URL('../scripts/herdr-send.mjs', import.meta.url).href;
  const code = `import{send,parse}from ${JSON.stringify(core)};import{appendFileSync}from'node:fs';
    const run=(file,args)=>file==='codex'?(appendFileSync(${JSON.stringify(journal)},'queue\\n'),{status:0,stdout:'Queued message ${queue} for thread ${thread}.\\n'}):
    args[0]==='session'?{status:0,stdout:JSON.stringify({sessions:[{name:'default',running:true,socket_path:'/x'}]})}:
    {status:0,stdout:JSON.stringify({result:{agents:[{name:'OWNER',terminal_id:'t',agent:'codex',agent_session:{kind:'id',value:'${thread}',agent:'codex'}}]}})};
    try{console.log(JSON.stringify(send(parse(['OWNER','hello']),{run,receiptDir:${JSON.stringify(join(f.root, 'receipts'))}})))}catch(e){console.log(JSON.stringify({refused:true}))}`;
  const start = () => new Promise(resolve => {
    const child = spawn(process.execPath, ['--input-type=module', '-e', code]);
    let text = ''; child.stdout.on('data', d => { text += d; }); child.on('exit', exit => resolve({ exit, text }));
  });
  const results = await Promise.all([start(), start()]);
  assert.ok(results.every(r => r.exit === 0));
  assert.equal(readFileSync(journal, 'utf8'), 'queue\n');
  assert.equal(results.filter(r => JSON.parse(r.text).state === 'queued' && !JSON.parse(r.text).duplicate).length, 1);
});

test('held-out: truncated receipt and wrong queue acknowledgement never become success', t => {
  const f = fixture(t);
  const plan = send(parse(['OWNER', 'payload', '--dry-run']), f.options);
  mkdirSync(join(f.root, 'receipts'));
  writeFileSync(plan.receiptPath, '{"version":1,"state":"queued"}');
  assert.throws(() => send(parse(['OWNER', 'payload']), f.options));
  assert.equal(queueCalls(f).length, 0);
});

test('a tab title names the recipient (herdr agent list sets no name/label), case-insensitively; ids still match exactly', t => {
  const f = fixture(t);
  delete f.agent.name; delete f.agent.label; f.agent.terminal_title_stripped = 'EFFICIENCY';
  for (const to of ['EFFICIENCY', 'efficiency', 'term_stable', 'pane-1', thread]) {
    const r = send(parse([to, 'hi', '--fingerprint', 'fp-' + to]), f.options);
    assert.equal(r.state, 'queued', to);
  }
  assert.throws(() => send(parse(['effic', 'hi']), f.options), { exitCode: 4 }, 'a prefix is not a name');
  const c = fixture(t, { agent: 'claude' }); delete c.agent.name; delete c.agent.label; c.agent.terminal_title_stripped = 'HEALTH';
  const r = send(parse(['health', 'hi']), c.options);
  assert.equal(r.state, 'unsupported'); assert.match(r.reason, /a0-tell/);
});
