#!/usr/bin/env node
/**
 * herdr-restore — relaunch the AI agents that herdr's native restore leaves out.
 *
 * WHAT HERDR DOES NATIVELY (verified 2026-07-02 from herdr-server.log):
 *   On server start it restores the full topology from session.json —
 *   workspaces (+custom names), tabs (+labels), panes (+cwd) — but spawns them
 *   as BARE SHELLS. It does NOT relaunch the claude/codex agents; Shaan
 *   re-starts each by hand after a reboot.
 *
 * WHAT THIS FILLS:
 *   session.json records, per pane, agent_session = {agent:'claude'|'codex',
 *   kind:'id', value:<session-uuid>}. For each such pane we find the now-bare
 *   live pane in the same workspace+tab and run the resume command into it:
 *       claude --resume <uuid> --dangerously-skip-permissions
 *       codex resume <uuid>
 *
 * MATCHING (both stable across a herdr restart — verified):
 *   - workspace: session.json workspace `id` == live pane `workspace_id`.
 *   - tab: session.json tabs are an ordered list whose `custom_name` == live tab
 *     `label`, and whose order == live tab position. We match by label first,
 *     positional index as fallback.
 *
 * IDEMPOTENT & SAFE:
 *   - Acts ONLY on a live pane whose `agent` is null and `agent_session` is null
 *     (a bare shell). A pane that already has an agent is skipped — so a second
 *     run, or a run on an already-populated session, is a no-op.
 *   - Never closes / splits / creates panes; never sends input to a pane that
 *     already has an agent. Purely additive relaunch into empty shells.
 *   - --dry-run prints the exact pane+command without touching anything.
 *
 * SOURCE OF TRUTH: read fresh each run — live `pane list` for the current panes.
 * For the desired agent bindings we MERGE two sources, snapshot-first:
 *   1. the newest archived snapshot (~/.local/state/herdr-resurrect/latest.json)
 *   2. the live session.json
 * Why snapshot-first: when an agent exits CLEANLY herdr immediately scrubs its
 * agent_session from session.json (verified 2026-07-02). On a real power-off the
 * agents are SIGKILLed so session.json keeps the binding — but the interval
 * snapshot, captured while the agent was alive, is the robust record either way.
 * We union both by (workspace,tab) so nothing is missed. --from-snapshot forces
 * snapshot-only (used by the reboot test where session.json was scrubbed).
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const HOME = homedir();
const HERDR = join(HOME, '.local/bin/herdr');
const SESSION_JSON = join(HOME, '.config/herdr/session.json');
const LATEST_SNAP = join(HOME, '.local/state/herdr-resurrect/latest.json');

const DRY = process.argv.includes('--dry-run');
const FROM_SNAPSHOT = process.argv.includes('--from-snapshot');
const VERBOSE = process.argv.includes('--verbose') || DRY;

function log(...a) { console.log('[herdr-restore]', ...a); }
function vlog(...a) { if (VERBOSE) console.log('[herdr-restore]', ...a); }

function herdr(args, { json = false } = {}) {
  const raw = execFileSync(HERDR, args, { encoding: 'utf8', timeout: 20000 });
  return json ? JSON.parse(raw) : raw;
}

function readJson(path, pick) {
  if (!existsSync(path)) return null;
  try { const d = JSON.parse(readFileSync(path, 'utf8')); return pick ? pick(d) : d; }
  catch { return null; }
}

// Pull desired agent bindings out of one session-topology object into a map
// keyed by `${wsId}::${tabIdx}` (the stable, restart-invariant coordinate).
function bindingsFrom(session) {
  const m = new Map();
  if (!session) return m;
  for (const w of session.workspaces || []) {
    (w.tabs || []).forEach((t, tabIdx) => {
      for (const p of Object.values(t.panes || {})) {
        const a = p.agent_session;
        if (a && a.agent && a.value && a.kind === 'id') {
          m.set(`${w.id}::${tabIdx}`, {
            wsId: w.id,
            wsLabel: w.custom_name || null,
            tabIdx,
            tabLabel: t.custom_name || null,
            cwd: p.cwd || w.identity_cwd,
            agent: a.agent,
            uuid: a.value,
          });
        }
      }
    });
  }
  return m;
}

// Merge snapshot (priority) + live session.json into one desired list.
function loadDesired() {
  const snap = readJson(LATEST_SNAP, (d) => d.session);
  const live = FROM_SNAPSHOT ? null : readJson(SESSION_JSON);
  const merged = new Map();
  // session.json first (lower priority), then snapshot overwrites — snapshot wins.
  for (const [k, v] of bindingsFrom(live)) merged.set(k, v);
  for (const [k, v] of bindingsFrom(snap)) merged.set(k, v);
  return [...merged.values()];
}

// Live panes grouped by workspace, tabs ordered by their numeric tab_id suffix.
function loadLive() {
  const panes = herdr(['pane', 'list'], { json: true }).result.panes;
  // group panes by workspace_id -> tab_id -> [panes]
  const byWs = new Map();
  for (const p of panes) {
    const ws = p.workspace_id;
    if (!byWs.has(ws)) byWs.set(ws, new Map());
    const byTab = byWs.get(ws);
    if (!byTab.has(p.tab_id)) byTab.set(p.tab_id, []);
    byTab.get(p.tab_id).push(p);
  }
  // For each ws, produce an ordered tab list.
  const out = new Map();
  for (const [ws, byTab] of byWs) {
    const tabIds = [...byTab.keys()].sort((a, b) => {
      const na = parseInt(a.split(':')[1] || '0', 10);
      const nb = parseInt(b.split(':')[1] || '0', 10);
      return na - nb;
    });
    out.set(ws, tabIds.map((tid) => ({ tabId: tid, panes: byTab.get(tid) })));
  }
  return out;
}

function isBareIdleShell(p) {
  return !!p && !p.agent && !p.agent_session;
}

function resumeCmd(agent, uuid) {
  if (agent === 'claude') return `claude --resume ${uuid} --dangerously-skip-permissions`;
  if (agent === 'codex') return `codex resume ${uuid}`;
  return null;
}

function main() {
  if (!existsSync(HERDR)) { console.error('herdr binary missing'); process.exit(2); }

  const want = loadDesired();
  if (want.length === 0) { log('nothing to restore (no persisted agent sessions found)'); return; }

  let live;
  try { live = loadLive(); }
  catch (e) { console.error('[herdr-restore] cannot reach herdr server:', e.message); process.exit(3); }

  let restored = 0, skipped = 0, unmatched = 0;

  for (const d of want) {
    const liveTabs = live.get(d.wsId);
    if (!liveTabs) { unmatched++; vlog(`UNMATCHED workspace ${d.wsId} (${d.wsLabel}) for ${d.agent}:${d.uuid}`); continue; }

    // Match tab: by label first, else positional index.
    let liveTab = null;
    if (d.tabLabel) {
      liveTab = liveTabs.find((lt) => lt.panes.some((p) => p.label === d.tabLabel));
    }
    if (!liveTab) liveTab = liveTabs[d.tabIdx] || null;
    if (!liveTab) { unmatched++; vlog(`UNMATCHED tab idx=${d.tabIdx} (${d.tabLabel}) in ws ${d.wsId}`); continue; }

    // Prefer a bare shell whose cwd matches; else any bare shell in the tab.
    let target = liveTab.panes.find((p) => isBareIdleShell(p) && p.cwd === d.cwd)
      || liveTab.panes.find((p) => isBareIdleShell(p));

    if (!target) {
      skipped++;
      vlog(`SKIP ${d.agent}:${d.uuid} — no bare shell in tab '${d.tabLabel || d.tabIdx}' (agent already running)`);
      continue;
    }

    const cmd = resumeCmd(d.agent, d.uuid);
    if (!cmd) { unmatched++; continue; }

    if (DRY) { log(`DRY: pane ${target.pane_id} (cwd=${target.cwd}) <= ${cmd}`); restored++; continue; }

    herdr(['pane', 'run', target.pane_id, cmd]);
    log(`RESTORED ${d.agent} in pane ${target.pane_id} (cwd=${target.cwd}) session=${d.uuid}`);
    restored++;
  }

  log(`done: ${restored} restored, ${skipped} skipped (already alive), ${unmatched} unmatched.`);
}

main();
