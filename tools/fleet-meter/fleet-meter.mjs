#!/usr/bin/env node
// fleet-meter.mjs — read-only token-share meter for the Bifrost router.
//
// Answers: "what % of our agent tokens ran on which model tier, per day"
// from ~/.config/bifrost/logs.db (Bifrost HTTP, localhost:8080).
//
// READ-ONLY: opens logs.db with mode=ro via better-sqlite3; never writes,
// vacuums, or alters the database. If better-sqlite3 isn't available, falls
// back to shelling out to sqlite3(1) with file:...?mode=ro.
//
// Usage:
//   fleet-meter [--days N] [--html] [--db PATH]
//
// Output: plain-text tier rollup + per-day table to stdout.
// --html writes fleet-meter-report.html next to the script.

import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { openSync, writeSync, closeSync } from 'node:fs';

const DEFAULT_DB = `${process.env.HOME}/.config/bifrost/logs.db`;

// Model → tier mapping. Anything unrecognised falls into "other".
const TIER_OF = (model) => {
  const m = (model || '').toLowerCase();
  if (!m) return 'other';
  if (m.startsWith('claude-fable') || m.startsWith('claude-opus')) return 'fable-opus';
  if (m.startsWith('claude-haiku') || m.startsWith('MiniMax')) return 'haiku';
  if (m.startsWith('claude-sonnet')) return 'sonnet';
  return 'other';
};

const TIER_LABEL = {
  'fable-opus': 'fable/opus',
  haiku: 'haiku/MiniMax',
  sonnet: 'sonnet',
  other: 'other',
};

function parseArgs(argv) {
  const out = { days: 7, html: false, db: DEFAULT_DB };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--days') out.days = parseInt(argv[++i], 10);
    else if (a === '--html') out.html = true;
    else if (a === '--db') out.db = argv[++i];
    else if (a === '-h' || a === '--help') {
      console.log('Usage: fleet-meter [--days N] [--html] [--db PATH]');
      process.exit(0);
    }
  }
  return out;
}

// Try better-sqlite3 first (fast, in-process, mode=ro). Fall back to sqlite3 CLI.
async function openDb(path) {
  if (!existsSync(path)) {
    throw new Error(`logs.db not found at ${path}`);
  }
  try {
    const Database = (await import('better-sqlite3')).default;
    const db = new Database(path, { readonly: true, fileMustExist: true });
    return { kind: 'better', db, close: () => db.close() };
  } catch (e) {
    // Fall through to sqlite3 CLI.
    const uri = `file:${path}?mode=ro`;
    return {
      kind: 'cli',
      uri,
      query: (sql) =>
        execFileSync('sqlite3', [uri, sql], {
          encoding: 'utf8',
          maxBuffer: 64 * 1024 * 1024,
        }),
      close: () => {},
    };
  }
}

// Run a query, return array of row objects.
function queryAll(handle, sql) {
  if (handle.kind === 'better') {
    return handle.db.prepare(sql).all();
  }
  const text = handle.query(sql);
  if (!text.trim()) return [];
  const lines = text.trim().split('\n');
  // sqlite3 -header -separator is more robust; use that.
  const headerText = handle.queryWithHeader(sql);
  const header = headerText.header;
  const data = headerText.body;
  const cols = header.split('|');
  return data
    .split('\n')
    .filter((l) => l.length > 0)
    .map((line) => {
      const vals = line.split('|');
      const row = {};
      cols.forEach((c, i) => (row[c] = vals[i]));
      return row;
    });
}

// For sqlite3 CLI we need header + body separately.
function attachCliHelpers(handle) {
  if (handle.kind !== 'cli') return;
  handle.queryWithHeader = (sql) => {
    const text = execFileSync(
      'sqlite3',
      [handle.uri, '-header', '-separator', '|', sql],
      { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
    );
    const idx = text.indexOf('\n');
    const header = text.slice(0, idx);
    const body = text.slice(idx + 1).replace(/\n$/, '');
    return { header, body };
  };
}

function num(v) {
  if (v === null || v === undefined || v === '') return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function fmtInt(n) {
  return n.toLocaleString('en-US');
}

function fmtPct(n) {
  if (n === 0) return '0.0%';
  return `${(n * 100).toFixed(1)}%`;
}

function fmtDate(s) {
  // Take YYYY-MM-DD prefix from a SQLite timestamp string.
  return String(s).slice(0, 10);
}

async function main() {
  const args = parseArgs(process.argv);
  const handle = await openDb(args.db);
  attachCliHelpers(handle);

  // Tier rollup (across the whole window)
  const tierRows = queryAll(
    handle,
    `SELECT
       CASE
         WHEN LOWER(model) LIKE 'claude-fable%' OR LOWER(model) LIKE 'claude-opus%' THEN 'fable-opus'
         WHEN LOWER(model) LIKE 'claude-haiku%' OR LOWER(model) LIKE 'MiniMax%'        THEN 'haiku'
         WHEN LOWER(model) LIKE 'claude-sonnet%'                                       THEN 'sonnet'
         ELSE 'other'
       END AS tier,
       COUNT(*) AS requests,
       COALESCE(SUM(prompt_tokens),0)     AS input_tokens,
       COALESCE(SUM(completion_tokens),0) AS output_tokens
     FROM logs
     WHERE timestamp >= datetime('now', '-' || ${args.days} || ' days')
     GROUP BY tier
     ORDER BY output_tokens DESC;`,
  );

  // Per-day × model breakdown
  const dailyModelRows = queryAll(
    handle,
    `SELECT
       substr(timestamp,1,10) AS day,
       model,
       COUNT(*)              AS requests,
       COALESCE(SUM(prompt_tokens),0)     AS input_tokens,
       COALESCE(SUM(completion_tokens),0) AS output_tokens
     FROM logs
     WHERE timestamp >= datetime('now', '-' || ${args.days} || ' days')
     GROUP BY day, model
     ORDER BY day DESC, output_tokens DESC;`,
  );

  // Per-day totals (for share denominator)
  const dayTotalsRows = queryAll(
    handle,
    `SELECT
       substr(timestamp,1,10) AS day,
       COALESCE(SUM(completion_tokens),0) AS output_tokens
     FROM logs
     WHERE timestamp >= datetime('now', '-' || ${args.days} || ' days')
     GROUP BY day
     ORDER BY day DESC;`,
  );

  handle.close();

  const tierAgg = tierRows.map((r) => ({
    tier: TIER_LABEL[r.tier] || r.tier,
    requests: num(r.requests),
    input: num(r.input_tokens),
    output: num(r.output_tokens),
  }));
  const totalOut = tierAgg.reduce((a, b) => a + b.output, 0) || 1;
  for (const t of tierAgg) t.share = t.output / totalOut;

  const haiku = tierAgg.find((t) => t.tier === 'haiku/MiniMax');
  const verdict = `haiku share: ${fmtPct(haiku ? haiku.share : 0)} of output tokens (last ${args.days}d)`;

  // ---- plain text ----
  const lines = [];
  lines.push(`fleet-meter — last ${args.days} day(s) — ${args.db}`);
  lines.push('');
  lines.push('TIER ROLLUP (sorted by output tokens)');
  lines.push(
    `${'tier'.padEnd(16)}  ${'requests'.padStart(10)}  ${'input_tokens'.padStart(14)}  ${'output_tokens'.padStart(14)}  ${'share'.padStart(7)}`,
  );
  for (const t of tierAgg) {
    lines.push(
      `${t.tier.padEnd(16)}  ${fmtInt(t.requests).padStart(10)}  ${fmtInt(t.input).padStart(14)}  ${fmtInt(t.output).padStart(14)}  ${fmtPct(t.share).padStart(7)}`,
    );
  }
  lines.push('');
  lines.push(verdict);
  lines.push('');
  lines.push('PER-DAY × MODEL');

  // Group dailyModelRows by day
  const byDay = new Map();
  for (const r of dailyModelRows) {
    const d = r.day;
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push({
      model: r.model || '(blank)',
      requests: num(r.requests),
      input: num(r.input_tokens),
      output: num(r.output_tokens),
    });
  }
  const dayTotals = new Map(dayTotalsRows.map((r) => [r.day, num(r.output_tokens)]));
  const days = [...byDay.keys()].sort().reverse();
  for (const d of days) {
    lines.push('');
    lines.push(`  ${d}  (total output: ${fmtInt(dayTotals.get(d) || 0)})`);
    lines.push(
      `    ${'model'.padEnd(28)}  ${'requests'.padStart(8)}  ${'input_tokens'.padStart(12)}  ${'output_tokens'.padStart(13)}  ${'share'.padStart(6)}`,
    );
    const tot = dayTotals.get(d) || 1;
    for (const m of byDay.get(d)) {
      lines.push(
        `    ${m.model.padEnd(28)}  ${fmtInt(m.requests).padStart(8)}  ${fmtInt(m.input).padStart(12)}  ${fmtInt(m.output).padStart(13)}  ${fmtPct(m.output / tot).padStart(6)}`,
      );
    }
  }

  const out = lines.join('\n') + '\n';
  process.stdout.write(out);

  if (args.html) {
    const html = renderHtml({
      days: args.days,
      db: args.db,
      verdict,
      tierAgg,
      byDay,
      dayTotals,
    });
    const outPath = resolve(process.argv[1], '..', 'fleet-meter-report.html');
    const fd = openSync(outPath, 'w');
    writeSync(fd, html);
    closeSync(fd);
    process.stderr.write(`wrote ${outPath}\n`);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderHtml({ days, db, verdict, tierAgg, byDay, dayTotals }) {
  const tierRows = tierAgg
    .map(
      (t) => `<tr>
      <td>${escapeHtml(t.tier)}</td>
      <td style="text-align:right">${fmtInt(t.requests)}</td>
      <td style="text-align:right">${fmtInt(t.input)}</td>
      <td style="text-align:right">${fmtInt(t.output)}</td>
      <td style="text-align:right">${fmtPct(t.share)}</td>
    </tr>`,
    )
    .join('');
  const dayBlocks = [...byDay.keys()]
    .sort()
    .reverse()
    .map((d) => {
      const tot = dayTotals.get(d) || 1;
      const modelRows = byDay
        .get(d)
        .map(
          (m) => `<tr>
          <td>${escapeHtml(m.model)}</td>
          <td style="text-align:right">${fmtInt(m.requests)}</td>
          <td style="text-align:right">${fmtInt(m.input)}</td>
          <td style="text-align:right">${fmtInt(m.output)}</td>
          <td style="text-align:right">${fmtPct(m.output / tot)}</td>
        </tr>`,
        )
        .join('');
      return `<h2>${escapeHtml(d)} <span style="color:#888;font-weight:400;font-size:14px">total output ${fmtInt(tot)}</span></h2>
      <table>
        <thead><tr><th>model</th><th style="text-align:right">requests</th><th style="text-align:right">input_tokens</th><th style="text-align:right">output_tokens</th><th style="text-align:right">share</th></tr></thead>
        <tbody>${modelRows}</tbody>
      </table>`;
    })
    .join('\n');
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>fleet-meter — last ${days}d</title>
<style>
body{font:14px/1.4 -apple-system,system-ui,sans-serif;margin:24px;max-width:920px;color:#222}
h1{margin:0 0 8px 0}
.meta{color:#888;font-size:12px;margin-bottom:24px}
.verdict{font:600 16px -apple-system,system-ui,sans-serif;background:#f4f4f4;padding:12px 16px;border-radius:8px;margin:16px 0 24px}
table{border-collapse:collapse;margin:8px 0 24px;width:100%}
th,td{border-bottom:1px solid #eee;padding:6px 10px}
th{text-align:left;background:#fafafa;font-weight:600}
h2{margin:24px 0 8px;border-bottom:1px solid #eee;padding-bottom:4px}
</style></head><body>
<h1>fleet-meter — last ${days} day(s)</h1>
<div class="meta">source: ${escapeHtml(db)}</div>
<div class="verdict">${escapeHtml(verdict)}</div>
<h2>Tier rollup</h2>
<table>
  <thead><tr><th>tier</th><th style="text-align:right">requests</th><th style="text-align:right">input_tokens</th><th style="text-align:right">output_tokens</th><th style="text-align:right">share</th></tr></thead>
  <tbody>${tierRows}</tbody>
</table>
${dayBlocks}
</body></html>`;
}

main().catch((e) => {
  console.error(`fleet-meter error: ${e.message}`);
  process.exit(1);
});