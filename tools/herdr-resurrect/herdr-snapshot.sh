#!/bin/zsh
# herdr-snapshot.sh — thin launchd wrapper for herdr-snapshot.mjs.
set -u
export HOME="${HOME:-$(eval echo ~"$(id -un)")}"
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/node@22/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
NODE="$(command -v node || echo /opt/homebrew/opt/node@22/bin/node)"
SNAP="$HOME/SISO_Workspace/SISO_Agents/siso-harness-lab/tools/herdr-resurrect/herdr-snapshot.mjs"
# No-op quietly if herdr isn't running (socket absent) — nothing to snapshot.
[[ -S "$HOME/.config/herdr/herdr.sock" ]] || exit 0
"$NODE" "$SNAP" >> /tmp/herdr-resurrect-snapshot.log 2>&1
