// On-demand isolated real Codex queue probe. No model turn is started, no auth is
// copied, no live thread is targeted. The isolated home is retained for readback.
import { spawn, spawnSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { send, parse } from './herdr-send.mjs';

const root = resolve('.local'); mkdirSync(root, { recursive: true });
const work = mkdtempSync(join(root, 'sender-real-'));
const home = join(work, 'codex-home'); mkdirSync(home);
const env = { ...process.env, CODEX_HOME: home };
const server = spawn('codex', ['app-server', '--stdio'], { env, stdio: ['pipe', 'pipe', 'pipe'] });
let next = 0;
const pending = new Map();
const lines = createInterface({ input: server.stdout });
server.stderr.on('data', () => {});
lines.on('line', line => {
  let message; try { message = JSON.parse(line); } catch { return; }
  const item = pending.get(message.id); if (!item) return;
  clearTimeout(item.timer); pending.delete(message.id);
  message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result);
});
function rpc(method, params) {
  return new Promise((resolve, reject) => {
    const id = ++next;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('local protocol timeout')); }, 15000);
    pending.set(id, { resolve, reject, timer });
    server.stdin.write(JSON.stringify({ id, method, params }) + '\n');
  });
}
try {
  await rpc('initialize', { clientInfo: { name: 'sender_isolated_test', version: '1' }, capabilities: { experimentalApi: true } });
  server.stdin.write(JSON.stringify({ method: 'initialized' }) + '\n');
  const created = await rpc('thread/start', { cwd: work, ephemeral: false, historyMode: 'paginated' });
  const thread = created.thread.id;
  await rpc('thread/name/set', { threadId: thread, name: 'isolated-sender-test' });
  const message = 'ISOLATED QUEUE PROBE ONLY\nquotes " and trailing newline\n';
  const draft = join(work, 'draft.txt'); writeFileSync(draft, 'UNSENT USER DRAFT\n');
  let mutations = 0;
  let transport;
  const run = (file, args) => {
    if (file === 'herdr' && args[0] === 'session') return { status: 0, stdout: JSON.stringify({ sessions: [{ name: 'isolated', running: true, socket_path: '/isolated-only/herdr.sock' }] }) };
    if (file === 'herdr' && args[2] === 'agent' && args[3] === 'list') return { status: 0, stdout: JSON.stringify({ result: { agents: [{ name: 'FIXTURE', terminal_id: 'term_fixture', pane_id: 'pane_fixture', agent: 'codex', cwd: work, agent_session: { kind: 'id', value: thread, agent: 'codex' } }] } }) };
    if (file !== 'codex' || args[0] !== 'queue' || args[2] !== thread) throw new Error('refusing non-isolated transport');
    mutations++;
    transport = spawnSync(file, args, { env, cwd: work, encoding: 'utf8', timeout: 15000 });
    return transport;
  };
  const options = parse(['FIXTURE', message, '--session', 'isolated']);
  const deps = { run, receiptDir: join(work, 'receipts') };
  const first = send(options, deps), retry = send(options, deps);
  const queue = await rpc('thread/queue/list', { threadId: thread });
  const found = queue.data.find(q => q.id === first.queueId);
  const exact = found?.input?.some(i => i.type === 'text' && i.text === message) === true;
  const result = { work, isolatedThread: thread, first, retry, mutations, transport: { status: transport?.status, stdout: transport?.stdout, stderr: transport?.stderr },
    queueCount: queue.data.length, exactPayloadReadback: exact,
    draftUnchanged: readFileSync(draft, 'utf8') === 'UNSENT USER DRAFT\n',
    modelTurnStarted: false, liveHerdrUsed: false,
    limitations: 'Real Codex producer and queue consumer; Herdr identity and draft are fixtures. No processed/busy-TUI claim.' };
  writeFileSync(join(work, 'result.json'), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result, null, 2));
  if (first.state !== 'queued' || retry.exitCode !== 5 || mutations !== 1 || !exact || !result.draftUnchanged) process.exitCode = 1;
} finally {
  for (const item of pending.values()) clearTimeout(item.timer);
  server.stdin.end(); lines.close(); server.kill();
}
