#!/usr/bin/env node
// lane-model: PreToolUse hook on SISO Code's delegate_task (mcp__t3-code__delegate_task). The owner (Opus) decides which
// model a lane runs; this hook only makes sure it decided. A lane that names no model inherits the owner's, so every
// HALO lane on 15-16 Oct ran Opus without anyone choosing it. When a Claude call names no model, the hook adds a
// reminder to pick one per task and changes nothing else. Shaan, 16 Oct: "Opus should be deciding what gets Sonnet or
// Haikus ... it's not about spending less, it's about more done per token".
// LANE_MODEL=force restores the first version (rewrite an unnamed or Opus lane to Sonnet 5.5, `[opus]` keeps Opus).
// Returns no permissionDecision, so the normal permission flow still applies. Never blocks; any error prints nothing.
// LANE_MODEL=0 turns it off.
export const SONNET = "claude-sonnet-5-5";

const NUDGE = "lane-model: this call names no model, so the lane runs on yours. Pick per task: Opus for design, debugging and anything " +
  "where a wrong turn is costly; claude-sonnet-5-5 for a well-specified build with a check; claude-haiku-5-5 for reading and checks. " +
  "Set target.model.";

export function needsChoice(ti) {
  const t = ti?.target ?? {};
  if (t.providerInstanceId && !/claude/i.test(String(t.providerInstanceId))) return false;
  return !t.model;
}

export function retarget(ti) {
  const t = ti?.target ?? {};
  if (t.providerInstanceId && !/claude/i.test(String(t.providerInstanceId))) return null;
  if (t.model && !/opus/i.test(String(t.model))) return null;
  if (/\[opus\]/i.test(`${ti?.task ?? ""} ${ti?.title ?? ""}`)) return null;
  return { ...ti, target: { ...t, model: SONNET } };
}

async function main() {
  const mode = process.env.LANE_MODEL;
  if (mode === "0") return;
  let raw = "";
  for await (const c of process.stdin) raw += c;
  const input = JSON.parse(raw);
  if (!/delegate_task$/.test(String(input.tool_name ?? ""))) return;
  const out = { hookEventName: "PreToolUse" };
  if (mode === "force") {
    const u = retarget(input.tool_input);
    if (!u) return;
    out.updatedInput = u;
    out.additionalContext = "lane-model: this lane starts on claude-sonnet-5-5. Put [opus] in the task to keep Opus.";
  } else if (needsChoice(input.tool_input)) out.additionalContext = NUDGE;
  else return;
  process.stdout.write(JSON.stringify({ hookSpecificOutput: out }));
}

if (import.meta.url === `file://${process.argv[1]}`) main().catch(() => {});
