#!/bin/bash
# after-compact: SessionStart hook (matcher "compact"). Whatever this prints goes into the compacted context, so an
# owner wakes from a compaction with its repo's newest HANDOFF entry, git state and last commits instead of
# re-reading them. Anthropic's recipe: code.claude.com/docs/en/hooks-guide "Re-inject context after compaction".
# Shaan, 12 Oct: "I'm sure there's stuff around auto-compacting ... you don't have any improvements to tell me".
# Never blocks, never fails the session: every step is best-effort and the output is capped.
input=$(cat 2>/dev/null)
cwd=$(printf '%s' "$input" | /usr/bin/python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("cwd",""))
except Exception: print("")' 2>/dev/null)
[ -d "$cwd" ] || cwd=$PWD
cd "$cwd" 2>/dev/null || exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || root=$cwd
{
  echo "After compaction (hook after-compact): state of $root"
  if git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
    echo; echo "## git: $(git -C "$root" branch --show-current 2>/dev/null)"
    git -C "$root" log --oneline -5 2>/dev/null
    n=$(git -C "$root" status --short 2>/dev/null | wc -l | tr -d ' ')
    echo "$n uncommitted paths (git status before you stage; others may own some)"
  fi
  h="$root/.agents/HANDOFF.md"
  if [ -f "$h" ]; then
    echo; echo "## Top of .agents/HANDOFF.md (newest first; read the rest if you need it)"
    head -30 "$h" | cut -c1-600
  fi
} | head -c 6000
exit 0
