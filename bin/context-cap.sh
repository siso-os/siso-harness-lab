# context-cap.sh — sourced by the Claude launchers (claude-siso, claude-siso-3). Picks this agent's context cap from
# the caps scale and exports it for hooks/context-ping.mjs: the heads-up at cap - lead (CONTEXT_PING_AT), the compact
# ask at the cap. The percentage line moves to 80% so a 1M window doesn't ping at 35% (350k) before an owner's cap.
# Shaan, 2 Oct ~14:25: "it should always be a scale, and we can pick where on the scale, up to like 500k".
#
#   siso_context_cap "$@"; exec claude "${SISO_ARGS[@]}"
# Reads -n/--name NAME (kept for claude) and --cap TIER|N (removed: claude doesn't know it). N is tokens: 450000 or 450k.
# Caps file: $SISO_CONTEXT_CAPS, else ~/.config/siso/context-caps.json, else this repo's config/context-caps.json.
# An explicit CONTEXT_PING_AT in the environment wins over everything.
# --task ID, --alloc usd:N|credits:N|tokens:N and --chain opus:spec,luna:build,opus:review (removed too) export
# SISO_TASK / SISO_ALLOC / SISO_CHAIN: the token ledger's stamp
# (so-020); the context-ping hook writes it to ~/.local/state/siso-task/marks.jsonl on the session's first tool call.
siso_context_cap() {
  local name="" cap="" here
  SISO_ARGS=()
  while (($#)); do
    case $1 in
      --cap) cap=${2:-}; shift; (($#)) && shift ;;
      --cap=*) cap=${1#*=}; shift ;;
      --task) export SISO_TASK=${2:-}; shift; (($#)) && shift ;;
      --task=*) export SISO_TASK=${1#*=}; shift ;;
      --alloc) export SISO_ALLOC=${2:-}; shift; (($#)) && shift ;;
      --chain) export SISO_CHAIN=${2:-}; shift; (($#)) && shift ;;
      --chain=*) export SISO_CHAIN=${1#*=}; shift ;;
      --alloc=*) export SISO_ALLOC=${1#*=}; shift ;;
      -n|--name) name=${2:-}; SISO_ARGS+=("$1"); shift; (($#)) && { SISO_ARGS+=("$1"); shift; } ;;
      --name=*) name=${1#*=}; SISO_ARGS+=("$1"); shift ;;
      *) SISO_ARGS+=("$1"); shift ;;
    esac
  done
  [[ -n ${CONTEXT_PING_AT:-} ]] && return 0
  here=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)
  local file=${SISO_CONTEXT_CAPS:-$HOME/.config/siso/context-caps.json}
  [[ -f $file ]] || file=$here/config/context-caps.json
  local py='
import json, re, sys
f, name, cap = sys.argv[1:4]
c = json.load(open(f))
tiers = c["tiers"]
def tokens(v):
    v = str(v).strip().lower()
    if v in tiers: return v, int(tiers[v])
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(k?)", v)
    if not m: raise SystemExit(1)
    return "custom", int(float(m[1]) * (1000 if m[2] else 1))
agents = {k.upper(): v for k, v in c.get("agents", {}).items()}
pick = cap or agents.get(name.upper())
tier, n = tokens(pick or c.get("default", "220k"))
if not pick and tier == "custom": tier = "default"
lead = int(c.get("lead", 100000))
print(tier, n, max(n - lead, 0), lead)
'
  local out
  out=$(python3 -c "$py" "$file" "$name" "$cap" 2>/dev/null) || return 0
  local lead
  read -r SISO_CONTEXT_TIER SISO_CONTEXT_CAP CONTEXT_PING_AT lead <<<"$out"
  export SISO_CONTEXT_TIER SISO_CONTEXT_CAP CONTEXT_PING_AT
  [[ -n $name ]] && export SISO_AGENT_NAME=$name   # the hook re-reads the caps file by this name, live
  [[ -n $cap ]] && export SISO_CONTEXT_SOURCE=cap  # an explicit --cap is never overridden by the file
  export CONTEXT_PING_PCT=${CONTEXT_PING_PCT:-80} CONTEXT_PING_STEP=${CONTEXT_PING_STEP:-$lead}  # the ask lands at the cap
  # Hard cap (Shaan, 3 Oct ~17:00: "that nine hundred k thing shouldn't have happened"): Claude Code auto-compacts at the cap.
  # The percentage is of the model's window; SISO's Claude agents run 1M-context Opus, so 300k = 30%. SISO_CONTEXT_WINDOW
  # overrides it for a 200k model; SISO_CONTEXT_HARD=0 goes back to ping-only.
  if [[ ${SISO_CONTEXT_HARD:-1} != 0 ]]; then
    local win=${SISO_CONTEXT_WINDOW:-1000000} pct
    pct=$(( (SISO_CONTEXT_CAP * 100 + win - 1) / win )); ((pct > 95)) && pct=95; ((pct < 10)) && pct=10
    export CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=$pct
  fi
}
