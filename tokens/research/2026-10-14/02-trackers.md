# Trackers and analyzers: top 5 ideas to steal (2026-10-14)

1. Read Claude Code's native OTel `api_request` and `token.usage` events instead of guessing from transcripts, and use `query_source` (main/subagent/auxiliary) and `skill.name`/`mcp_tool.name` for attribution. Source: https://code.claude.com/docs/en/monitoring-usage
2. Burn rate in tokens per minute from the last hour, with a projected time to limit and a depletion warning, as in Claude-Code-Usage-Monitor. Source: https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor
3. Name cold-cache waste by cause (idle gap vs session over 90 min) and price it in dollars, plus a what-if replay for model swap or cache TTL, as in ccmeter. Source: https://github.com/vnmoorthy/ccmeter
4. Use official rate-limit numbers from statusline when fresh, and label local estimates as estimates; infer a personal limit from the P90 of past 5h blocks instead of a fixed plan table. Source: https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor
5. Context-size gates that exit non-zero (`scan --max-total`, `--max-delta` in tokenscope) as a harness check on big contexts. Source: https://github.com/wartzar-bee/tokenscope

Still missing: no tracker found that attributes cost per file (tokenscope lists it only as roadmap). Star counts and last-commit dates were not verified for most repos, and the Grafana dashboard panels and the BurnRate formula were not opened. Excluded as generic observability SaaS: LangWatch.
