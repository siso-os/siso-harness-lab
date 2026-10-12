#!/usr/bin/env node
// Claude Code transcript token totals — the Claude-side twin of usage-window.mjs (which reads Codex rollouts).
// Usage: node scripts/claude-usage.mjs <session.jsonl> [more.jsonl ...]   (sub-agent files: <session>/subagents/*.jsonl)
// Read-only. Counts each API response once (Claude Code writes one line per content block with the same message id).
// Reports tokens only: no billing conversion, no transcript content.
import { createReadStream, statSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { basename } from 'node:path';

export async function claudeUsage(path) {
  if (!statSync(path).isFile()) throw new Error(`not a file: ${path}`);
  const seen = new Set();
  const r = { source: basename(path), responses: 0, uncached_input_tokens: 0, cache_write_tokens: 0,
    cache_read_tokens: 0, output_tokens: 0, max_context_tokens: 0, models: {}, first: null, last: null };
  for await (const line of createInterface({ input: createReadStream(path), crlfDelay: Infinity })) {
    if (!line.includes('"usage"')) continue;
    let o; try { o = JSON.parse(line); } catch { continue; }
    const m = o.message, u = m?.usage;
    if (o.type !== 'assistant' || !u) continue;
    const key = m.id || o.requestId || o.uuid;
    if (seen.has(key)) continue;
    seen.add(key);
    const inp = u.input_tokens || 0, cw = u.cache_creation_input_tokens || 0, cr = u.cache_read_input_tokens || 0;
    r.responses++;
    r.uncached_input_tokens += inp; r.cache_write_tokens += cw; r.cache_read_tokens += cr;
    r.output_tokens += u.output_tokens || 0;
    r.max_context_tokens = Math.max(r.max_context_tokens, inp + cw + cr);
    const model = m.model || 'unknown';
    r.models[model] = (r.models[model] || 0) + 1;
    r.first ??= o.timestamp; r.last = o.timestamp || r.last;
  }
  r.mean_context_tokens = r.responses ? Math.round((r.uncached_input_tokens + r.cache_write_tokens + r.cache_read_tokens) / r.responses) : 0;
  return r;
}

if (process.argv[1] && import.meta.url.endsWith(basename(process.argv[1]))) {
  const paths = process.argv.slice(2);
  if (!paths.length) { console.error('usage: claude-usage.mjs <session.jsonl> [...]'); process.exit(2); }
  try {
    console.log(JSON.stringify(await Promise.all(paths.map(claudeUsage)), null, 2));
  } catch (e) { console.error(String(e.message || e)); process.exit(2); }
}
