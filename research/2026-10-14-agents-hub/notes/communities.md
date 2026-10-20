# communities slice, 2026-10-14

Rows: rows/communities.jsonl (80 rows: 35 awesome-lists, 14 subreddit/Discord/newsletter/conference/YouTube sites, 16 HN threads, 15 X handles). All verified:null.

## What was pulled
- Awesome lists: gh search repos, with star counts from the same call (Oct 2026). Hub/directory sites (chatmcp/mcpso, toolsdk registry) excluded per scope. Zero-star "awesome-ai-coding-agents" clones skipped as noise.
- Subreddit counts: GummySearch comparison table (r/ClaudeCode page, updated 1 Oct 2026) and the r/LocalLLaMA GummySearch page (30 Sep 2026); TheHiveIndex for r/ClaudeAI (1.1M, 20 Jul 2026). Reddit itself was blocked (curl and WebFetch), so r/mcp, r/AI_Agents and r/ChatGPTCoding have NO count.
- HN: hn.algolia.com API (tags=story). Points and comment counts are from the API at run time.
- Discord: claude.com/community for the official Claude Developer Discord invite. No member count is published. Cursor and MCP Discords are from Discord listing sites (approximate).
- Newsletters: Latent Space (secondary-source figures, Aug-Sep 2026); Ben's Bites (self-reported, inconsistent 115k-150k); Simon Willison (sponsor-gated, no count); Pragmatic Engineer (paywalled, no count).
- Conference: AI Engineer World's Fair 2026 (already happened, 28 Jun-2 Jul, SF).

## Gaps (not solved)
1. X follower rankings: no source ranked people by followers, and X blocks scraping from this run. The 15 person rows are handles from memory or cited pages, unverified on X, with no follower counts. Needs the xsearch skill or a live X session to rank them.
2. Reddit counts for r/mcp, r/AI_Agents, r/ChatGPTCoding: Reddit is blocked here. Try GummySearch pages, or Reddit about.json from an unblocked machine.
3. Official Anthropic Discord member count and the official MCP Discord owner: not found.
4. Pragmatic Engineer and Simon Willison subscriber counts: not published.
5. YouTube: no verified subscriber counts for IndyDevDan, Matt Pocock or AI Explained. Only @aidotengineer has a figure.
6. HN coverage is a search sample, not a full crawl.

## Quality flags
- The r/ClaudeCode 14k figure from an older GummySearch page looks stale, so 446k is used.
- Matt Pocock's skills repo star count conflicts across sources (58.5k in May, 160k+ later). Not used as a row number.
- The "Claude Code source leak via npm map" HN thread (2,095 pts) is included for engagement and because it bears on harness trust.
