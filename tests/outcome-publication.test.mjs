import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { recordResponse, claimResponse } from '../scripts/grade-outcome.mjs';

const repoRoot = fileURLToPath(new URL('..', import.meta.url));
const script = join(repoRoot, 'scripts', 'grade-outcome.mjs');

function disposableRoot() {
  const root = mkdtempSync(join(tmpdir(), 'outcome-publication-'));
  mkdirSync(join(root, 'experiments'));
  mkdirSync(join(root, 'reports', '2026-09-08-outcome-quality'), { recursive: true });
  cpSync(join(repoRoot, 'experiments', 'owner-continuation-rubric.json'), join(root, 'experiments', 'owner-continuation-rubric.json'));
  cpSync(join(repoRoot, 'experiments', 'owner-continuation-cases.json'), join(root, 'experiments', 'owner-continuation-cases.json'));
  const casePath = 'experiments/owner-continuation-cases.json';
  writeFileSync(join(root, 'reports', '2026-09-08-outcome-quality', 'frozen-inputs.json'), JSON.stringify({
    experiment: 'owner-continuation-v1', inputs: { [casePath]: createHash('sha256').update(readFileSync(join(root, casePath))).digest('hex') }
  }));
  return root;
}

function response() {
  const actions = [
    'explain_keep_existing_pause_new_dispatch', 'checkpoint_and_pause_existing',
    'continue_local_preparation_no_send', 'report_missing_input_once',
    'perform_lookup_inline', 'plan_new_project_keep_unrelated_work'
  ];
  const ids = ['clarification', 'explicit-hold', 'external-boundary', 'missing-packet', 'small-lookup', 'new-plan-only'];
  return { experiment: 'owner-continuation-v1', responses: ids.map((id, i) => ({ id, action: actions[i], explanation: `Decision for ${id}.` })) };
}

async function withRoot(fn) {
  const root = disposableRoot();
  try { return await fn(root); } finally { rmSync(root, { recursive: true, force: true }); }
}

test('publishes and reads back the first response, including a wrong decision', () => withRoot(root => {
  const value = response();
  value.responses[0].action = 'perform_lookup_inline';
  const destination = recordResponse(root, 'baseline', value);
  assert.deepEqual(JSON.parse(readFileSync(destination, 'utf8')), value);
}));

test('second writer refuses and preserves the exact first bytes', () => withRoot(root => {
  const destination = recordResponse(root, 'candidate', response());
  const firstBytes = readFileSync(destination);
  const changed = response(); changed.responses[0].explanation = 'A different explanation.';
  assert.throws(() => recordResponse(root, 'candidate', changed), /publication conflict/);
  assert.deepEqual(readFileSync(destination), firstBytes);
}));

test('reservation prevents a second coordinator dispatch, including the same owner retry', () => withRoot(root => {
  assert.equal(claimResponse(root, 'baseline', 'owner-a').dispatch_allowed, true);
  for (const owner of ['owner-a', 'owner-b']) assert.throws(() => claimResponse(root, 'baseline', owner), /already claimed/);
  recordResponse(root, 'candidate', response());
  assert.throws(() => claimResponse(root, 'candidate', 'owner-b'), /already recorded/);
}));

test('changed inputs do not acquire a claim', () => withRoot(root => {
  const path = join(root, 'experiments', 'owner-continuation-cases.json');
  writeFileSync(path, readFileSync(path, 'utf8') + '\n');
  assert.throws(() => claimResponse(root, 'baseline', 'owner-a'), /changed frozen input/);
  assert.equal(existsSync(join(root, 'reports', '2026-09-08-outcome-quality', 'baseline-claim.json')), false);
}));

test('simultaneous writers publish at most one response without overwriting', async () => withRoot(async root => {
  const code = `import { recordResponse } from ${JSON.stringify(script)}; recordResponse(process.argv[1], 'baseline', JSON.parse(process.argv[2]));`;
  const payloads = ['first', 'second'].map(label => {
    const value = response(); value.responses[0].explanation = label; return value;
  });
  const run = value => new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--input-type=module', '-e', code, root, JSON.stringify(value)], { stdio: 'ignore' });
    child.on('error', reject);
    child.on('close', status => resolve(status));
  });
  const statuses = await Promise.all(payloads.map(run));
  assert.equal(statuses.filter(status => status === 0).length, 1);
  const output = join(root, 'reports', '2026-09-08-outcome-quality', 'baseline-response.json');
  assert.deepEqual(JSON.parse(readFileSync(output)), payloads[statuses.indexOf(0)]);
}));

test('malformed input leaves no output and invalid arm or symlink cannot escape publication', () => withRoot(root => {
  const malformed = [
    { experiment: 'owner-continuation-v1', responses: [] },
    (() => { const value = response(); value.responses[0].id = 'unknown'; return value; })(),
    (() => { const value = response(); value.responses[1].id = value.responses[0].id; return value; })(),
    (() => { const value = response(); value.responses[0].action = 'unknown'; return value; })(),
    (() => { const value = response(); value.responses[0].explanation = ''; return value; })(),
    (() => { const value = response(); value.responses[0].explanation = 'word '.repeat(31); return value; })(),
    (() => { const value = response(); value.experiment = 'other'; return value; })()
  ];
  for (const value of malformed) assert.throws(() => recordResponse(root, 'baseline', value), /invalid response/);
  const destination = join(root, 'reports', '2026-09-08-outcome-quality', 'candidate-response.json');
  const baseline = join(root, 'reports', '2026-09-08-outcome-quality', 'baseline-response.json');
  assert.equal(existsSync(destination), false);
  assert.equal(existsSync(baseline), false);
  assert.throws(() => recordResponse(root, '../outside', response()), /invalid response: arm/);
  writeFileSync(destination, '{malformed existing bytes');
  assert.throws(() => recordResponse(root, 'candidate', response()), /publication conflict/);
  assert.equal(readFileSync(destination, 'utf8'), '{malformed existing bytes');
  rmSync(destination);
  const target = join(root, 'target.txt'); writeFileSync(target, 'keep'); symlinkSync(target, destination);
  assert.throws(() => recordResponse(root, 'candidate', response()), /publication conflict/);
  assert.equal(readFileSync(target, 'utf8'), 'keep');
}));
