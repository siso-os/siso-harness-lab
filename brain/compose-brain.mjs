#!/usr/bin/env node
// Compose the shared agent brain into each tool's flat instruction file.
// ONE canonical core (WORKING-WITH-SHAAN.core.md) + the estate router (estate.md) + a per-tool shell
// -> the file the tool actually reads. Run after editing any of them. --check = dry-run (CI-friendly).
//
//   node compose-brain.mjs            # lint the estate router, then write every target
//   node compose-brain.mjs --check    # exit 1 if a target is stale or the router points at something missing
//
// Targets are NEVER hand-edited — they carry a GENERATED header pointing back here.
// Codex target: native Codex loads ~/.codex/AGENTS.md (proved with `codex debug prompt-input`,
// 2026-09-23). The earlier ~/.codex/instructions.md target was composed for months but never loaded.

import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const here = path.dirname(fileURLToPath(import.meta.url));
const HOME = homedir();
const CORE = path.join(here, "WORKING-WITH-SHAAN.core.md");
const ESTATE = path.join(here, "estate.md");

const TARGETS = [
  { tool: "claude", shell: path.join(here, "claude.shell.md"), out: path.join(HOME, ".claude/CLAUDE.md"), maxShellBytes: 900 }, // +200: compact instructions (Anthropic: CLAUDE.md steers compaction), 12 Oct
  { tool: "codex", shell: path.join(here, "codex.shell.md"), out: path.join(HOME, ".codex/AGENTS.md"), maxShellBytes: 700 },
  // omp (oh-my-pi) loads ~/.omp/agent/AGENTS.md as global context (marker-tested 2026-09-23); it reads
  // neither ~/.claude/CLAUDE.md nor ~/.codex/AGENTS.md. Its skills come from ~/.claude/skills.
  { tool: "omp", shell: path.join(here, "omp.shell.md"), out: path.join(HOME, ".omp/agent/AGENTS.md"), maxShellBytes: 400 },
];

const MAX_CORE_BYTES = 2500; // 4 Oct (Elon pass): each composed file stays under 4 KB
const MAX_ESTATE_BYTES = 900;

// Where each harness loads skills from. Claude Code: ~/.claude/skills. Codex: ~/.agents/skills + ~/.codex/skills.
const SKILL_ROOTS = {
  claude: [path.join(HOME, ".claude/skills")],
  codex: [path.join(HOME, ".agents/skills"), path.join(HOME, ".codex/skills")],
};
const WORKSPACE = path.join(HOME, "SISO_Workspace");

const check = process.argv.includes("--check");

function header(tool) {
  return `<!-- GENERATED FILE — DO NOT EDIT. Composed by SISO_Agents/siso-harness-lab/brain/compose-brain.mjs from WORKING-WITH-SHAAN.core.md + estate.md + ${tool}.shell.md. Edit those, then re-run compose-brain.mjs. -->\n\n`;
}

function compose(tool, shellPath) {
  const core = readFileSync(CORE, "utf8").trimEnd();
  const estate = readFileSync(ESTATE, "utf8").trimEnd();
  const shell = readFileSync(shellPath, "utf8").trimEnd();
  return `${header(tool)}${core}\n\n${estate}\n\n${shell}\n`;
}

function hasSkill(roots, name) {
  return roots.some((r) => existsSync(path.join(r, name, "SKILL.md")));
}

function onPath(cmd) {
  try {
    execFileSync("/bin/zsh", ["-lc", `command -v -- ${cmd}`], { stdio: "ignore" });
    return true;
  } catch {
    return false;
  }
}

// Every backticked reference in the estate router must resolve for every harness that loads it:
// a bare-word skill must be installed for Claude AND Codex; a bare-word non-skill must be a command
// on the login PATH; a path (~/... or rooted at a top-level workspace entry) must exist.
function lintEstate(text) {
  const errors = [];
  const topLevel = new Set(readdirSync(WORKSPACE));
  for (const [, span] of text.matchAll(/`([^`]+)`/g)) {
    const words = span.trim().split(/\s+/);
    if (words.length === 1 && /^[a-z0-9][a-z0-9-]*$/.test(span)) {
      const inClaude = hasSkill(SKILL_ROOTS.claude, span);
      const inCodex = hasSkill(SKILL_ROOTS.codex, span);
      if (inClaude || inCodex) {
        if (!inClaude) errors.push(`skill \`${span}\` is not in ~/.claude/skills (Claude Code cannot load it)`);
        if (!inCodex) errors.push(`skill \`${span}\` is not in ~/.agents/skills or ~/.codex/skills (Codex cannot load it)`);
      } else if (!onPath(span)) {
        errors.push(`\`${span}\` is neither an installed skill nor a command on the login PATH`);
      }
      continue;
    }
    for (const raw of words) {
      const w = raw.replace(/^["'(]+|["',;:)]+$/g, "");
      if (w.includes("<") || w.includes("$")) continue;
      let p = null;
      if (w.startsWith("~/")) p = path.join(HOME, w.slice(2));
      else if (w.includes("/") && topLevel.has(w.split("/")[0])) p = path.join(WORKSPACE, w);
      if (p && !existsSync(p)) errors.push(`path \`${w}\` does not exist`);
    }
  }
  return errors;
}

// Consumer half (--check only): ask Codex which skills it actually lists at turn 1. A skill can exist
// on disk and still be dropped by the loader (e.g. a symlinked SKILL.md file), which the lint above
// cannot see. Claude Code has no offline prompt dump, so its half stays the file check.
function codexListedSkills() {
  try {
    const out = execFileSync("codex", ["debug", "prompt-input"], { cwd: HOME, encoding: "utf8", timeout: 60000, stdio: ["ignore", "pipe", "ignore"] });
    return new Set([...out.matchAll(/\\n- ([a-z0-9_:-]+): /g)].map((m) => m[1]));
  } catch {
    return null;
  }
}

function routerSkills(text) {
  return [...text.matchAll(/`([a-z0-9][a-z0-9-]*)`/g)].map((m) => m[1])
    .filter((s) => hasSkill(SKILL_ROOTS.claude, s) || hasSkill(SKILL_ROOTS.codex, s));
}

const coreBytes = statSync(CORE).size;
if (coreBytes > MAX_CORE_BYTES) {
  console.error(`CORE OVER BUDGET: ${coreBytes} bytes (max ${MAX_CORE_BYTES})`);
  process.exit(1);
}
const estateText = readFileSync(ESTATE, "utf8");
if (Buffer.byteLength(estateText) > MAX_ESTATE_BYTES) {
  console.error(`ESTATE OVER BUDGET: ${Buffer.byteLength(estateText)} bytes (max ${MAX_ESTATE_BYTES})`);
  process.exit(1);
}
const lint = lintEstate(estateText);
if (lint.length) {
  console.error(`ESTATE ROUTER BROKEN (${lint.length}): fix the reference or install the skill for both harnesses`);
  for (const e of lint) console.error(`  - ${e}`);
  process.exit(1);
}
console.log("estate router: every skill, command and path resolves for Claude and Codex");
if (check) {
  const listed = codexListedSkills();
  if (!listed) {
    console.log("codex consumer check: skipped (codex debug prompt-input unavailable)");
  } else {
    const missing = [...new Set(routerSkills(estateText))].filter((s) => !listed.has(s));
    if (missing.length) {
      console.error(`CODEX DOES NOT LIST ${missing.length} router skill(s): ${missing.join(", ")} (installed but dropped by its loader)`);
      process.exit(1);
    }
    console.log(`codex consumer check: all ${new Set(routerSkills(estateText)).size} router skills listed at turn 1`);
  }
}

let stale = 0;
for (const { tool, shell, out, maxShellBytes } of TARGETS) {
  if (!existsSync(shell)) { console.error(`MISSING shell: ${shell}`); process.exit(1); }
  const shellBytes = statSync(shell).size;
  if (shellBytes > maxShellBytes) {
    console.error(`SHELL OVER BUDGET: ${tool} ${shellBytes} bytes (max ${maxShellBytes})`);
    process.exit(1);
  }
  const composed = compose(tool, shell);
  const current = existsSync(out) ? readFileSync(out, "utf8") : null;
  if (current === composed) {
    console.log(`up-to-date  ${tool} -> ${out}`);
    continue;
  }
  if (check) {
    console.error(`STALE       ${tool} -> ${out}  (run compose-brain.mjs to regenerate)`);
    stale += 1;
    continue;
  }
  writeFileSync(out, composed);
  console.log(`wrote       ${tool} -> ${out}  (${Buffer.byteLength(composed)} bytes)`);
}

if (check && stale > 0) process.exit(1);
