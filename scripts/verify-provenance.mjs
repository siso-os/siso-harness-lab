import { readFileSync, statSync, createReadStream } from 'node:fs';
import { createHash } from 'node:crypto';
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// On demand, exact locators only. Never return conversation text or discover logs.
export async function verifyProvenance(receipt, projectRoot) {
  if (!Array.isArray(receipt?.attempts) || !receipt.attempts.length) throw new Error('missing attempts');
  const attempts = [];
  for (const expected of receipt.attempts) {
    const result = { thread: expected.id, status: 'unavailable', errors: [] };
    attempts.push(result);
    if (typeof expected.id !== 'string' || !expected.id || typeof expected.rollout_path !== 'string' ||
        typeof expected.rollout_sha256 !== 'string' || typeof expected.model_provider !== 'string' ||
        expected.source === undefined || !Array.isArray(expected.observed_models) || !expected.observed_models.length ||
        !Array.isArray(expected.observed_efforts) || !expected.observed_efforts.length ||
        !['input_tokens', 'cached_input_tokens', 'output_tokens'].every(k => Number.isFinite(expected.usage?.[k]))) {
      result.status = 'invalid_receipt'; result.errors.push('missing source locator/hash'); continue;
    }
    try {
      const stat = statSync(expected.rollout_path);
      if (!stat.isFile()) { result.errors.push('source is not a regular file'); continue; }
      if (stat.size > 8 * 1024 * 1024) {
        result.errors.push('source exceeds this bounded verifier limit'); continue;
      }
    } catch (error) { result.errors.push(error.code ?? 'source unavailable'); continue; }
    const stream = createReadStream(expected.rollout_path);
    const hash = createHash('sha256'); stream.on('data', bytes => hash.update(bytes));
    const lines = createInterface({ input: stream, crlfDelay: Infinity });
    let readError = null;
    stream.on('error', error => { readError = error.code ?? 'source read error'; lines.close(); });
    const models = new Set(), efforts = new Set(), responses = new Map(), usage = {};
    let scoped = false, lineNumber = 0;
    try {
      for await (const line of lines) {
        lineNumber++;
        if (!line.trim()) continue;
        const event = JSON.parse(line), payload = event.payload ?? {};
        if (!scoped) {
          if (event.type !== 'session_meta' || payload.id !== expected.id ||
              typeof payload.cwd !== 'string' || resolve(payload.cwd) !== resolve(projectRoot)) {
            result.errors.push('source identity/project scope mismatch'); break;
          }
          scoped = true;
          const declared = typeof expected.source === 'string' && expected.source.startsWith('{') ? JSON.parse(expected.source) : expected.source;
          if (typeof declared === 'string') {
            if (payload.source !== declared) result.errors.push('launch source mismatch');
          } else {
            const wanted = declared?.subagent?.thread_spawn, actual = payload.source?.subagent?.thread_spawn;
            if (!wanted || !actual || !['agent_role', 'agent_path', 'parent_thread_id'].every(k => wanted[k] === actual[k])) result.errors.push('native role/source mismatch');
          }
          if (payload.model_provider !== expected.model_provider) result.errors.push('recorded provider mismatch');
        }
        if (event.type === 'turn_context') { models.add(payload.model); efforts.add(payload.effort); }
        if (event.type !== 'token_usage_record') continue;
        if (typeof payload.response_id !== 'string' || !payload.usage ||
            !['input_tokens', 'cached_input_tokens', 'output_tokens'].every(k =>
              Number.isFinite(payload.usage[k]) && payload.usage[k] >= 0) ||
            payload.usage.cached_input_tokens > payload.usage.input_tokens) throw new Error('invalid usage record');
        const encoded = JSON.stringify(payload.usage);
        if (responses.has(payload.response_id)) {
          if (responses.get(payload.response_id) !== encoded) throw new Error('conflicting duplicate response usage');
          continue;
        }
        responses.set(payload.response_id, encoded);
        for (const [key, value] of Object.entries(payload.usage)) {
          if (!Number.isFinite(value) || value < 0) throw new Error('invalid usage value');
          usage[key] = (usage[key] ?? 0) + value;
        }
      }
    } catch { result.errors.push(`invalid source record at line ${lineNumber}`); }
    finally { lines.close(); stream.destroy(); }
    if (readError) { result.status = 'unavailable'; result.errors.push(readError); continue; }
    if (!scoped) { result.status = 'scope_mismatch'; continue; }
    if (!responses.size) result.errors.push('no attributable usage records');
    if (hash.digest('hex') !== expected.rollout_sha256) result.errors.push('source changed since capture');
    if (JSON.stringify([...models].sort()) !== JSON.stringify([...(expected.observed_models ?? [])].sort()) ||
        JSON.stringify([...efforts].sort()) !== JSON.stringify([...(expected.observed_efforts ?? [])].sort())) result.errors.push('model/effort metadata mismatch');
    for (const [key, value] of Object.entries(expected.usage ?? {})) {
      if (usage[key] !== value) result.errors.push(`usage mismatch: ${key}`);
    }
    if (!expected.usage || !Object.keys(expected.usage).length) result.errors.push('missing expected usage');
    result.status = result.errors.length ? 'mismatch' : 'verified';
    result.response_ids = responses.size;
  }
  return { status: attempts.every(a => a.status === 'verified') ? 'verified' :
    attempts.some(a => !['verified', 'unavailable'].includes(a.status)) ? 'mismatch' : 'unavailable',
    attempts, scope: 'Recorded source identity/model/usage; live invocation evidence remains separate.',
    raw_content_returned: false, sources_discovered: false };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.length !== 3) throw new Error('usage: verify-provenance.mjs RECEIPT.json');
    const result = await verifyProvenance(JSON.parse(readFileSync(process.argv[2])), resolve('.'));
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = result.status === 'verified' ? 0 : result.status === 'unavailable' ? 2 : 1;
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
