#!/usr/bin/env node
// test-filter: PreToolUse hook on Bash. A bare test run in a main chat (npm/pnpm/yarn/bun test, node --test, a
// tests/*.mjs file, vitest, jest, pytest, cargo test, go test; optionally after `cd X &&` or `heavy --`) is rewritten
// so the chat sees only the end of the output when it passes, and the failing lines plus the end when it fails. The
// full log goes to a file named on the last line; the exit code is kept.
// Why: Bash output carried on every later call was 15% of 72 h list-price spend (scripts/token-where.py, 12 Oct), and
// a passing suite's 150 "ok" lines are carried at Opus rates until the next compaction. Idea: rvaniaaa's Opus 5.5 cost
// guide step 6. Anything with a pipe, redirect or chain is left alone (the author is already shaping the output).
// Returns updatedInput without a permissionDecision, so the normal permission flow still applies.
// Never blocks; any error prints nothing. TEST_FILTER=0 turns it off; `# full` anywhere in the command skips it.
export const TEST = /^(?:cd [^;&|<>]+ && )?(?:heavy -- )?(?:(?:npm|pnpm|yarn|bun)(?: run)? test(?::[\w:-]+)?|(?:npx |pnpm exec |pnpm )?(?:vitest|jest|mocha)(?: run)?|node --test|node (?:\S+\/)?(?:tests?|__tests__)\/\S+\.m?[jt]s|node \S+\.test\.m?[jt]s|(?:python3? -m )?pytest|cargo test|go test)(?:\s|$)/;
const MESSY = /[|;<>`]|&&|\$\(|&\s*$|# full/;

export function wrap(cmd) {
  const c = cmd.trim();
  if (!TEST.test(c) || MESSY.test(c.replace(/^cd [^;&|<>]+ && /, ""))) return null;
  const q = c.replace(/'/g, `'\\''`);
  return `__log=$(mktemp -t test-out); bash -c '${q}' >"$__log" 2>&1; __rc=$?; ` +
    `if [ $__rc -eq 0 ]; then tail -n 6 "$__log"; else ` +
    `grep -n -i -E -A 4 'fail|error|not ok|✗|✖|assert|expected|traceback|panic' "$__log" | head -n 80; echo '--- last lines'; tail -n 15 "$__log"; fi; ` +
    `echo "[test-filter: $(wc -l < "$__log" | tr -d ' ') lines, full log $__log, exit $__rc]"; (exit $__rc)`;
}

async function main() {
  if (process.env.TEST_FILTER === "0") return;
  let raw = "";
  for await (const c of process.stdin) raw += c;
  const input = JSON.parse(raw);
  if (input.agent_id || input.tool_name !== "Bash") return; // sub-agents run on Haiku and return short answers already
  const cmd = wrap(String(input.tool_input?.command ?? ""));
  if (!cmd) return;
  process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", updatedInput: { ...input.tool_input, command: cmd } } }));
}

if (import.meta.url === `file://${process.argv[1]}`) main().catch(() => {});
