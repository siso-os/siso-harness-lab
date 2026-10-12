import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { verifyProvenance } from '../scripts/verify-provenance.mjs';

function fixture(t, options = {}) {
  const root = mkdtempSync(join(tmpdir(), 'private-provenance-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const usage = { input_tokens: 100, cached_input_tokens: 60, output_tokens: 10 };
  const record = { type: 'token_usage_record', payload: { response_id: 'response-a', usage } };
  const events = [
    { type: 'session_meta', payload: { id: 'thread-a', cwd: options.cwd ?? root, source: 'exec', model_provider: 'openai' } },
    { type: 'turn_context', payload: { model: 'gpt-5.6-luna', effort: 'medium' } },
    { type: 'response_item', payload: { private_text: 'PRIVATE_CONTENT_MUST_NOT_RETURN' } },
    record, record,
  ];
  if (options.conflict) events.push({ ...record, payload: { ...record.payload, usage: { ...usage, input_tokens: 101 } } });
  const bytes = events.map(e => JSON.stringify(e)).join('\n') + '\n', path = join(root, 'source.jsonl');
  writeFileSync(path, bytes);
  const receipt = { attempts: [{ id: 'thread-a', rollout_path: path,
    source: 'exec', model_provider: 'openai',
    rollout_sha256: createHash('sha256').update(bytes).digest('hex'), usage,
    observed_models: ['gpt-5.6-luna'], observed_efforts: ['medium'] }] };
  return { root, path, receipt };
}
test('exact local source verifies deduplicated usage without returning private content', async t => {
  const { root, receipt } = fixture(t), result = await verifyProvenance(receipt, root);
  assert.equal(result.status, 'verified'); assert.equal(result.attempts[0].response_ids, 1);
  assert.equal(JSON.stringify(result).includes('PRIVATE_CONTENT_MUST_NOT_RETURN'), false);
});
test('missing private source is unavailable, not a passing zero-cost record', async t => {
  const { root, path, receipt } = fixture(t); rmSync(path);
  assert.equal((await verifyProvenance(receipt, root)).status, 'unavailable');
});
test('a directory locator is unavailable without starting a source stream', async t => {
  const { root, receipt } = fixture(t); receipt.attempts[0].rollout_path = root;
  assert.equal((await verifyProvenance(receipt, root)).status, 'unavailable');
});
test('changed or conflicting usage fails verification', async t => {
  const a = fixture(t); a.receipt.attempts[0].usage.input_tokens = 90;
  assert.equal((await verifyProvenance(a.receipt, a.root)).status, 'mismatch');
  const b = fixture(t, { conflict: true });
  assert.equal((await verifyProvenance(b.receipt, b.root)).status, 'mismatch');
});
test('a source belonging to another project is rejected before processing its content', async t => {
  const { root, receipt } = fixture(t, { cwd: '/another-project' });
  const result = await verifyProvenance(receipt, root);
  assert.equal(result.attempts[0].status, 'scope_mismatch');
  assert.equal(result.attempts[0].response_ids, undefined);
});
test('empty receipt cannot claim verification', async () => {
  await assert.rejects(verifyProvenance({ attempts: [] }, '/tmp'), /missing attempts/);
});
test('launch-route metadata and required usage fields cannot be omitted or conflated', async t => {
  const a = fixture(t); a.receipt.attempts[0].source = 'cli';
  assert.equal((await verifyProvenance(a.receipt, a.root)).status, 'mismatch');
  const b = fixture(t); delete b.receipt.attempts[0].usage.output_tokens;
  assert.equal((await verifyProvenance(b.receipt, b.root)).attempts[0].status, 'invalid_receipt');
});
