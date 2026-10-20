# 04 Anthropic context-cost features (2026-10-14), top 5

1. Claude Code and the Agent SDK expose no switch for tool-result clearing; the only API path is the beta header context-management-2025-06-27 with body context_management (clear_tool_uses_20250919), and the SDK options table has no contextManagement field.
2. Cache TTL is the one lever SDK users can pull by env: ENABLE_PROMPT_CACHING_1H=1 or CLAUDE_CODE_PROMPT_CACHE_TTL=1h via options.env (1h write 2x base, read 0.1x; Opus 5.5 read 0.05x).
3. Opus 5.5 is $4 in / $5 write5m / $8 write1h / $0.20 hit / $20 out per MTok; Haiku 5.5 is $0.10 in up to 100k prompt tokens and 5x that above 100k (the only model with a long-context premium).
4. The 1M window is the default on Opus 5.5 and Haiku 5.5 with no beta header, so the SDK betas option (context-1m-2025-08-07) is only for retired Sonnet 4/4.5.
5. Compaction is beta under compact-2026-09-04; the SDK tool_runner has compact_before_next_turn(), but the mirror does not show Claude Code calling that API (it uses its own auto-compact, tuned by CLAUDE_CODE_AUTO_COMPACT_WINDOW).

Missing or unverified: token-efficient tool use (no doc page found in the mirror); live web pages only partly read (pricing fetch was too large, numbers taken from the local mirror, which matches); no check of whether Claude Code sends clear_tool_uses itself beyond the errors-page mention.
