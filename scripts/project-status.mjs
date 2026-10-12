import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { dirname, join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { next } from './efficiency-loop.mjs';
import { grade } from './grade-outcome.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const read = path => JSON.parse(readFileSync(path, 'utf8'));

export function projectStatus(projectRoot = root) {
  const metadata = read(join(projectRoot, '.agents/repos.json'));
  const trialPath = 'reports/2026-09-08-outcome-quality';
  const trialRoot = join(projectRoot, trialPath);
  const outcome = { status: 'not_configured', results: {}, review: null, errors: [] };
  const frozenPath = join(trialRoot, 'frozen-inputs.json');
  if (existsSync(frozenPath)) {
    outcome.status = 'pending_responses';
    const frozen = read(frozenPath);
    for (const [path, hash] of Object.entries(frozen.inputs)) {
      const full = resolve(projectRoot, path), local = relative(resolve(projectRoot), full);
      if (local.startsWith('..') || resolve(path) === path || !existsSync(full) ||
          digest(readFileSync(full)) !== hash) outcome.errors.push(`Frozen input changed or absent: ${path}`);
    }
    const rubric = read(join(projectRoot, 'experiments/owner-continuation-rubric.json'));
    const hashes = {};
    for (const arm of ['baseline', 'candidate']) {
      const path = join(trialRoot, `${arm}-response.json`);
      if (!existsSync(path)) continue;
      try {
        const bytes = readFileSync(path); hashes[arm] = digest(bytes);
        outcome.results[arm] = grade(JSON.parse(bytes), rubric);
      } catch { outcome.errors.push(`Unreadable ${arm} response`); }
    }
    if (Object.keys(outcome.results).length === 2) outcome.status = 'requires_owner_review';
    const reviewPath = join(trialRoot, 'review.json');
    if (existsSync(reviewPath)) {
      const review = read(reviewPath);
      const provenancePath = join(trialRoot, 'provenance.json');
      if (review.experiment !== rubric.experiment ||
          review.frozen_inputs_hash !== digest(readFileSync(frozenPath)) ||
          !existsSync(provenancePath) || review.provenance_sha256 !== digest(readFileSync(provenancePath)) ||
          !['baseline', 'candidate'].every(arm => hashes[arm] && review.response_hashes?.[arm] === hashes[arm])) {
        outcome.errors.push('Owner review is stale or does not match both responses');
      } else {
        outcome.review = { verdict: review.verdict, protocol_status: review.protocol_status,
          limits: review.limits, next_action: review.next_action };
        outcome.status = review.protocol_status === 'duplicate_execution_collision' ? 'qualified_review' : 'reviewed';
      }
    }
    if (outcome.errors.length) outcome.status = 'blocked_evidence';
  }
  const backlog = readFileSync(join(projectRoot, 'BACKLOG.md'), 'utf8');
  const open = backlog.split('## Open')[1]?.split('## Done')[0] ?? '';
  const nextRow = open.split('\n').find(line => /^\|\s*\d+\s*\|/.test(line));
  const cells = nextRow?.split('|').map(s => s.trim());
  const implementation = { status: 'not_recorded', test_summary: null };
  const implementationPath = join(trialRoot, 'implementation.json');
  if (existsSync(implementationPath)) {
    try {
      const record = read(implementationPath);
      const matches = Object.entries(record.source_hashes ?? {}).every(([path, hash]) => {
        const full = resolve(projectRoot, path), local = relative(resolve(projectRoot), full);
        return !local.startsWith('..') && resolve(path) !== path && existsSync(full) && digest(readFileSync(full)) === hash;
      });
      implementation.status = matches && Object.keys(record.source_hashes ?? {}).length > 0 &&
        record.checks?.npm_test_exit_code === 0 ? 'verified_source_and_checks' : 'stale_or_unverified';
      if (implementation.status === 'verified_source_and_checks') implementation.test_summary = record.checks.summary;
    } catch { implementation.status = 'blocked_evidence'; }
  }
  return { schema_version: 1, observed_at: new Date().toISOString(),
    purpose: 'Better accepted work at comparable tokens, or equal quality for fewer tokens.',
    diagnostic: next(projectRoot), outcome, implementation,
    next_work: cells ? { id: cells[1], task: cells[2], evidence: cells[3], check: cells[4], gate: cells[6] } : null,
    connections: { repository: metadata.repository_url, parent: metadata.parent_url,
      library_work_id: metadata.library_work_id, library_status_recorded: metadata.library_registration_status,
      library_preview: metadata.library_preview_url ?? null,
      library_pr: metadata.library_registration_url, implementation_pr: metadata.implementation_url,
      status_scope: 'Repository records, not a fresh network or live-runtime check.' },
    artifacts: { system_map: 'docs/SYSTEM-MAP.md', outcome_report: `${trialPath}/README.md`,
      outcome_review: `${trialPath}/review.json`, backlog: 'BACKLOG.md' },
    claims_not_made: ['tenfold_improvement', 'live_ChatGPT_acceptance', 'automatic_skill_installation', 'fleet_savings'] };
}

export function serve(port = 8947, projectRoot = root) {
  const assets = new Map([['/', ['index.html', 'text/html']], ['/app.js', ['app.js', 'text/javascript']], ['/style.css', ['style.css', 'text/css']]]);
  const server = createServer((request, response) => {
    if (request.method !== 'GET') { response.writeHead(405); response.end('Read-only surface'); return; }
    const path = request.url?.split('?')[0];
    try {
      if (path === '/api/status') {
        const body = JSON.stringify(projectStatus(projectRoot));
        response.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
        response.end(body); return;
      }
      const asset = assets.get(path);
      if (!asset) { response.writeHead(404); response.end('Not found'); return; }
      const body = readFileSync(join(projectRoot, 'site', asset[0]));
      response.writeHead(200, { 'content-type': `${asset[1]}; charset=utf-8` });
      response.end(body);
    } catch {
      response.writeHead(500, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ status: 'blocked_evidence', error: 'Unable to read project evidence; inspect the local CLI.' }));
    }
  });
  server.listen(port, '127.0.0.1');
  return server;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv[2] === 'serve') {
      const port = Number(process.argv[3] ?? 8947);
      if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('invalid port');
      const server = serve(port);
      server.on('listening', () => console.log(`Harness Lab: http://127.0.0.1:${port}`));
      server.on('error', error => { console.error(error.message); process.exitCode = 1; });
    } else if (!process.argv[2] || process.argv[2] === 'status') console.log(JSON.stringify(projectStatus(), null, 2));
    else throw new Error('usage: project-status.mjs status|serve [port]');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
