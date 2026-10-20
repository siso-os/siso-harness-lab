#!/usr/bin/env node
// slow-bg: PreToolUse hook on Bash. A command that is known to take minutes (a whole-disk du/find, a bulk `heavy --`
// job, a build, an install, a deploy, a clone, a browser test run) started in the foreground is switched to
// run_in_background, with no extra turn (Shaan, 17 Oct: a refusal to rerun "sounds like a waste of tokens").
// Why: in 6 h on 17 Oct, main chats made 1,418 Bash calls and waited 171 min on them; 38 calls over a minute were
// 94 min of that, and only 47 calls (3%) ran in the background (/tmp/cmdtime2.py over ~/.claude*/projects). Shaan,
// 17 Oct: "they always get stuck behind it".
// Heredoc bodies and quoted text are ignored, so a script or message that mentions a build is not moved.
// Sub-agents are left alone (they return one answer, so they wait anyway). `# fg` anywhere in the command, or
// SLOW_BG=0, skips it. Returns updatedInput without a permissionDecision; any error prints nothing.
export const SLOW = [
  /\bheavy --(?:\s|$)/, // bulk class; `heavy --class quick --` does not match
  /\bdu\b[^|;&]*\s(?:~|\$HOME|\/|\/Users\/[\w.-]+|~\/SISO_Workspace|~\/Library)\/?(?=\s|$|[|;&)])/,
  /\bfind\s+(?:~|\$HOME|\/|\/Users\/[\w.-]+|~\/Library)\/?(?=\s|$)/,
  /\b(?:npm|pnpm|yarn|bun)(?: run)? build\b/, /\b(?:vp|next|vite) build\b/, /\b(?:docker|cargo) build\b/, /\bxcodebuild\b/,
  /\b(?:npm|pnpm|yarn|bun) (?:install|i|ci|add)\b/, /\bbrew (?:install|upgrade|reinstall)\b/,
  /\bwrangler (?:pages )?deploy\b/, /\bvercel\b.*--prod\b/, /(?:^|[\s/])deploy[\w-]*\.sh\b/,
  /\bplaywright test\b/, /\bgit clone\b/, /\bstorage-map\.py\b/, /\bestate backup run\b/,
];

// The command as the shell runs it: heredoc bodies and quoted strings blanked.
export function bare(cmd) {
  let c = String(cmd);
  c = c.replace(/<<-?\s*(['"]?)(\w+)\1[^\n]*\n[\s\S]*?\n\s*\2(?=\s|$)/g, "<<HEREDOC");
  return c.replace(/'[^']*'/g, "''").replace(/"(?:[^"\\]|\\.)*"/g, '""');
}

export function slow(cmd) {
  const c = String(cmd);
  if (/#\s*fg\b/.test(c)) return null;
  const b = bare(c);
  const hit = SLOW.find(re => re.test(b));
  return hit ? b.match(hit)[0].trim() : null;
}

async function main() {
  if (process.env.SLOW_BG === "0") return;
  let raw = "";
  for await (const c of process.stdin) raw += c;
  const input = JSON.parse(raw);
  if (input.agent_id || input.tool_name !== "Bash" || input.tool_input?.run_in_background) return;
  const hit = slow(input.tool_input?.command ?? "");
  if (!hit) return;
  process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse",
    updatedInput: { ...input.tool_input, run_in_background: true },
    additionalContext: `slow-bg moved "${hit}" to the background; do the next independent step, you are woken when it ends.` } }));
}

if (import.meta.url === `file://${process.argv[1]}`) main().catch(() => {});
