#!/usr/bin/env node
// Idle chats compact themselves, on stock T3 Code (Alpha) 0.0.x (Cam's Mac). Same rule as SISO Code's
// apps/server/src/siso/idleCompact.ts: every sweep, a chat whose latest turn ended over IDLE_MIN ago, with nothing
// running, pending or waiting on a person, and a last context of at least MIN_CONTEXT tokens gets a native `/compact`
// turn (sent with t3ctl); at most MAX_PER_SWEEP per sweep; once per idle spell; never "agent zero", never a pinned or
// settled chat. Chats idle over MAX_IDLE_H are left alone: compacting one re-writes its whole context at the cold-cache
// price, which only pays if someone comes back, and nobody comes back to a lane left for a day.
// Why: after an hour the prompt cache is gone, so the next message re-writes the whole context at the 1-hour write
// price; compacting first shrinks what is re-written.
// Reads T3's state.sqlite read-only (sqlite3 CLI, file:...?mode=ro). Prints counts and ids only, never chat text.
// Usage: t3-idle-compact.mjs [--dry-run] [--state <state.sqlite>] [--min-context 100000] [--idle-min 60]
//        [--max 2] [--max-idle-hours 24] [--t3ctl <path>] [--spell-file <json>] [--now <iso>]
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';

const opt = {};
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i++) {
  if (!argv[i].startsWith('--')) continue;
  const k = argv[i].slice(2);
  opt[k] = argv[i + 1] === undefined || argv[i + 1].startsWith('--') ? true : argv[++i];
}
const home = homedir();
const DB = opt.state || join(home, '.t3/userdata/state.sqlite');
const MIN_CONTEXT = Number(opt['min-context'] ?? 100_000);
const IDLE_MIN = Number(opt['idle-min'] ?? 60);
const MAX_IDLE_MIN = Number(opt['max-idle-hours'] ?? 24) * 60;
const MAX_PER_SWEEP = Number(opt.max ?? 2);
const T3CTL = opt.t3ctl || 't3ctl';
const SPELL_FILE = opt['spell-file'] || join(home, '.local/state/t3-idle-compact.json');
const DRY = Boolean(opt['dry-run']);
const NOW = opt.now ? Date.parse(opt.now) : Date.now();
/** The compact turn we send is requested within seconds; a later turn on the chat is a person, and a new spell. */
const COMPACT_TURN_WINDOW_MS = 120_000;
const TERMINAL = new Set(['completed', 'error', 'interrupted']);

const uri = 'file:' + DB.replace(/%/g, '%25').replace(/\?/g, '%3f').replace(/#/g, '%23') + '?mode=ro';
const query = sql => {
  const out = execFileSync('sqlite3', ['-json', uri, sql], { encoding: 'utf8', maxBuffer: 64 << 20 }).trim();
  return out ? JSON.parse(out) : [];
};

// One row per live chat: its latest turn, any unfinished turn, session status, and last context size.
// Context is the newest context-window.updated; a context-compaction after it means the chat is at afterTokens.
const rows = query(`
  SELECT t.thread_id AS id, t.title AS title, t.pinned_at AS pinned,
    (t.settled_override = 'settled' OR (t.settled_at IS NOT NULL AND COALESCE(t.settled_override, '') <> 'unsettled')) AS settled,
    t.pending_approval_count AS approvals, t.pending_user_input_count AS inputs,
    (SELECT s.status FROM projection_thread_sessions s WHERE s.thread_id = t.thread_id) AS session,
    (SELECT u.requested_at FROM projection_turns u WHERE u.thread_id = t.thread_id ORDER BY u.requested_at DESC, u.row_id DESC LIMIT 1) AS last_requested,
    (SELECT u.state FROM projection_turns u WHERE u.thread_id = t.thread_id ORDER BY u.requested_at DESC, u.row_id DESC LIMIT 1) AS last_state,
    (SELECT u.completed_at FROM projection_turns u WHERE u.thread_id = t.thread_id ORDER BY u.requested_at DESC, u.row_id DESC LIMIT 1) AS last_completed,
    (SELECT count(*) FROM projection_turns u WHERE u.thread_id = t.thread_id AND (u.completed_at IS NULL OR u.state NOT IN ('completed','error','interrupted'))) AS unfinished,
    (SELECT json_extract(a.payload_json, '$.usedTokens') FROM projection_thread_activities a
       WHERE a.thread_id = t.thread_id AND a.kind = 'context-window.updated' AND json_extract(a.payload_json, '$.usedTokens') IS NOT NULL
       ORDER BY a.created_at DESC, a.rowid DESC LIMIT 1) AS used,
    (SELECT a.created_at FROM projection_thread_activities a
       WHERE a.thread_id = t.thread_id AND a.kind = 'context-window.updated' AND json_extract(a.payload_json, '$.usedTokens') IS NOT NULL
       ORDER BY a.created_at DESC, a.rowid DESC LIMIT 1) AS used_at,
    (SELECT json_extract(a.payload_json, '$.afterTokens') FROM projection_thread_activities a
       WHERE a.thread_id = t.thread_id AND a.kind = 'context-compaction'
       ORDER BY a.created_at DESC, a.rowid DESC LIMIT 1) AS after_compact,
    (SELECT a.created_at FROM projection_thread_activities a
       WHERE a.thread_id = t.thread_id AND a.kind = 'context-compaction'
       ORDER BY a.created_at DESC, a.rowid DESC LIMIT 1) AS compact_at
  FROM projection_threads t
  WHERE t.deleted_at IS NULL AND t.archived_at IS NULL`);

let spells = {};
try { spells = JSON.parse(readFileSync(SPELL_FILE, 'utf8')); } catch { /* none yet */ }

const verdicts = rows.map(r => {
  const v = { id: r.id, idleMin: null, contextK: null, picked: false, reason: '' };
  const used = r.after_compact != null && r.compact_at && (!r.used_at || r.compact_at > r.used_at) ? r.after_compact : r.used;
  v.contextK = used == null ? null : Math.round(used / 1000);
  if (r.last_completed) v.idleMin = Math.round((NOW - Date.parse(r.last_completed)) / 60_000);
  if (/agent zero/i.test(r.title || '')) v.reason = 'agent zero';
  else if (r.pinned) v.reason = 'pinned';
  else if (r.settled) v.reason = 'settled';
  else if (!r.last_requested) v.reason = 'no turns';
  else if (r.unfinished > 0 || !TERMINAL.has(r.last_state) || !r.last_completed) v.reason = 'running or queued';
  else if (['running', 'starting'].includes(r.session)) v.reason = 'running or queued';
  else if (r.approvals > 0 || r.inputs > 0) v.reason = 'waiting on a person';
  else if (v.idleMin < IDLE_MIN) v.reason = `recent (${v.idleMin} min)`;
  else if (v.idleMin > MAX_IDLE_MIN) v.reason = `idle too long (${Math.round(v.idleMin / 60)} h)`;
  else if (used == null) v.reason = 'no context reading';
  else if (used < MIN_CONTEXT) v.reason = `small (${v.contextK}k)`;
  else if (spells[r.id] && Date.parse(r.last_requested) <= Date.parse(spells[r.id].sentAt) + COMPACT_TURN_WINDOW_MS)
    v.reason = 'already compacted this spell';
  else { v.picked = true; v.used = used; v.reason = 'idle and big'; }
  return v;
});

const candidates = verdicts.filter(v => v.picked).sort((a, b) => b.used - a.used);
const chosen = candidates.slice(0, MAX_PER_SWEEP);
for (const v of candidates.slice(MAX_PER_SWEEP)) { v.picked = false; v.reason = `over the ${MAX_PER_SWEEP} per sweep`; }

const fmt = v => `${String(v.id).slice(0, 8)}  idle ${v.idleMin ?? '-'} min  context ${v.contextK ?? '-'}k  ${v.picked ? 'COMPACT' : 'skip: ' + v.reason}`;
console.log(`t3-idle-compact ${DRY ? '(dry run) ' : ''}${new Date(NOW).toISOString()}: ${rows.length} chats, ${chosen.length} to compact (idle ${IDLE_MIN} min to ${MAX_IDLE_MIN / 60} h, context >= ${MIN_CONTEXT / 1000}k, max ${MAX_PER_SWEEP})`);
const show = verdicts.filter(v => v.picked || v.reason.startsWith('over the') || opt.all);
for (const v of show) console.log(fmt(v));
if (DRY || opt.all) {
  const tally = {};
  for (const v of verdicts) if (!v.picked) tally[v.reason.replace(/ \(.*\)$/, '')] = (tally[v.reason.replace(/ \(.*\)$/, '')] || 0) + 1;
  console.log('skipped: ' + (Object.entries(tally).map(([k, n]) => `${n} ${k}`).join(', ') || 'none'));
}

if (!DRY) {
  for (const v of chosen) {
    try {
      execFileSync(T3CTL, ['send', v.id, '--prompt', '/compact'], { stdio: ['ignore', 'pipe', 'pipe'], timeout: 60_000 });
      spells[v.id] = { sentAt: new Date(opt.now ? NOW : Date.now()).toISOString(), contextK: v.contextK };
      console.log(`sent /compact to ${String(v.id).slice(0, 8)}`);
    } catch (e) {
      console.log(`could not send to ${String(v.id).slice(0, 8)}: exit ${e.status ?? '?'}`);
    }
  }
  if (chosen.length) {
    mkdirSync(dirname(SPELL_FILE), { recursive: true });
    const tmp = SPELL_FILE + '.tmp';
    writeFileSync(tmp, JSON.stringify(spells, null, 1));
    renameSync(tmp, SPELL_FILE);
  }
}
