#!/usr/bin/env node
/**
 * herdr-snapshot — archive herdr's own session topology for resurrection.
 *
 * herdr ALREADY persists full topology (workspaces/tabs/panes/cwd/labels + the
 * claude/codex agent_session UUID) to ~/.config/herdr/session.json every few
 * seconds. We do NOT re-derive that. This snapshotter just keeps timestamped
 * COPIES (last 10) so a bad session.json write can't lose the topology, and
 * captures a parallel live `pane list` for verification/diagnostics.
 *
 * Read-only against the live server (one `pane list` API call). Never mutates
 * herdr state. Writes only to ~/.local/state/herdr-resurrect/.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync, statSync, unlinkSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const HOME = homedir();
const HERDR = join(HOME, '.local/bin/herdr');
const SESSION_JSON = join(HOME, '.config/herdr/session.json');
const OUT_DIR = join(HOME, '.local/state/herdr-resurrect');
const KEEP = 10;

function ts() {
  return new Date().toISOString().replace(/[:.]/g, '-').replace('T', '_').slice(0, 19);
}

function safePaneList() {
  try {
    const raw = execFileSync(HERDR, ['pane', 'list'], { encoding: 'utf8', timeout: 15000 });
    return JSON.parse(raw);
  } catch (e) {
    return { error: String(e.message || e) };
  }
}

function main() {
  mkdirSync(OUT_DIR, { recursive: true });

  if (!existsSync(SESSION_JSON)) {
    console.error(`[herdr-snapshot] no session.json at ${SESSION_JSON} — herdr not running?`);
    process.exit(2);
  }

  let session;
  try {
    session = JSON.parse(readFileSync(SESSION_JSON, 'utf8'));
  } catch (e) {
    console.error(`[herdr-snapshot] session.json unreadable: ${e.message}`);
    process.exit(3);
  }

  // Count panes for a quick fidelity number.
  let paneCount = 0;
  for (const w of session.workspaces || []) {
    for (const t of w.tabs || []) paneCount += Object.keys(t.panes || {}).length;
  }

  const stamp = ts();
  const snap = {
    captured_at: new Date().toISOString(),
    source: 'herdr-session.json',
    pane_count: paneCount,
    workspace_count: (session.workspaces || []).length,
    session,                 // herdr's own persisted topology (the resurrection source of truth)
    live_pane_list: safePaneList(), // parallel live capture for verification/diagnostics
  };

  const outFile = join(OUT_DIR, `snapshot-${stamp}.json`);
  writeFileSync(outFile, JSON.stringify(snap, null, 2));

  // Maintain a stable "latest" pointer that restore reads.
  writeFileSync(join(OUT_DIR, 'latest.json'), JSON.stringify(snap, null, 2));

  // Prune to KEEP most-recent timestamped snapshots.
  const snaps = readdirSync(OUT_DIR)
    .filter((f) => f.startsWith('snapshot-') && f.endsWith('.json'))
    .map((f) => ({ f, m: statSync(join(OUT_DIR, f)).mtimeMs }))
    .sort((a, b) => b.m - a.m);
  for (const s of snaps.slice(KEEP)) unlinkSync(join(OUT_DIR, s.f));

  console.log(`[herdr-snapshot] ${stamp}: ${paneCount} panes / ${snap.workspace_count} workspaces -> ${outFile}`);
}

main();
