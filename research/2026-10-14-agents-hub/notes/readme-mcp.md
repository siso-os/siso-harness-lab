# readme-mcp slice notes (2026-10-14)

Input: notes/readme-mcp.list (40 repos). README heads read for 12 relevant repos (#3, #6, #8, #10, #12, #14, #16, #18, #19, #30, #36, #39, #40, so 13 with #40); the other six (#1, #2, #13, #17, #29, #33) were judged from the list description plus homepage. Homepage, stars, license and last push came from the GitHub API for all 19. Install commands grepped for context7, codebase-memory-mcp, serena, gemini-cli, chrome-devtools-mcp, n8n-mcp, fastapi_mcp, fastmcp, python-sdk.

Relevant (read): #3 awesome-mcp-servers, #6 context7, #8 chrome-devtools-mcp, #10 codebase-memory-mcp, #12 github-mcp-server, #14 serena, #16 fastmcp, #18 python-sdk, #19 n8n-mcp, #30 typescript-sdk, #36 fastapi_mcp, #39 apify-mcp-server, #40 tyk, #1 n8n, #2 gemini-cli, #17 activepieces, #13 mcp-for-blender, #29 unity-mcp, #33 ida-pro-mcp.

Noise: the other 21 (worldmonitor, Scrapling, TrendRadar, nanobot, UI-TARS, gpt-researcher, MaxKB, FunASR, Douyin API, nuclear, mcp-for-beginners, trigger.dev, xiaohongshu-mcp, docker-android, OpenMetadata, nightingale, XHS-Downloader, hexstrike-ai, QuantDinger, nginx-ui, holaOS). Several were judged from the list description only and are marked "unverified" in the row note. nanobot, MaxKB and holaOS could hold an MCP layer; a second look is worth one README read each if the hub covers agent platforms.

Distribution patterns seen (for the hub's packaging question):
- Skill-first plus MCP from one installer command: context7 (`npx ctx7 setup`), codebase-memory-mcp (`curl ... install.sh | bash`, which writes MCP entries, hooks and skills into 45 agent surfaces).
- Vendor-hosted remote MCP, OAuth, URL-only config: github-mcp-server (api.githubcopilot.com/mcp), apify (mcp.apify.com, /sse removed).
- Explicit anti-pattern: serena's README says do not install via an MCP or plugin marketplace; use `uv tool install -p 3.13 serena-agent`.
- Plugin-store channel: ida-pro-mcp via the Hex-Rays plugin store.
- Catalog of MCP wrappers: activepieces (about 400 MCP servers from its piece library).
- Gateway product: tyk MCP gateway, a governance layer rather than a server.

Caveats: star counts are from the sweep (snapshot 2026-10-14). The Context7 and Serena install steps came from README greps, not full reads. The Apify and n8n-mcp hosted pricing was not verified beyond what the READMEs state. Verified fields are null by design.
