#!/bin/zsh
# herdr-restore-on-login — poll-until-herdr-appears wrapper around herdr-restore.
#
# WHY A POLL, NOT RUN-ONCE-AT-LOGIN: there is no LaunchAgent that auto-starts the
# herdr server — Shaan opens herdr manually from his terminal, which may be
# seconds or many minutes after login. A single RunAtLoad shot would time out and
# miss him. So launchd runs THIS every 30s; it does nothing until herdr is up AND
# the restored panes are still bare shells, then relaunches the agents ONCE and
# drops a per-boot latch so it won't re-fire.
#
# Safe regardless: herdr-restore only injects into bare shells, so even without
# the latch a re-run is a no-op once agents are alive.

set -u
export HOME="${HOME:-$(eval echo ~"$(id -un)")}"
export PATH="/opt/homebrew/bin:/opt/homebrew/opt/node@22/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

HERDR="$HOME/.local/bin/herdr"
NODE="$(command -v node || echo /opt/homebrew/opt/node@22/bin/node)"
RESTORE="$HOME/SISO_Workspace/SISO_Agents/siso-harness-lab/tools/herdr-resurrect/herdr-restore.mjs"
SOCK="$HOME/.config/herdr/herdr.sock"
LOG="/tmp/herdr-resurrect.log"
LATCH_DIR="$HOME/.local/state/herdr-resurrect"
LATCH="$LATCH_DIR/.restored-this-boot"

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S') $*" >> "$LOG"; }
mkdir -p "$LATCH_DIR"

# Boot id = kernel boot time; changes every reboot, so the latch auto-resets.
BOOT_ID="$(sysctl -n kern.boottime 2>/dev/null | sed 's/[^0-9]//g' | head -c 20)"

# Already restored this boot? bail silently (the common case on every 30s tick).
if [[ -f "$LATCH" && "$(cat "$LATCH" 2>/dev/null)" == "$BOOT_ID" ]]; then
  exit 0
fi

# herdr not up yet? nothing to do this tick.
[[ -S "$SOCK" ]] || exit 0
"$HERDR" pane list >/dev/null 2>&1 || exit 0

# Give herdr a moment to finish spawning restored bare-shell panes.
sleep 5

# GUARD: how many desired-agent panes are still bare (eligible)? If zero, either
# the session was never populated this boot yet, or agents are already alive.
GUARD=$("$NODE" "$RESTORE" --dry-run 2>/dev/null | grep -c '^\[herdr-restore\] DRY:')

if [[ "$GUARD" -eq 0 ]]; then
  # Distinguish "no persisted agents at all" from "not yet restored". If herdr has
  # panes but none are bare-eligible AND at least one agent is already running, the
  # session is populated — latch so we stop polling this boot.
  ALIVE=$("$HERDR" pane list 2>/dev/null | "$NODE" -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const p=JSON.parse(s).result.panes;process.stdout.write(String(p.filter(x=>x.agent).length))}catch{process.stdout.write("0")}})')
  if [[ "${ALIVE:-0}" -gt 0 ]]; then
    echo "$BOOT_ID" > "$LATCH"
    log "session already populated ($ALIVE agents alive) — latched, no restore needed this boot."
  fi
  exit 0
fi

log "=== restore-on-login: $GUARD bare agent pane(s) eligible — restoring ==="
"$NODE" "$RESTORE" >> "$LOG" 2>&1
echo "$BOOT_ID" > "$LATCH"
log "restore complete; latched for this boot."
exit 0
