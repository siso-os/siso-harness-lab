#!/usr/bin/env node
// spend-glance.mjs — Claude Code PreToolUse hook on Agent|Task: show the budget at the moment an agent spends big.
//
// Shaan, 6 Oct ~23:30: "it shouldn't have a hard cap ... he should have checked the usage allocation available and figured
// out and reasoned". ADR 0001 (siso-agent-zero docs/adr): look at the budget first, cost it (tokens ~ calls x context),
// pick the shape. This hook puts those numbers in front of the agent as it launches a sub-agent. It never blocks,
// never caps and never decides: it only adds text (additionalContext), and it is silent on any error.
//
// Measured (FLEET-COST, 7 Oct; scripts/window-spend.py over 6 Oct 19:09-00:09): the window cost $279 at list prices;
// OPERATOR-UI's 6 research sub-agents were $88 of it (32%), each growing to 250-770k context over 100-200 calls,
// because a sub-agent re-reads everything it has read on every call. UI-HUB's 15 short sub-agents were $12.
//
// Reads: STATE/burn/samples.jsonl (context-ping, this login), the Agent Base host records (live chats and their context),
// the load average and swap. Env (tests): CONTEXT_PING_STATE, AB_HOSTS_DIR, CLAUDE_CONFIG_DIR, SPEND_GLANCE_NOW.

import { readdirSync, readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { homedir, loadavg, cpus } from "node:os";
import path from "node:path";

const readJson = f => { try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; } };

// The newest five-hour reading for this login and its rise per hour over the last hour (same reset only).
export function window5h(samplesFile, profile, now) {
  let rows = [];
  try {
    const text = readFileSync(samplesFile, "utf8");
    const cut = Math.max(0, text.length - 200_000); // the last ~200 KB; a cut first line is dropped
    rows = text.slice(cut).split("\n").slice(cut ? 1 : 0).map(l => { try { return JSON.parse(l); } catch { return null; } })
      .filter(r => r && r.profile === profile && r.h5 != null);
  } catch { return null; }
  if (!rows.length) return null;
  const at = r => Date.parse(r.at);
  const reset = v => v == null ? null : Math.round((typeof v === "number" ? (v > 1e11 ? v / 1000 : v) : Date.parse(v) / 1000) / 60) * 60;
  const last = rows[rows.length - 1];
  if (now - at(last) > 30 * 60_000) return { pct: last.h5, stale: true };
  const seg = rows.filter(r => reset(r.h5_reset) === reset(last.h5_reset) && now - at(r) <= 60 * 60_000);
  const span = (at(seg[seg.length - 1]) - at(seg[0])) / 3_600_000;
  const perH = seg.length >= 2 && span >= 5 / 60 ? (seg[seg.length - 1].h5 - seg[0].h5) / span : null;
  const resetsAt = reset(last.h5_reset);
  return { pct: last.h5, perH, resetsIn: resetsAt ? Math.max(0, resetsAt * 1000 - now) : null, stale: false };
}

// Live hosted chats: Claude ones with their context, newest record per session.
export function liveChats(hostsDir, now) {
  const out = [];
  try {
    for (const f of readdirSync(hostsDir)) {
      if (!f.endsWith(".json")) continue;
      const h = readJson(path.join(hostsDir, f));
      if (!h?.ctx || h.child !== "running" || now - (h.updatedAt || 0) > 6 * 3_600_000) continue;
      out.push({ name: h.name, model: String(h.model || ""), used: h.ctx.used || 0, state: h.state, effort: h.effort || null });
    }
  } catch {}
  return out;
}

function swapPct() {
  try {
    const s = execFileSync("sysctl", ["-n", "vm.swapusage"], { encoding: "utf8", timeout: 2000 });
    const t = Number(/total = ([\d.]+)M/.exec(s)?.[1]), u = Number(/used = ([\d.]+)M/.exec(s)?.[1]);
    return t ? Math.round((100 * u) / t) : null;
  } catch { return null; }
}

const k = n => `${Math.round(n / 1000)}k`;
const hm = ms => `${Math.floor(ms / 3_600_000)}h${String(Math.round((ms % 3_600_000) / 60_000)).padStart(2, "0")}`;

export function glance(env = process.env, now = Number(env.SPEND_GLANCE_NOW) || Date.now(), load = loadavg()[0], swap = swapPct()) {
  const state = env.CONTEXT_PING_STATE || path.join(homedir(), ".local", "state", "context-ping");
  const hosts = env.AB_HOSTS_DIR || path.join(homedir(), ".local", "state", "agent-base", "hosts");
  const profile = env.CLAUDE_CONFIG_DIR || path.join(homedir(), ".claude");
  const w = window5h(path.join(state, "burn", "samples.jsonl"), profile, now);
  const chats = liveChats(hosts, now);
  const opus = chats.filter(c => /opus/i.test(c.model));
  const working = opus.filter(c => c.state === "working");
  const lines = [];
  if (w && !w.stale) {
    const rate = w.perH != null ? `, rising ${w.perH.toFixed(1)}%/h` : "";
    const left = w.perH > 0 ? `, full in ~${hm(((100 - w.pct) / w.perH) * 3_600_000)}` : "";
    lines.push(`Budget before you launch: 5-hour window ${Math.round(w.pct)}% used${rate}${left}${w.resetsIn != null ? `, resets in ${hm(w.resetsIn)}` : ""}.`);
  } else {
    lines.push(`Budget before you launch: no fresh 5-hour reading${w ? ` (last ${Math.round(w.pct)}%)` : ""}; check curl -s http://127.0.0.1:5401/api/usage.`);
  }
  if (opus.length) {
    lines.push(`${opus.length} Opus chats live (${working.length} working, ${k(opus.reduce((s, c) => s + c.used, 0))} context between them).`);
  }
  if (Number.isFinite(load)) lines.push(`Laptop: load ${load.toFixed(1)} on ${cpus().length} cores${swap != null ? `, swap ${swap}% used` : ""}.`);
  lines.push("Cost it: tokens ~ calls x context, and a sub-agent re-reads everything it has read on every call " +
    "(6 Oct: six research sub-agents grew to 250-770k each and cost a third of the window). Script the fetching, batch " +
    "related items into one sub-agent, ask for a compact return, and tell it to stop and report before ~150k context. " +
    "Your call, not a cap (ADR 0001).");
  return lines.join(" ");
}

if (import.meta.url === `file://${process.argv[1]}`) {
  let raw = "";
  process.stdin.on("data", c => (raw += c));
  process.stdin.on("end", () => {
    try {
      const input = JSON.parse(raw || "{}");
      // Workflow too (Shaan, 12 Oct: "sometimes opus workflows are needed, it's just they should be justified ... given the
      // compute constraints"): workflow agents default to Haiku 5.5 (settings CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL); one that
      // asks for Opus should say why, against these numbers. HALO's six-agent Opus workflow was ~45% of a 4 h window.
      if (/^(Agent|Task|Workflow)$/.test(input.tool_name || "")) {
        const why = input.tool_name === "Workflow" ? "\nWorkflow agents run on Haiku 5.5 unless an agent asks for model 'opus'; give each Opus agent a one-line reason (judgement Haiku can't do, priority) and keep the count small." : "";
        process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", additionalContext: glance() + why } }));
      }
    } catch {}
    process.exit(0);
  });
}
