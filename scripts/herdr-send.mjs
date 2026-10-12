#!/usr/bin/env node
// One canonical sender for both historical herdr-send command-line contracts.
// No terminal reads/writes/keys. Codex queue acknowledgement is NOT processing.
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { constants, closeSync, fsyncSync, ftruncateSync, mkdirSync, openSync, readFileSync, realpathSync, writeFileSync, writeSync } from 'node:fs';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const UUID = '[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}';
const validUuid = new RegExp(`^${UUID}$`, 'i');
const hash = text => createHash('sha256').update(text).digest('hex');
const fail = (message, exitCode = 64) => Object.assign(new Error(message), { exitCode });

export function parse(argv) {
  const out = { session: 'default' };
  const flags = new Set(['dry-run', 'force', 'help']);
  const values = new Set(['to', 'text', 'file', 'expect-identity', 'audit', 'fingerprint', 'retries', 'prefix', 'session', 'status']);
  const positional = [];
  if (argv[0] && !argv[0].startsWith('--')) {
    if (argv.length < 2) throw fail('positional form requires NAME MESSAGE');
    [out.to, out.text] = argv.slice(0, 2);
    argv = argv.slice(2);
  }
  const seen = new Set();
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!arg.startsWith('--')) { positional.push(arg); continue; }
    const name = arg.slice(2);
    if (seen.has(name) || (['to', 'text', 'file'].includes(name) && out.to && out.text !== undefined)) throw fail(`duplicate or mixed --${name}`);
    seen.add(name);
    if (flags.has(name)) out[name] = true;
    else if (values.has(name)) {
      if (argv[i + 1] === undefined || (!['text', 'prefix'].includes(name) && argv[i + 1].startsWith('--'))) throw fail(`missing --${name} value`);
      out[name] = argv[++i];
    } else throw fail(`unknown option ${arg}`);
  }
  if (positional.length) {
    if (positional.length !== 2 || out.to || out.text !== undefined || out.file) throw fail('use NAME MESSAGE or --to with --text/--file');
    [out.to, out.text] = positional;
  }
  if (out.help) return out;
  if (out.status) {
    if (out.to || out.text !== undefined || out.file) throw fail('--status is read-only; do not combine with a send');
    return out;
  }
  if (!out.to || !out.session || (out.text === undefined) === (out.file === undefined)) throw fail('require recipient and exactly one message source');
  if (out.retries !== undefined && !/^\d+$/.test(out.retries)) throw fail('--retries must be a nonnegative integer');
  if (out['expect-identity'] !== undefined) {
    try { out.expect = new RegExp(out['expect-identity'], 'i'); } catch { throw fail('invalid identity expression'); }
  }
  return out;
}

export function command(file, args) {
  return spawnSync(file, args, { encoding: 'utf8', timeout: 20000, maxBuffer: 2 * 1024 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'] });
}

function jsonCommand(run, args) {
  const r = run('herdr', args);
  if (r.error || r.status !== 0) throw fail('Herdr transport unavailable; nothing submitted', 69);
  let d;
  try { d = JSON.parse(r.stdout); } catch { throw fail('invalid Herdr response; nothing submitted', 69); }
  if (d.error) throw fail('Herdr rejected request; nothing submitted', 69);
  return d;
}

function recipient(run, options) {
  const sessions = jsonCommand(run, ['session', 'list', '--json']).sessions;
  if (!Array.isArray(sessions)) throw fail('invalid server inventory', 69);
  const servers = sessions.filter(s => s.name === options.session && s.running === true);
  if (servers.length !== 1 || typeof servers[0].socket_path !== 'string') throw fail('requested Herdr server unavailable or ambiguous', 69);
  const agents = jsonCommand(run, ['--session', options.session, 'agent', 'list']).result?.agents;
  if (!Array.isArray(agents)) throw fail('invalid agent inventory', 69);
  // herdr agent list sets neither name nor label: the tab title (terminal_title_stripped) is the name Shaan and agents use,
  // so names match case-insensitively there; ids match exactly. (2 Oct 2026: every name was refused as 'recipient not found'.)
  const want = String(options.to).toLowerCase();
  const matches = agents.filter(a => [a.name, a.label, a.terminal_title_stripped].some(n => typeof n === 'string' && n.trim().toLowerCase() === want)
    || [a.terminal_id, a.pane_id, a.agent_session?.value].includes(options.to));
  if (matches.length !== 1) throw fail(matches.length ? 'ambiguous recipient; use exact terminal/session ID' : 'recipient not found on selected server', 4);
  const a = matches[0], s = a.agent_session;
  if (typeof a.terminal_id !== 'string' || s?.kind !== 'id' || !validUuid.test(s.value ?? '')) throw fail('recipient lacks stable session identity', 3);
  if (a.agent !== s.agent) throw fail('conflicting agent/session identity', 3);
  const identity = { server: options.session, socket: servers[0].socket_path,
    terminal: a.terminal_id, thread: s.value, agent: s.agent, cwd: a.cwd ?? null };
  // Legacy expression is applied to identity metadata, NEVER screen text.
  if (options.expect && !options.expect.test(JSON.stringify({ ...identity, name: a.name, label: a.label }))) throw fail('identity expression does not match recipient metadata', 3);
  return identity;
}

function readReceipt(path) {
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const r = JSON.parse(readFileSync(fd, 'utf8'));
    if (r.version !== 1 || !['attempting', 'queued', 'unconfirmed'].includes(r.state)
      || !validUuid.test(r.identity?.thread ?? '') || !/^[a-f0-9]{64}$/.test(r.payloadHash ?? '')
      || (r.state === 'queued' && !validUuid.test(r.queueId ?? ''))) throw fail('invalid sender receipt', 70);
    return r;
  } finally { closeSync(fd); }
}

function save(fd, receipt) {
  // Same open inode, no path re-open after reservation. Failed/truncated writes
  // leave an unreadable receipt that refuses retries, not a fresh send opportunity.
  const bytes = Buffer.from(JSON.stringify(receipt) + '\n');
  ftruncateSync(fd, 0);
  let at = 0;
  while (at < bytes.length) at += writeSync(fd, bytes, at, bytes.length - at, at);
  fsyncSync(fd);
}

export function send(options, { run = command, receiptDir = join(homedir(), '.claude', 'state', 'herdr-send'), now = () => new Date().toISOString() } = {}) {
  if (options.status) {
    const receipt = readReceipt(resolve(options.status));
    return { ...receipt, receiptPath: resolve(options.status), exitCode: receipt.state === 'queued' ? 0 : 70, processed: false };
  }
  const message = (options.prefix ?? '') + (options.file ? readFileSync(options.file, 'utf8') : options.text);
  if (!message || Buffer.byteLength(message) > 128 * 1024 || message.includes('\0')) throw fail('message must be nonempty, NUL-free and at most 128 KiB');
  const identity = recipient(run, options);
  if (identity.agent !== 'codex') return { state: 'unsupported', exitCode: 69, identity,
    reason: 'No verified draft-preserving submission transport for this agent; no text or keys sent. For a Claude agent use a0-tell NAME "msg"', processed: false };
  const payloadHash = hash(message);
  const key = hash(JSON.stringify([identity.server, identity.socket, identity.thread, options.fingerprint ?? payloadHash]));
  const receiptPath = join(receiptDir, `${key}.json`);
  const initial = { version: 1, state: 'attempting', identity, payloadHash, fingerprint: options.fingerprint ?? null,
    bytes: Buffer.byteLength(message), createdAt: now(), processed: false };
  if (options['dry-run']) return { ...initial, state: 'dry-run', receiptPath, exitCode: 0 };
  mkdirSync(receiptDir, { recursive: true, mode: 0o700 });
  let fd;
  try { fd = openSync(receiptPath, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | constants.O_NOFOLLOW, 0o600); }
  catch (error) {
    if (error.code !== 'EEXIST') throw error;
    const old = readReceipt(receiptPath);
    if (old.payloadHash !== payloadHash || JSON.stringify(old.identity) !== JSON.stringify(identity)) throw fail('fingerprint collision or changed identity; nothing resent', 70);
    return { ...old, duplicate: true, receiptPath, exitCode: old.state === 'queued' ? 5 : 70, processed: false };
  }
  let receipt = initial;
  try {
    save(fd, initial);
    if (options.audit && options.fingerprint) {
      let previous = '';
      try { previous = readFileSync(options.audit, 'utf8'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
      for (const line of previous.split('\n').filter(Boolean)) {
        let row; try { row = JSON.parse(line); } catch { throw fail('malformed legacy audit; nothing submitted', 70); }
        if (row.fingerprint === options.fingerprint && !['DRY_RUN', 'dry-run'].includes(row.outcome ?? row.state)) {
          throw fail('Existing audit fingerprint; legacy delivery is not processing proof and will not be resent', 70);
        }
      }
    }
    const current = recipient(run, { ...options, to: identity.terminal });
    if (JSON.stringify(current) !== JSON.stringify(identity)) throw fail('recipient changed before submission', 3);
    // Unlike PTY insertion this does not read, append to or submit a user's draft.
    // The durable attempting receipt prevents a second send after a timeout/crash.
    const result = run('codex', ['queue', '--thread', identity.thread, '--message', message]);
    const matched = new RegExp(`^Queued message (${UUID}) for thread (${UUID})\\.\\s*$`, 'i').exec(result.stdout ?? '');
    const accepted = !result.error && result.status === 0 && matched?.[2] === identity.thread;
    receipt = { ...initial, state: accepted ? 'queued' : 'unconfirmed', updatedAt: now(),
      ...(accepted ? { queueId: matched[1] } : { reason: 'No exact queue acknowledgement; do not retry blindly' }) };
  } catch (error) {
    receipt = { ...initial, state: 'unconfirmed', updatedAt: now(), reason: error.exitCode ? error.message : 'Submission interrupted; do not retry blindly' };
  }
  try { save(fd, receipt); } finally { closeSync(fd); }
  const output = { ...receipt, receiptPath, exitCode: receipt.state === 'queued' ? 0 : 70 };
  if (options.audit) {
    // Audit is supplementary; the exclusive receipt above is retry authority.
    const audit = openSync(resolve(options.audit), constants.O_WRONLY | constants.O_APPEND | constants.O_CREAT | constants.O_NOFOLLOW, 0o600);
    try { writeFileSync(audit, JSON.stringify(output) + '\n'); fsyncSync(audit); } finally { closeSync(audit); }
  }
  return output;
}

export function main(argv = process.argv.slice(2)) {
  try {
    const options = parse(argv);
    if (options.help) {
      console.log('herdr-send NAME MESSAGE | --to TARGET (--text TEXT | --file PATH) [--session default] [--expect-identity REGEX] [--fingerprint ID] [--audit PATH] [--prefix TEXT] [--dry-run] [--force] [--retries N]\nherdr-send --status RECEIPT\n0=queued (NOT processed), 5=duplicate suppressed, 3/4=identity/target refused, 69=unsupported/unavailable, 70=unconfirmed, 64=usage. No terminal keys; --retries never repeats submission. --force cannot bypass stable identity.');
      return 0;
    }
    const result = send(options);
    console.log(JSON.stringify(result));
    return result.exitCode;
  } catch (error) {
    // Do not echo raw provider/CLI error output that may contain a message/secret.
    console.error(JSON.stringify({ state: 'refused', reason: error.exitCode ? error.message : 'local receipt/input failure; inspect paths and retry status, not submission', processed: false }));
    return error.exitCode ?? 70;
  }
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) process.exitCode = main();
