import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { usageWindow } from '../scripts/usage-window.mjs';

const event = (type, payload, timestamp = '2026-09-06T00:00:00Z') => ({ type, payload, timestamp });
const usage = (id, input = 10, timestamp) => event('token_usage_record', { response_id: id,
  usage: { input_tokens: input, cached_input_tokens: 2, output_tokens: 3, reasoning_output_tokens: 1 } }, timestamp);
function fixture(t, events) {
  const dir = mkdtempSync(join(tmpdir(), 'usage-window-')); t.after(() => rmSync(dir, { recursive: true, force: true }));
  const path = join(dir, 'old-created.jsonl');
  writeFileSync(path, [event('session_meta', { id: 'old-owner' }, '2026-09-01T00:00:00Z'), ...events].map(JSON.stringify).join('\n'));
  return { start: '2026-09-06T07:00:00+07:00', end: '2026-09-07T07:00:00+07:00', sources: [{ path, id: 'old-owner', role: 'owner' }] };
}
test('counts active old threads, uses exclusive end, ignores cumulative mirrors/resets, deduplicates', async t => {
  const m = fixture(t, [usage('before', 100, '2026-09-05T23:59:59Z'), usage('a'), usage('a'),
    event('event_msg', { type: 'token_count', info: { total_token_usage: { input_tokens: 9000 } } }),
    event('event_msg', { type: 'token_count', info: { total_token_usage: { input_tokens: 0 } } }),
    usage('b', 20), usage('end', 500, '2026-09-07T00:00:00Z')]);
  const r = (await usageWindow(m)).sources[0];
  assert.equal(r.responses, 2); assert.equal(r.duplicate_records, 1);
  assert.equal(r.usage.input_tokens, 30); assert.equal(r.usage.uncached_input_tokens, 26);
  assert.equal(r.usage.output_tokens, 6); assert.equal(r.mean_input_tokens, 15);
});
test('models come from per-turn fields, not prose or rate labels; rate resets stay separate', async t => {
  const rate = reset => event('event_msg', { type: 'token_count', rate_limits: { limit_id: 'Spark', primary: { used_percent: 0, resets_at: reset, window_minutes: 10080 } } });
  const r = (await usageWindow(fixture(t, [usage('unknown'), event('turn_context', { model: 'Astra', effort: 'low' }),
    event('response_item', { text: 'Sol' }), usage('a'), rate(1), rate(2),
    event('turn_context', { model: 'Luna', effort: 'max' }), usage('b')]))).sources[0];
  assert.equal(r.models['["unknown","unknown"]'].responses, 1);
  assert.equal(r.models['["Astra","low"]'].responses, 1);
  assert.equal(r.models['["Luna","max"]'].responses, 1);
  assert.equal(Object.keys(r.rate_observations).length, 2);
});
test('conflicting duplicates fail without publishing a partial success', async t => {
  await assert.rejects(usageWindow(fixture(t, [usage('a'), usage('a', 20)])), /conflicting duplicate/);
});
test('invalid counters and source identities fail', async t => {
  await assert.rejects(usageWindow(fixture(t, [usage('a', 1)])), /invalid response usage/);
  const m = fixture(t, [usage('a')]); m.sources[0].id = 'other';
  await assert.rejects(usageWindow(m), /identity mismatch/);
});
test('no usage is unknown, not a zero-cost task', async t => {
  const r = (await usageWindow(fixture(t, []))).sources[0];
  assert.equal(r.status, 'no_response_usage_in_window'); assert.equal(r.mean_input_tokens, null);
});
test('ambiguous timezones and duplicate source selection fail', async t => {
  const m = fixture(t, [usage('a')]);
  await assert.rejects(usageWindow({ ...m, start: '2026-09-06' }), /timezone/);
  await assert.rejects(usageWindow({ ...m, sources: [m.sources[0], m.sources[0]] }), /duplicate source/);
});
test('cross-window duplicate does not become new usage; absent files fail', async t => {
  const m = fixture(t, [usage('a', 10, '2026-09-05T23:59:59Z'), usage('a')]);
  assert.equal((await usageWindow(m)).sources[0].responses, 0);
  m.sources[0].path += '.missing'; await assert.rejects(usageWindow(m), /ENOENT/);
});
test('CLI emits verifiable metadata, excludes message content and fails on malformed input', t => {
  const m = fixture(t, [event('response_item', { text: 'PRIVATE_SENTINEL' }), usage('a')]);
  const manifest = join(m.sources[0].path, '..', 'manifest.json');
  writeFileSync(manifest, JSON.stringify(m));
  const cli = fileURLToPath(new URL('../scripts/usage-window.mjs', import.meta.url));
  const result = spawnSync(process.execPath, [cli, manifest], { encoding: 'utf8' });
  assert.equal(result.status, 0); assert.doesNotMatch(result.stdout, /PRIVATE_SENTINEL/);
  assert.match(JSON.parse(result.stdout).sources[0].source_snapshot.sha256, /^[a-f0-9]{64}$/);
  writeFileSync(manifest, '{');
  const bad = spawnSync(process.execPath, [cli, manifest], { encoding: 'utf8' });
  assert.equal(bad.status, 1); assert.equal(bad.stdout, '');
});
test('malformed private records never leak their contents through parser errors', async t => {
  const m = fixture(t, []);
  writeFileSync(m.sources[0].path, 'PRIVATE_SENTINEL_NOT_JSON');
  await assert.rejects(usageWindow(m), error => /malformed JSON record/.test(error.message) && !error.message.includes('PRIVATE_SENTINEL'));
});
