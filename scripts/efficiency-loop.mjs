import { readFileSync, readdirSync, mkdirSync, writeFileSync, rmdirSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDiagnostic, policies, quality } from './output-policies.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const hash = text => createHash('sha256').update(text).digest('hex');

export function evaluate(spec) {
  if (spec.id !== 'output-retrieval-v1' || !Array.isArray(spec.cases) || !spec.cases.length ||
      new Set(spec.cases.map(c => c.id)).size !== spec.cases.length ||
      !spec.cases.some(c => c.split === 'held_out') || !spec.cases.some(c => c.split === 'development') ||
      spec.cases.some(c => !['development', 'held_out'].includes(c.split))) throw new Error('invalid experiment');
  return Object.entries(policies).map(([policy, run]) => {
    const cases = spec.cases.map(c => {
      const diagnostic = makeDiagnostic(c), output = run(diagnostic);
      return { id: c.id, split: c.split, correct: quality(output, diagnostic),
        bytes: Buffer.byteLength(output), baseline_bytes: Buffer.byteLength(policies.full(diagnostic)) };
    });
    const correct = cases.every(c => c.correct);
    const bytes = cases.reduce((n,c) => n+c.bytes, 0);
    const baseline = cases.reduce((n,c) => n+c.baseline_bytes, 0);
    return { policy, verdict: !correct ? 'rejected_quality' : bytes < baseline ? 'fixture_gain' : 'baseline',
      correct, bytes, baseline_bytes: baseline, cases };
  });
}

export function inputs(projectRoot = root) {
  const files = ['experiments/output-retrieval.json', 'scripts/output-policies.mjs', 'scripts/efficiency-loop.mjs', 'tests/efficiency-loop.test.mjs'];
  const source_hashes = Object.fromEntries(files.map(p => [p, hash(readFileSync(join(projectRoot,p)))]));
  return { fingerprint: hash(JSON.stringify(source_hashes)), source_hashes,
    spec: JSON.parse(readFileSync(join(projectRoot, files[0]), 'utf8')) };
}

export function receipts(projectRoot = root) {
  const dir = join(projectRoot, 'reports/efficiency-loop');
  if (!existsSync(dir)) return [];
  const runs = readdirSync(dir).filter(f => /^[a-f0-9]{64}\.json$/.test(f)).map(f => {
    const record = JSON.parse(readFileSync(join(dir, f), 'utf8'));
    if (f !== record.fingerprint + '.json') throw new Error('receipt identity mismatch');
    const { receipt_hash, ...body } = record;
    if (receipt_hash !== hash(JSON.stringify(body))) throw new Error('receipt integrity mismatch');
    return record;
  }).sort((a,b) => a.sequence-b.sequence);
  for (let i=0; i<runs.length; i++) {
    if (runs[i].sequence !== i+1 || runs[i].previous !== (runs[i-1]?.receipt_hash ?? null)) throw new Error('broken receipt chain');
  }
  return runs;
}

export function cycle(projectRoot = root) {
  const lock = join(projectRoot, '.loop.lock');
  mkdirSync(lock); // Exclusive writer; never steal or silently remove an existing lock.
  try {
    const input = inputs(projectRoot), history = receipts(projectRoot);
    if (history.some(r => r.fingerprint === input.fingerprint)) return { status: 'unchanged', next: 'No new candidate/evidence. Take the real-case gate or another unblocked BACKLOG item.' };
    const record = { schema_version: 1, sequence: history.length+1, previous: history.at(-1)?.receipt_hash ?? null,
      fingerprint: input.fingerprint, source_hashes: input.source_hashes, experiment: input.spec.id,
      recorded_at: new Date().toISOString(), evidence_class: 'synthetic_regression', promotion: 'fixture_only',
      results: evaluate(input.spec), next_gate: 'paired_real_task_with_fresh_holdout',
      claims_not_made: ['model_token_savings', 'fleet_behavior_improved', 'global_installation', 'weight_training'] };
    record.receipt_hash = hash(JSON.stringify(record));
    const dir = join(projectRoot, 'reports/efficiency-loop'); mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, input.fingerprint+'.json'), JSON.stringify(record,null,2)+'\n', { flag:'wx' });
    return { status: 'recorded', receipt: `reports/efficiency-loop/${input.fingerprint}.json`,
      results: record.results.map(({policy, verdict, bytes, baseline_bytes}) => ({policy,verdict,bytes,baseline_bytes})), next: record.next_gate };
  } finally { rmdirSync(lock); }
}

export function next(projectRoot = root) {
  const input = inputs(projectRoot), history = receipts(projectRoot);
  return { status: history.some(r => r.fingerprint === input.fingerprint) ? 'needs_new_evidence' : 'ready_to_evaluate',
    experiment: input.spec.id, completed_cycles: history.length, backlog: 'BACKLOG.md',
    next: history.some(r => r.fingerprint === input.fingerprint)
      ? 'Add a privacy-reviewed real task and fresh hold-out; measure decision quality and actual usage. If unavailable, select another unblocked backlog item.'
      : 'Run npm test then npm run loop:cycle; record the lesson and continue.',
    runtime: 'assigned_agent_session', scheduler: 'none' };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const command = process.argv[2];
    let result;
    if (command === 'next') result = next();
    else if (command === 'cycle') result = cycle();
    else if (command === 'check') {
      receipts();
      const results = evaluate(inputs().spec);
      if (results.find(r => r.policy === 'focused').verdict !== 'fixture_gain' ||
          results.find(r => r.policy === 'blind_cap').verdict !== 'rejected_quality') throw new Error('regression in evidence-preserving output');
      result = { status: 'pass', evidence_class: 'synthetic_regression', policies: results.map(r => ({policy:r.policy,verdict:r.verdict})) };
    } else throw new Error('usage: efficiency-loop.mjs next|cycle|check');
    console.log(JSON.stringify(result,null,2));
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
