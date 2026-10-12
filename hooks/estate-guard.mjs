#!/usr/bin/env node
// estate-guard: PreToolUse hook (Claude Code and Codex) that stops the three moves that made the estate messy
// (siso-estate goal A9; Shaan, 24 Sep: "make the estate beautiful" and keep it that way).
//
//   1. a new folder or file at the top of ~/SISO_Workspace that plan/layout.json does not allow
//   2. a new visible folder or file directly in ~ that plan/home-zones.json does not list
//   3. `git worktree add` anywhere but ~/SISO_Workspace/_data/worktrees/<repo>/<lane>
//
// It blocks (exit 2, the reason on stderr, which the agent reads) only when it is sure; anything it cannot parse passes.
// Escape hatch for a deliberate exception: put `# estate-guard: allow` in the command, or ESTATE_GUARD=off.
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { isAbsolute, join, normalize, resolve } from 'node:path';

const HOME = homedir();
const WS = join(HOME, 'SISO_Workspace');
const PLAN = join(WS, 'SISO_Agents', 'siso-estate', 'plan');

function readJSON(p) { try { return JSON.parse(readFileSync(p, 'utf8')); } catch { return null; } }

function allowed() {
  const layout = readJSON(join(PLAN, 'layout.json'));
  const zones = readJSON(join(PLAN, 'home-zones.json'));
  if (!layout || !zones) return null; // cannot tell: never block
  return {
    root: new Set(layout.root_allowed || []),
    home: new Set(Object.values(zones.zones || {}).flatMap((z) => z.entries || [])),
  };
}

function expand(p, cwd) {
  let s = p.replace(/^["']|["']$/g, '');
  s = s.replace(/^~(?=\/|$)/, HOME).replace(/^\$HOME(?=\/|$)/, HOME).replace(/^\$\{HOME\}(?=\/|$)/, HOME);
  if (s.includes('$') || s.includes('`') || s.includes('*')) return null; // a variable or glob: cannot know
  return normalize(isAbsolute(s) ? s : resolve(cwd || HOME, s));
}

function verdict(target, a) {
  if (!target || existsSync(target)) return null; // only new things
  const rel = target.startsWith(WS + '/') ? target.slice(WS.length + 1) : null;
  if (rel !== null) {
    const top = rel.split('/')[0];
    if (!a.root.has(top) && !existsSync(join(WS, top)))
      return `"${top}" would be a new entry at the top of ~/SISO_Workspace, which only holds the districts in plan/layout.json. ` +
        'Find its home with `estate where <words>` (a product: SISO_Agency/apps/, client work: SISO_Agency/clients/<brand>/, ' +
        "HALO's: SISO_Agency/partners/halo/, agent tooling: SISO_Agents/, others' code: _reference/, runtime data: _data/).";
    return null;
  }
  if (target.startsWith(HOME + '/')) {
    const top = target.slice(HOME.length + 1).split('/')[0];
    if (!top.startsWith('.') && !a.home.has(top) && !existsSync(join(HOME, top)))
      return `"~/${top}" would be a new folder in your home folder. Work belongs in ~/SISO_Workspace (run \`estate where <words>\`); ` +
        'scratch goes in `mktemp -d "${TMPDIR%/}/.siso-ephemeral-<task>.XXXXXX"`.';
  }
  return null;
}

function worktreeVerdict(target) {
  if (!target) return null;
  if (target.startsWith(join(WS, '_data', 'worktrees') + '/')) return null;
  return `a worktree at ${target.replace(HOME, '~')}: every worktree lives in ~/SISO_Workspace/_data/worktrees/<repo>/<lane> ` +
    '(siso-estate ADR 0006), never beside or inside the repo, never in /tmp.';
}

function words(cmd) {
  return (cmd.match(/"[^"]*"|'[^']*'|[^\s;&|()]+|[;&|()]+/g) || []);
}

function check(cmd, cwd, a) {
  if (/#\s*estate-guard:\s*allow/.test(cmd)) return null;
  const w = words(cmd);
  const SEP = /^(;|&&|\|\||\||\(|\)|&|then|do|else|sudo|command|env|nohup|time)$/;
  for (let i = 0; i < w.length; i++) {
    const t = w[i];
    if (i > 0 && !SEP.test(w[i - 1])) continue; // only a word in command position runs
    if (t === 'git') {
      let j = i + 1;
      while (j < w.length && /^-/.test(w[j])) j += ['-C', '-c', '--git-dir', '--work-tree'].includes(w[j]) ? 2 : 1;
      if (w[j] === 'worktree' && w[j + 1] === 'add') {
        const args = [];
        for (let k = j + 2; k < w.length && !/^[;&|()]+$/.test(w[k]); k++) {
          if (['-b', '-B', '--reason'].includes(w[k])) { k++; continue; }
          if (w[k].startsWith('-')) continue;
          args.push(w[k]);
        }
        const gi = w.indexOf('-C', i);
        const base = gi > i && gi < j ? expand(w[gi + 1], cwd) : cwd;
        const v = worktreeVerdict(args[0] ? expand(args[0], base || cwd) : null);
        if (v) return v;
      }
      continue;
    }
    if (t === 'mkdir' || t === 'touch') {
      for (let j = i + 1; j < w.length && !/^[;&|()]+$/.test(w[j]); j++) {
        if (w[j].startsWith('-')) continue;
        const v = verdict(expand(w[j], cwd), a);
        if (v) return v;
      }
    }
  }
  return null;
}

async function main() {
  if (process.env.ESTATE_GUARD === 'off') return 0;
  let raw = '';
  for await (const c of process.stdin) raw += c;
  let p;
  try { p = JSON.parse(raw); } catch { return 0; }
  const a = allowed();
  if (!a) return 0;
  const input = p.tool_input || p.input || {};
  const cwd = p.cwd || input.workdir || process.cwd();
  let reason = null;
  const cmd = Array.isArray(input.command) ? input.command.join(' ') : (input.command || input.cmd || '');
  if (typeof cmd === 'string' && cmd) reason = check(cmd, cwd, a);
  const file = input.file_path || input.path;
  if (!reason && typeof file === 'string' && /^(Write|Edit|MultiEdit|NotebookEdit)$/.test(p.tool_name || ''))
    reason = verdict(expand(file, cwd), a);
  if (!reason) return 0;
  process.stderr.write(`estate-guard blocked this: ${reason} If this is a deliberate exception, add \`# estate-guard: allow\` to the command.\n`);
  return 2;
}

main().then((code) => process.exit(code)).catch(() => process.exit(0));
