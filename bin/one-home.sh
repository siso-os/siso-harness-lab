# one-home.sh — sourced by the SISO Claude launchers (claude-siso, claude-siso-3) after they set their own CLAUDE_CONFIG_DIR.
#
# Native-agents step 4 (siso-harness-lab/.agents/plans/2026-10-02-native-agents.md; Shaan, 2 Oct 21:30: "all of these sim
# links in wrong folders are hella confusing"). With SISO_ONE_HOME=1 every SISO session runs from ONE config folder, ~/.claude
# (one projects/, one sessions/ registry, so SendMessage names resolve across accounts), and the account comes from that
# account's long-lived token (claude-token-login; Keychain item siso-claude-oauth/<account>) instead of a per-login folder.
# ~/.claude's own Keychain login is Fahmy's (plain `claude`): a SISO launch never falls back to it. No token = refuse.
# On by default for claude-siso (fuzeheritage) since 2 Oct, opt-in for claude-siso-3; SISO_ONE_HOME=0|1 always wins.
# Streaming seats stay on their own login until A0 clears them (after Oracle production, 3 Oct ~18:00).
SISO_ONE_HOME_EXEMPT='^(STREAMING-CLAUDE|STREAM-.*|OPS-BUILD)$'
siso_one_home() {  # $1 = the account's Keychain name (fuzeheritage | lordsisodia); $2 = on|off when SISO_ONE_HOME is unset
  local want=${SISO_ONE_HOME:-}
  if [[ -z $want ]]; then
    want=0
    [[ ${2:-off} == on ]] && want=1
    [[ $want == 1 && ${SISO_AGENT_NAME:-} =~ $SISO_ONE_HOME_EXEMPT ]] && want=0
  fi
  [[ $want == 1 ]] || return 0
  local tok
  tok=$(security find-generic-password -s siso-claude-oauth -a "$1" -w 2>/dev/null) || tok=
  if [[ -z $tok ]]; then
    echo "one-home: no token for $1; run: claude-token-login $1   (refusing: ~/.claude's own login is Fahmy's)" >&2
    exit 3
  fi
  unset CLAUDE_CONFIG_DIR
  export CLAUDE_CODE_OAUTH_TOKEN=$tok SISO_ACCOUNT=$1
}

# Plain `claude` must stay fuzeheritage (Shaan 3 Oct): an update rewrites ~/.local/bin/claude as a symlink to the new version,
# which would put plain claude back on ~/.claude's own login (Fahmy's). Every SISO launch puts the wrapper back.
siso_claude_wrapper_heal() {
  local w; w="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)/claude"
  [ -x "$w" ] || return 0
  case "$(readlink "$HOME/.local/bin/claude" 2>/dev/null)" in  # only the updater's own form: a symlink into versions/
    "$HOME/.local/share/claude/versions/"*) ln -sfn "$w" "$HOME/.local/bin/claude" 2>/dev/null || true ;;
  esac
}
siso_claude_wrapper_heal
