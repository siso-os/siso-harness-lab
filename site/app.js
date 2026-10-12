const text = (id, value) => { document.getElementById(id).textContent = value; };
const clean = value => String(value ?? '').replace(/\*\*|`/g, '');

async function load() {
  try {
    const response = await fetch('/api/status', { cache: 'no-store' });
    if (!response.ok) throw new Error('Project evidence is unavailable. Run npm run project:status to inspect the cause.');
    const state = await response.json(), trial = state.outcome;
    text('diagnostic', `${state.diagnostic.completed_cycles} recorded cycle${state.diagnostic.completed_cycles === 1 ? '' : 's'}`);
    text('scores', ['baseline', 'candidate'].map(arm => {
      const result = trial.results[arm]; return result ? `${result.correct}/${result.total}` : 'Pending';
    }).join('  ·  '));
    text('decision-caption', 'Baseline · candidate. Current structured decision scores only.');
    text('promotion', trial.review?.verdict === 'no_promotion' ? 'Not promoted' : 'Review required');
    text('implementation-status', clean(state.implementation.status.replaceAll('_', ' ')));
    text('implementation-checks', state.implementation.test_summary ?? 'Current source/check receipt must be verified before this change earns a passing badge.');
    text('trial-status', clean(trial.status.replaceAll('_', ' ')));
    text('protocol', trial.errors.length ? trial.errors.join('. ') :
      trial.review?.protocol_status === 'duplicate_execution_collision'
        ? 'Protocol collision: overlapping evaluator attempts wrote the same candidate path. Preserved and reconciled; this is not a clean cost comparison.'
        : 'No live outcome or fleet-level improvement is inferred from these task responses.');
    for (const limit of trial.review?.limits ?? ['Independent result and explanation review remain required.']) {
      const item = document.createElement('li'); item.textContent = limit; document.getElementById('limits').append(item);
    }
    text('next-title', state.next_work ? `Backlog ${state.next_work.id}` : 'No open backlog item');
    text('next-task', clean(state.next_work?.task ?? 'Record the next source-backed experiment before starting work.'));
    text('next-check', clean(state.next_work?.check));
    text('next-gate', clean(state.next_work?.gate));
    text('library-status', clean(state.connections.library_status_recorded.replaceAll('_', ' ')) + '.');
    if (state.connections.library_preview?.startsWith('http://127.0.0.1:')) {
      const link = document.getElementById('library-preview'); link.href = state.connections.library_preview; link.hidden = false;
    }
    for (const [id, url] of [['library-link', state.connections.library_pr], ['repo-link', state.connections.repository], ['pr-link', state.connections.implementation_pr]]) {
      if (typeof url === 'string' && url.startsWith('https://')) document.getElementById(id).href = url;
    }
    text('observed', `Read from local evidence ${new Date(state.observed_at).toLocaleString()}. Network status is last recorded.`);
    document.getElementById('loaded').hidden = false;
  } catch (error) { text('error', error.message); document.getElementById('error').hidden = false; }
}
load();
