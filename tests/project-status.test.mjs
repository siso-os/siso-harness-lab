import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, copyFileSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import { projectStatus, serve } from '../scripts/project-status.mjs';

const source = fileURLToPath(new URL('..', import.meta.url));
const trial = 'reports/2026-09-08-outcome-quality';
function fixture(t, responses = false) {
  const root = mkdtempSync(join(tmpdir(), 'project-status-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const files = ['.agents/repos.json', 'BACKLOG.md', 'experiments/output-retrieval.json',
    'scripts/efficiency-loop.mjs', 'scripts/output-policies.mjs', 'tests/efficiency-loop.test.mjs',
    'experiments/owner-continuation-cases.json', 'experiments/owner-continuation-rubric.json',
    ...['frozen-inputs.json', 'baseline-brief.md', 'candidate-brief.md'].map(f => `${trial}/${f}`),
    'site/index.html', 'site/app.js', 'site/style.css'];
  if (responses) files.push(...['baseline-response.json', 'candidate-response.json', 'review.json', 'provenance.json'].map(f => `${trial}/${f}`));
  for (const file of files) {
    mkdirSync(dirname(join(root, file)), { recursive: true });
    copyFileSync(join(source, file), join(root, file));
  }
  writeFileSync(join(root, 'BACKLOG.md'), '# Backlog\n## Open\n| 42 | Finish a real task | report | check | S | owner gate |\n## Done\n');
  return root;
}

test('cold status identifies pending inputs and uses the existing backlog', t => {
  const result = projectStatus(fixture(t));
  assert.equal(result.outcome.status, 'pending_responses');
  assert.equal(result.next_work.id, '42');
  assert.equal(result.diagnostic.completed_cycles, 0);
  assert.ok(result.claims_not_made.includes('tenfold_improvement'));
});
test('live cold pickup follows the budget reset without erasing the conditional fixture task', () => {
  assert.equal(projectStatus(source).next_work.id, '26');
  const backlog = readFileSync(join(source, 'BACKLOG.md'), 'utf8');
  assert.match(backlog, /\| 25 \|/);
  assert.match(readFileSync(join(source, '.agents/PAGE.md'), 'utf8'), /Current order: \*\*EFFICIENCY-OWNER/);
  assert.match(readFileSync(join(source, '.agents/HANDOFF.md'), 'utf8'), /## ACTIVE — EFFICIENCY-OWNER/);
});
test('reconciled collision remains qualified, not a clean experimental win', t => {
  const result = projectStatus(fixture(t, true));
  assert.equal(result.outcome.status, 'qualified_review');
  assert.equal(result.outcome.review.verdict, 'no_promotion');
  assert.equal(result.outcome.results.baseline.correct, 6);
});
test('changed responses invalidate a prior owner review even when scores pass', t => {
  const root = fixture(t, true), path = join(root, trial, 'candidate-response.json');
  const response = JSON.parse(readFileSync(path)); response.responses[0].explanation = 'Still preserve authorized work.';
  writeFileSync(path, JSON.stringify(response));
  const result = projectStatus(root);
  assert.equal(result.outcome.status, 'blocked_evidence');
  assert.equal(result.outcome.review, null);
});
test('changed frozen inputs are blocked', t => {
  const root = fixture(t), path = join(root, 'experiments/owner-continuation-cases.json');
  writeFileSync(path, readFileSync(path, 'utf8') + '\n');
  assert.equal(projectStatus(root).outcome.status, 'blocked_evidence');
});
test('implementation badge requires current source hashes as well as a passing check receipt', t => {
  const root = fixture(t), relativePath = 'scripts/output-policies.mjs';
  writeFileSync(join(root, trial, 'implementation.json'), JSON.stringify({
    source_hashes: { [relativePath]: createHash('sha256').update(readFileSync(join(root, relativePath))).digest('hex') },
    checks: { npm_test_exit_code: 0, summary: 'fixture checks passed' }
  }));
  assert.equal(projectStatus(root).implementation.status, 'verified_source_and_checks');
  writeFileSync(join(root, relativePath), readFileSync(join(root, relativePath), 'utf8') + '\n');
  assert.equal(projectStatus(root).implementation.status, 'stale_or_unverified');
});
test('the local front page and API are read-only and cannot expose arbitrary paths', { timeout: 10000 }, async t => {
  const server = serve(0, fixture(t, true)); t.after(() => new Promise(resolve => server.close(resolve)));
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const status = await fetch(`${base}/api/status`);
  assert.equal(status.headers.get('cache-control'), 'no-store');
  assert.equal((await status.json()).outcome.status, 'qualified_review');
  assert.match(await (await fetch(base)).text(), /Make the next/);
  assert.equal((await fetch(`${base}/api/status`, { method: 'POST' })).status, 405);
  assert.equal((await fetch(`${base}/.agents/repos.json`)).status, 404);
  assert.equal((await fetch(`${base}/%2e%2e/package.json`)).status, 404);
});
test('corrupt evidence is reported as blocked instead of a successful empty result', { timeout: 10000 }, async t => {
  const root = fixture(t); writeFileSync(join(root, '.agents/repos.json'), 'broken');
  const server = serve(0, root); t.after(() => new Promise(resolve => server.close(resolve)));
  await once(server, 'listening');
  const response = await fetch(`http://127.0.0.1:${server.address().port}/api/status`);
  assert.equal(response.status, 500);
  assert.equal((await response.json()).status, 'blocked_evidence');
});
