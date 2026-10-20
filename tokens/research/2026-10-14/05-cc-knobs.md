# 05 Claude Code knobs: 5 best non-invasive ways to watch or cut tokens

1. Watch per turn: add a statusline script reading `context_window.used_percentage` and `cost.total_cost_usd` from stdin (read-only, no model tokens). https://code.claude.com/docs/en/statusline
2. Watch per tool: enable OTEL (`CLAUDE_CODE_ENABLE_TELEMETRY=1`) and chart `claude_code.tool_result` `tool_result_size_bytes` by `tool_name` to find the biggest outputs. https://code.claude.com/docs/en/monitoring-usage
3. Stop idle waste: set `CLAUDE_CODE_GOAL_CHECKIN_MINUTES=0` and `crossSessionInbound: hold` so idle sessions do not re-send full context. https://code.claude.com/docs/en/costs
4. Cap tool output: lower `BASH_MAX_OUTPUT_LENGTH` (default 30000 chars) and `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` (default 25000) only where lines are not needed; this is a cut, so check it does not hide failures. https://code.claude.com/docs/en/env-vars
5. Route simple subagent work to Haiku with `model: haiku` in the subagent definition, and watch `/usage` Prompt cache line for misses. https://code.claude.com/docs/en/costs

Caveats: `MAX_MCP_OUTPUT_TOKENS` and `/cost` were requested but not confirmed on the pages read; `CLAUDE_CODE_SUBAGENT_MODEL` precedence unconfirmed. The changelog fetch was noisy (mentions of hook names not on the docs), so changelog-only rows are marked.
