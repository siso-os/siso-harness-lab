# marketplaces-r2 notes (2026-10-14)

Gap-fill for the plugin-marketplaces slice. 30 rows in rows/marketplaces-r2.jsonl (market2-001 to market2-030). Round-1 URLs were not repeated.

## Strongest finds
- Vibe Index and claudemarket.ai show the two trust signals the round-1 sites lack: per-listing security scan status (Vibe Index, Cisco scan) and install-count ranking (claudemarket.ai, sponsored cards interleaved).
- Arcade.dev: per-user OAuth with a consent URL, policy checks before each call, and a per-call audit trail.
- Pipedream Connect and Composio: managed-auth catalogs with auth type per app (Pipedream: 3,223 apps, 14,957 tools; Composio: 1,607 toolkits).

## Dead or blocked (not written as rows, or written with a caveat)
- Langflow store (langflow.org/store): 404. Row uses docs page.
- Flowise marketplace (flowiseai.com/marketplaces): 404. Row uses docs and DeepWiki mirrors.
- Google Gemini Enterprise blog (introducing agent gallery): 404. Row uses Google Cloud docs.
- agent.ai: redirects to builderpack.com, a different product. Dropped.
- ccplugins.dev: parked domain (GoDaddy sale page). Dropped.
- mcphub.tools: DNS failure. mcphub.io: 402. Dropped.
- mcp-get: no npm or search hit for the name. mcpbar and mcp-pm used as CLI-installer stand-ins.
- mcpservers.org: 403 to fetcher. Kept as row 017 with URL pattern only; counts unverified.
- Kong: fetch was empty; row built from the press release.
- Zapier counts: the landing page disagrees with itself (9,000+ apps; 66,000+ triggers and actions; 30,000+ actions in the FAQ). Counters are garbled; do not quote without a live check.
- Toolhouse: integrations conflict (1,000+ vs 5,000+ on the same page).
- Claude Market (claudemarket.ai): hero 23,000+, FAQ 13,870+ MCP and 4,384+ skills; inconsistent.
- Gemini Gems: no gallery or marketplace found; only the Gem manager help pages.
- AWS AgentCore Gateway listing rules: only a third-party guide; unverified.

## Open gaps
- Install and auth details for MCP Market, buildwithclaude and claudepluginhub listing pages (only the directory pages were read).
- A browser pass on mcpservers.org and mcpmarket.com for real counts and sort order.
- Langflow and Flowise official counts: none found.
- GPT Store current categories (only the Jan 2024 launch post was read).
- Hugging Face Spaces MCP count: the Spaces search page returned 400.
- Arcade toolkit list page: 404; counts come from secondary sources.
