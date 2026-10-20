# 10-community: what heavy Claude Code users report cutting weekly-limit burn (2026-10-14)

Scope: 21 rows in 10-community.jsonl. About 15 searches and 2 fetches. Official docs are included as anchors; the rest are community or secondary. Community evidence is thin: no Reddit or HN thread was reachable through search, and most numbers come from SEO guides.

Top 5 tactics, strongest evidence first:
1. Clear between unrelated tasks and default to Sonnet (or Haiku for mechanical work); reserve Opus for hard reasoning. Official docs call this the highest-impact habit; Opus-burn reports (1.5-3x vs 4.6, Reddit via botmonster) back it.
2. Set effort deliberately; do not accept the xhigh or high default for simple work. Opus 4.7 default-effort complaints (Cursor forum, Towards AI test) are anecdotal; the official doc confirms thinking bills as output tokens.
3. Defer or disable MCP servers and check /context and /usage attribution. Official docs say tool definitions are deferred by default and /usage shows per-MCP-server share; no measured saving number.
4. Subagents isolate verbose output but are not free: their requests count toward the plan, agent teams run about 7x (official), and parallel fan-out hit caps in about half the time of sequential work (DEV, anecdotal).
5. Keep CLAUDE.md under 200 lines and move workflow text into skills and hooks. Official guidance; the 91.9 percent and 20-43 percent figures are single-test blog claims (low).

Still missing: a measured /clear-plus-handoff vs /compact comparison, a per-model weekly-limit ratio with a dated source, ccusage-based community data, and a fetched Reddit thread with a dated claim. Official Max-usage help page was not fetched directly; its 225/900 message figures come from a search excerpt.
