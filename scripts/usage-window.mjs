import { createReadStream, readFileSync, statSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const fields = ['input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens'];
const zero = () => Object.fromEntries(fields.map(k => [k, 0]));
function instant(value) {
  if (typeof value !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) {
    throw new Error('timestamp requires an explicit timezone');
  }
  return Date.parse(value);
}

// Explicit sources only; no directory discovery, model calls, billing conversion or transcript output.
export async function usageWindow(manifest) {
  const start = instant(manifest.start), end = instant(manifest.end);
  if (start >= end || !Array.isArray(manifest.sources) || !manifest.sources.length || manifest.sources.length > 8) {
    throw new Error('require an ordered window and 1–8 explicit sources');
  }
  const ids = new Set(); let bytes = 0;
  for (const source of manifest.sources) {
    if (!['id', 'path', 'role'].every(k => typeof source[k] === 'string' && source[k]) || ids.has(source.id)) throw new Error('invalid/duplicate source identity');
    ids.add(source.id);
    const stat = statSync(source.path);
    if (!stat.isFile() || stat.size > 128 * 1024 * 1024) throw new Error('source unavailable or exceeds 128MiB');
    bytes += stat.size;
  }
  if (bytes > 256 * 1024 * 1024) throw new Error('selected sources exceed 256MiB');
  const results = [];
  for (const source of manifest.sources) {
    const result = { id: source.id, role: source.role, responses: 0, duplicate_records: 0,
      usage: zero(), models: {}, rate_observations: {}, max_input_tokens: 0, first: null, last: null };
    const seen = new Map(); let model = 'unknown', effort = 'unknown', identity = false, lineNumber = 0;
    const size = statSync(source.path).size;
    if (!size || size > 128 * 1024 * 1024) throw new Error('source empty or changed beyond limit');
    const hash = createHash('sha256');
    const stream = createReadStream(source.path, { end: size - 1 });
    stream.on('data', bytes => hash.update(bytes));
    const lines = createInterface({ input: stream, crlfDelay: Infinity });
    try {
      for await (const line of lines) {
        lineNumber++;
        if (!line.trim()) continue;
        let event;
        try { event = JSON.parse(line); } catch { throw new Error('malformed JSON record'); }
        if (!event || typeof event !== 'object') throw new Error('invalid event record');
        const p = event.payload ?? {};
        if (!identity) {
          if (event.type !== 'session_meta' || p.id !== source.id) throw new Error('source identity mismatch');
          identity = true;
        }
        if (event.type === 'turn_context') { model = p.model ?? 'unknown'; effort = p.effort ?? 'unknown'; }
        if (event.type !== 'token_usage_record' && !(event.type === 'event_msg' && p.type === 'token_count')) continue;
        const timestamp = instant(event.timestamp);
        if (event.type === 'token_usage_record') {
          if (p.thread_id && p.thread_id !== source.id) throw new Error('usage thread mismatch');
          if (typeof p.response_id !== 'string' || !p.response_id || !fields.every(k => Number.isSafeInteger(p.usage?.[k]) && p.usage[k] >= 0) ||
              p.usage.cached_input_tokens > p.usage.input_tokens || p.usage.reasoning_output_tokens > p.usage.output_tokens) {
            throw new Error('invalid response usage');
          }
          const signature = JSON.stringify(fields.map(k => p.usage[k]));
          if (seen.has(p.response_id)) {
            if (seen.get(p.response_id) !== signature) throw new Error('conflicting duplicate response usage');
            if (timestamp >= start && timestamp < end) result.duplicate_records++;
            continue;
          }
          seen.set(p.response_id, signature);
          if (timestamp < start || timestamp >= end) continue;
          const key = JSON.stringify([model, effort]);
          const group = result.models[key] ??= { responses: 0, ...zero() };
          group.responses++; result.responses++;
          for (const k of fields) { result.usage[k] += p.usage[k]; group[k] += p.usage[k]; }
          result.max_input_tokens = Math.max(result.max_input_tokens, p.usage.input_tokens);
          if (!result.first || timestamp < Date.parse(result.first)) result.first = event.timestamp;
          if (!result.last || timestamp > Date.parse(result.last)) result.last = event.timestamp;
        } else if (timestamp >= start && timestamp < end && p.rate_limits) {
          // Keep resets and separate windows; never attach the label to a model/request.
          const r = p.rate_limits;
          for (const kind of ['primary', 'secondary']) {
            const w = r[kind]; if (!w || !Number.isFinite(w.used_percent)) continue;
            const key = JSON.stringify([r.limit_id ?? 'unknown', kind, w.window_minutes, w.resets_at]);
            const group = result.rate_observations[key] ??= { observations: 0, min_percent: w.used_percent, max_percent: w.used_percent };
            group.observations++; group.min_percent = Math.min(group.min_percent, w.used_percent);
            group.max_percent = Math.max(group.max_percent, w.used_percent);
          }
        }
      }
      if (!identity) throw new Error('empty source');
    } catch (error) { throw new Error(`${source.id} line ${lineNumber}: ${error.message}`); }
    finally { lines.close(); stream.destroy(); }
    result.source_snapshot = { path: source.path, bytes: size, sha256: hash.digest('hex') };
    result.usage.uncached_input_tokens = result.usage.input_tokens - result.usage.cached_input_tokens;
    result.mean_input_tokens = result.responses ? result.usage.input_tokens / result.responses : null;
    result.status = result.responses ? 'observed' : 'no_response_usage_in_window';
    results.push(result);
  }
  return { start: manifest.start, end: manifest.end, sources: results,
    scope: 'Explicit-source sample; unique response increments only. No fleet completeness, accepted-outcome or subscription-cost inference.' };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv.length !== 3) throw new Error('usage: usage-window.mjs MANIFEST.json');
    console.log(JSON.stringify(await usageWindow(JSON.parse(readFileSync(process.argv[2], 'utf8'))), null, 2));
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
