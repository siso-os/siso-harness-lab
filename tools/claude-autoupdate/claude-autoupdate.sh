#!/bin/bash
# claude-autoupdate: keep Claude Code on the newest release without anyone pressing anything (Shaan, 15 Oct: "how can you make
# sure it's updated ... so we don't have to do all these bullshits again"). Runs `claude update` every 4 hours from launchd
# (com.siso.claude-autoupdate). The `claude` launcher (siso-harness-lab/bin/claude) always execs the newest folder under
# ~/.local/share/claude/versions, so every new terminal and every new SISO Code agent turn picks the update up; running
# agents keep the version they started on. Log: ~/.local/state/claude-autoupdate.log.
export HOME="${HOME:-/Users/shaansisodia}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/bin:/bin"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.config/claude-siso-3}"
LOG="$HOME/.local/state/claude-autoupdate.log"
before=$(claude --version 2>/dev/null | awk '{print $1}')
out=$(claude update 2>&1 | tail -n 3 | tr '\n' ' ')
after=$(claude --version 2>/dev/null | awk '{print $1}')
echo "$(date '+%Y-%m-%d %H:%M:%S %z') ${before:-?} -> ${after:-?} | $out" >> "$LOG"
