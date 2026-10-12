import { readFileSync, writeFileSync, lstatSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join, resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

// Scores task decisions, not response length, token savings or live execution.
export function grade(response, rubric) {
  const expected = rubric.expected_actions;
  if (!expected || !Object.keys(expected).length) throw new Error('empty rubric');
  const errors = [], seen = new Set(), cases = [];
  if (response?.experiment !== rubric.experiment) errors.push('wrong experiment');
  if (!Array.isArray(response?.responses)) errors.push('responses must be an array');
  for (const row of Array.isArray(response?.responses) ? response.responses : []) {
    if (!row || !Object.hasOwn(expected, row.id)) {
      errors.push('unknown case');
      continue;
    }
    if (seen.has(row.id)) {
      errors.push(`duplicate case: ${row.id}`);
      continue;
    }
    seen.add(row.id);
    const explanation = typeof row.explanation === 'string' ? row.explanation.trim() : '';
    const format_ok = explanation.length > 0 && explanation.split(/\s+/).length <= 30;
    cases.push({ id: row.id, correct: row.action === expected[row.id] && format_ok });
  }
  for (const id of Object.keys(expected)) if (!seen.has(id)) errors.push(`missing case: ${id}`);
  const correct = cases.filter(c => c.correct).length, total = Object.keys(expected).length;
  return { experiment: rubric.experiment, accepted: errors.length === 0 && correct === total,
    correct, total, cases, errors, evidence_class: 'decision_response',
    acceptance_scope: 'structured_decisions_only', explanations_require_review: true,
    live_outcome_verified: false, token_savings_measured: false };
}

const RUN = '2026-09-08-outcome-quality';

// Reserve before allocating model work. This is a receipt in the existing run,
// not a scheduler. Never steal a reservation or infer that its owner is dead.
export function claimResponse(projectRoot, arm, owner) {
  if (!['baseline', 'candidate'].includes(arm) || typeof owner !== 'string' ||
      !owner.trim() || owner.length > 160) throw new Error('invalid claim');
  const run = join(projectRoot, 'reports', RUN);
  try {
    lstatSync(join(run, `${arm}-response.json`));
    throw new Error('already recorded: do not dispatch another evaluator');
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const frozenBytes = readFileSync(join(run, 'frozen-inputs.json'));
  const frozen = JSON.parse(frozenBytes);
  if (!frozen.inputs || !Object.keys(frozen.inputs).length) throw new Error('missing frozen inputs');
  for (const [path, hash] of Object.entries(frozen.inputs)) {
    const full = resolve(projectRoot, path), local = relative(resolve(projectRoot), full);
    if (local.startsWith('..') || resolve(path) === path ||
        createHash('sha256').update(readFileSync(full)).digest('hex') !== hash) throw new Error(`changed frozen input: ${path}`);
  }
  const claim = { experiment: frozen.experiment, arm, owner, claimed_at: new Date().toISOString(),
    frozen_inputs_hash: createHash('sha256').update(frozenBytes).digest('hex') };
  try {
    writeFileSync(join(run, `${arm}-claim.json`), JSON.stringify(claim, null, 2) + '\n', { flag: 'wx' });
  } catch (error) {
    if (error.code === 'EEXIST') throw new Error('already claimed: inspect the existing owner; do not dispatch');
    throw error;
  }
  return { status: 'claimed', dispatch_allowed: true, ...claim };
}

function publicationError(message) {
  throw new Error(`invalid response: ${message}`);
}

export function recordResponse(projectRoot, arm, response) {
  if (arm !== 'baseline' && arm !== 'candidate') publicationError('arm');

  let fixture;
  try {
    fixture = JSON.parse(readFileSync(join(projectRoot, 'experiments', 'owner-continuation-cases.json'), 'utf8'));
  } catch (error) {
    publicationError(`fixture: ${error.message}`);
  }
  if (!response || typeof response !== 'object' || Array.isArray(response)) publicationError('object');
  if (response.experiment !== fixture.id) publicationError('experiment');
  if (!Array.isArray(response.responses)) publicationError('responses must be an array');

  const caseIds = new Set(fixture.cases.map(c => c.id));
  const actionLabels = new Set(fixture.actions);
  const seen = new Set();
  if (response.responses.length !== caseIds.size) publicationError('case count');
  for (const row of response.responses) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) publicationError('case row');
    if (typeof row.id !== 'string' || !caseIds.has(row.id)) publicationError('case ID');
    if (seen.has(row.id)) publicationError(`duplicate case: ${row.id}`);
    seen.add(row.id);
    if (typeof row.action !== 'string' || !actionLabels.has(row.action)) publicationError(`action: ${row.id}`);
    const explanation = typeof row.explanation === 'string' ? row.explanation.trim() : '';
    if (!explanation || explanation.split(/\s+/).length > 30) publicationError(`explanation: ${row.id}`);
  }
  if (seen.size !== caseIds.size) publicationError('missing case');

  const destination = join(projectRoot, 'reports', RUN, `${arm}-response.json`);
  try {
    writeFileSync(destination, `${JSON.stringify(response, null, 2)}\n`, { encoding: 'utf8', flag: 'wx' });
  } catch (error) {
    if (error.code === 'EEXIST') throw new Error(`publication conflict: ${destination}`);
    throw error;
  }
  return destination;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv[2] === 'claim') {
      if (process.argv.length !== 5) throw new Error('usage: grade-outcome.mjs claim baseline|candidate OWNER_ID');
      console.log(JSON.stringify(claimResponse(resolve('.'), process.argv[3], process.argv[4]), null, 2));
    } else if (process.argv[2] === 'record') {
      if (process.argv.length !== 5) throw new Error('usage: grade-outcome.mjs record baseline|candidate INPUT.json');
      const destination = recordResponse(resolve('.'), process.argv[3], JSON.parse(readFileSync(process.argv[4], 'utf8')));
      console.log(destination);
    } else {
      if (process.argv.length !== 3) throw new Error('usage: grade-outcome.mjs RESPONSE.json');
      const rubric = JSON.parse(readFileSync(new URL('../experiments/owner-continuation-rubric.json', import.meta.url)));
      const result = grade(JSON.parse(readFileSync(process.argv[2])), rubric);
      console.log(JSON.stringify(result, null, 2));
      process.exitCode = result.accepted ? 0 : 1;
    }
  } catch (error) { console.error(error.message); process.exitCode = 2; }
}
