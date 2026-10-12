# agent-boot.sh — sourced by the Claude launchers after context-cap.sh. A lean boot for herdr agents (STACK-OPT item 4,
# 2 Oct 2026; Shaan 14:35: boot context by task, loaded on demand). Adds to the args claude gets:
#   --settings config/agent-boot.json   Artifact tool off (Shaan: never a claude.ai artifact), skills unused in 14 days
#                                       listed by name only (still invocable; regenerate with scripts/boot-profile.py)
#   --no-chrome                         agents browse with camofox, never Shaan's Chrome
#   --plugin-dir <agent-base>/stack/plugin  the role agents (always, when present; SISO_STACK_PLUGIN= overrides or empties it)
# and exports ENABLE_CLAUDEAI_MCP_SERVERS=false (claude.ai connectors: Docs, Gmail, Drive, ... unused by agents).
# SISO_FULL_BOOT=1 skips all of it; an explicit --chrome or --settings from the caller wins over ours.
siso_agent_boot() {
  # The SISO stack plugin (role agents siso:worker, siso:specker, siso:reviewer) from the Agent Base repo, for every launch, lean
  # or full (native-agents step 2). It is there once Agent Base is deployed with it (merge 5b67386); until then nothing is added.
  local plugin=${SISO_STACK_PLUGIN-$HOME/SISO_Workspace/SISO_Agency/apps/siso-internal-labs/siso-internal-labs-agent-base/stack/plugin}
  [[ -n $plugin && -f $plugin/.claude-plugin/plugin.json ]] && SISO_ARGS=(--plugin-dir "$plugin" ${SISO_ARGS[@]+"${SISO_ARGS[@]}"})
  [[ ${SISO_FULL_BOOT:-} == 1 ]] && return 0
  local here a chrome=1 settings=1
  here=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)
  for a in ${SISO_ARGS[@]+"${SISO_ARGS[@]}"}; do
    case $a in --chrome|--no-chrome) chrome=0 ;; --settings|--settings=*) settings=0 ;; esac
  done
  ((settings)) && [[ -f $here/config/agent-boot.json ]] && SISO_ARGS=(--settings "$here/config/agent-boot.json" ${SISO_ARGS[@]+"${SISO_ARGS[@]}"})
  ((chrome)) && SISO_ARGS=(--no-chrome ${SISO_ARGS[@]+"${SISO_ARGS[@]}"})
  export ENABLE_CLAUDEAI_MCP_SERVERS=${ENABLE_CLAUDEAI_MCP_SERVERS:-false}
}
