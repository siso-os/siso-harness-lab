# mcp-registries notes (2026-10-14)

Budget used: about 36 tool calls. Rows: 29 in rows/mcp-registries.jsonl (target was 30+; short by one).

## Blocked or not fetched (not in rows)
- mcpservers.org: HTTP 403.
- mcp-get (github.com/mcp-get/mcp-get): HTTP 404.
- github/github-mcp-registry: HTTP 404.
- Kong mcp-registry: HTTP 404.
- cursor.directory/mcp: HTTP 429.
- studiomeyer.io roundup: HTTP 403 (covered from search snippet, row 029).
- lobehub.com/mcp and mcp.run: redirected; followed to market.lobehub.com and turbomcp.ai (mcp.run redirect not followed; turbomcp.ai not fetched).
- Invariant mcp-scan repo: requested URL returned snyk/agent-scan content instead.

## Counts disagree across sources (treat as unverified)
- MCP Market: 49,358 on page vs "10,000+ across 23 categories" in a roundup.
- Smithery: 26,582+ on page vs 7,000-8,000 in a roundup.
- MCP.Directory: 2,303 stat vs "3,000+" header.
- Zapier actions: 30,000+ (FAQ) vs 66,000+ (page).
- Official registry: API returned metadata.count 100 on a limit=100 page; no grand total exposed.

## Trust and ranking patterns (for the synthesis)
- Scored: Glama (A-F grades for license, quality, maintenance); Snyk agent-scan (risk indicators, scanner not directory).
- Review rubric: Cline marketplace (adoption, credibility, maturity, security); Docker mcp-registry (PR review, signed builds).
- Provenance and namespace proof: official registry (GitHub OAuth or DNS challenge); ToolHive (signs servers).
- Popularity-only ranking: Smithery usage, Apify popularity score, LobeHub installCount, mcp.so and MCP.Directory "most installed" with no method stated.
- No stated vetting: mcp.so, Cursor marketplace, PulseMCP (submissions paused at fetch time).

## Gaps still open
- Real per-directory trust scanners beyond Glama and Snyk (e.g. Socket, Invariant, MCP scoring sites) were not searched.
- Gateways beyond ContextForge, Microsoft, ToolHive, MetaMCP and Klavis (Kong, Obot, Lunar, Portkey) not fetched.
- Hosting platforms beyond Cloudflare, Smithery, Pipedream, Zapier not fetched (e.g. Vercel, Railway, Fly).
- Current counts for OpenTools, Klavis hosted catalog, and Cline marketplace size are not on their pages.
