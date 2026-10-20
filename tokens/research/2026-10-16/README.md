# Claude Code token and plan-usage levers, research 2026-10-16

Scope: the five questions in the brief (output filters, system-floor levers, model mix, cache TTL and thinking, usage meters). Budget was about 15 searches and fetches. Rows are in `rows.jsonl` (one per finding). Every claim below is tagged as official (Anthropic docs or pricing page), vendor-reported (tool README), or third-party (blog or issue).

## Settled (official docs, read 2026-10-16)

- Cache TTL: `CLAUDE_CODE_PROMPT_CACHE_TTL=5m|1h` (only these values). It overrides `ENABLE_PROMPT_CACHING_1H`. `FORCE_PROMPT_CACHING_5M=1` pins 5m. `DISABLE_PROMPT_CACHING` turns caching off.
- Thinking: `CLAUDE_CODE_EFFORT_LEVEL` (low to max, auto). `MAX_THINKING_TOKENS` only applies to fixed-budget models. `CLAUDE_CODE_DISABLE_THINKING=1` does not turn thinking off on Opus 5.5, Sonnet 5.5, Haiku 5.5 or Fable.
- Output caps: `BASH_MAX_OUTPUT_LENGTH` (default 30000 chars, max 150000); `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS` (default 25,000).
- Tool surface: `CLAUDE_CODE_DISABLE_WEB_FETCH`, `_EXPLORE_PLAN_AGENTS`, `_BACKGROUND_TASKS`, `_CRON`, `_ARTIFACT`, `_WORKFLOWS`, `_FAST_MODE`, `_ADVISOR_TOOL`. MCP tool definitions are deferred by default (costs page). `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` caps description size.
- Advisor: `advisorModel` setting, `--advisor <model>`, `/advisor <model>`. Advisor must rank at or above the main model. Sonnet 5.5 main + Opus 5 advisor is accepted. Opus 5.x main has no cheaper accepted advisor.
- Pricing per MTok (Opus 5.5 / Sonnet 5.5 / Haiku 5.5): input $4 / $2 / $0.10; 5m write $5 / $2.50 / $0.125; 1h write $8 / $4 / $0.20; hit $0.20 / $0.10 / $0.01; output $20 / $10 / $0.50.
- Autocompact: `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` (1-100, lower only); `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (100k-1M).

## Not confirmed (do not rely on until checked on the installed version)

- `ENABLE_TOOL_SEARCH` values (auto, auto:N, true, false): third-party guide only. Official env-vars page excerpt did not reach that row.
- `ENABLE_PROMPT_CACHING_1H` actually taking effect for API-key users: a closed issue (claudeissues #49139) says it did not.
- rtk and context-mode savings: vendor README numbers, no independent benchmark found.

## Ranked levers for the measured spend ($437, 24h)

1. Output filter on noisy Bash results. The official pattern is a PreToolUse hook (costs page). rtk (83.5k stars, Apache-2.0 CLI, BUSL-1.1 for engine and proxy) is the packaged version. context-mode (29.8k stars, ELv2) covers MCP and file output too. Expected effect is on the tool-result share of cache reads and writes, not the system floor. Measure with ccusage before and after.
2. Worker lanes (41% of spend): route simple subagent work to `model: haiku` (costs page) and keep Opus for the advisor or main seat. Haiku 5.5 is $0.10 input, about 1/40 of Opus 5.5. Advisor pattern: Sonnet 5.5 executor ($2/$10) with Opus 5.5 advisor ($4/$20) halves the executor price. The Anthropic blog numbers use a Sonnet baseline, so they do not prove savings against an all-Opus fleet.
3. Cache TTL (30% of spend is 1h writes). 1h writes cost 1.6x 5m writes. Rough breakeven: 5m is cheaper only if the prefix gets rewritten fewer than about 1.6 times per hour. Test on a sample of seats with `FORCE_PROMPT_CACHING_5M=1` or `CLAUDE_CODE_PROMPT_CACHE_TTL=5m`, and read the /usage `Prompt cache (main)` line for misses.
4. Thinking (26% of spend is output incl. thinking): on Opus 5.5 use `CLAUDE_CODE_EFFORT_LEVEL` (medium or low for routine work). `MAX_THINKING_TOKENS` does nothing there.
5. System floor (about 43k tokens, 19% of cache reads): MCP servers are the main lever (`/mcp` to disable, `/context` to measure). CLAUDE.md under 200 lines, workflows moved to skills. Built-in disables are low-value unless a tool is unused. ENABLE_TOOL_SEARCH behavior is not confirmed here.

## Missing / next steps

- No measured quality-vs-cost study for Claude Code itself (only Anthropic's API blog, which uses Sonnet baselines).
- ENABLE_TOOL_SEARCH and FORCE_/ENABLE_ rows of the env-vars page were past the read window (about 100k chars read of 171k); a second read at offset 100000 would confirm them.
- No independent benchmark of rtk or context-mode; a 20-task A/B on one seat would give the real number.
- Advisor docs say the feature needs the Anthropic API and feature-flag fetching. Confirm the seat's auth path before counting on it.
