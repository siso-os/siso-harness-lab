# AGENTS-HUB research run, 14 Oct 2026 (hub-research v1 pilot)

## Goal (Shaan, 14 Oct ~11:15)
"world standing research on pretty much 80% of every single skills hub ... anything related to agent skills agent
playbooks harnesses ... subagent structures, like literally anything ... white papers ... mainly I want to find like all
of the website URLs of other sites which are like skill repositories ... a bunch of different sites we can pick their UI
base and figure out how these guys show it." We are the layer above everything that exists.

## Coverage target
- Sites (skill hubs, MCP registries, plugin marketplaces, prompt/rule directories): ~80% of those a practitioner would
  name; falsifier: a fresh Haiku searching blind in round 2 finds >20% sites not already in merged.jsonl.
- GitHub: every skill/MCP/plugin/harness repo >=50 stars from the sweep; READMEs read for the top ~60.
- Papers/vendor docs: the canonical ones (Anthropic, OpenAI, Google) plus the top ~20 papers on skills/tools/agents.
- Merge target: 40 rows per directed slice.

## Already held (reuse, do not re-find)
See `notes/estate-reuse.md` (filled by the reuse Haiku). Known incumbents seed: official MCP registry, Smithery, Glama,
mcp.so, skills.sh, Claude Code plugin marketplaces, n8n templates; harness-rob (100 findings, 5 harnesses);
siso-skills-hub registry (52 skills).

## Method
0. Reuse check (1 Haiku) + GitHub sweep (gh-sweep.py, 4 slices, 49 phrasings) + blind map (3 Haikus): in parallel.
1. Revise slices below from the blind map.
2. Directed slices: ~10 Haikus in one message.
3. Merge, read COVERAGE.md, re-send at LIGHT slices.
4. Verify: 2 checkers. 5. INDEX.md + themes.json.

## Slices (draft; revised after the blind map — see "Revision" below)
| # | slice | objective | sources | out of scope | budget | falsifier |
|---|---|---|---|---|---|---|
| 1 | skill-sites | every skills hub/directory/marketplace site | web search, awesome lists, HN/Reddit/X mentions | MCP-only sites | 40 | a known site (skills.sh, claude-plugins.dev, skillsmp) missing |
| 2 | github-skills-readme | read READMEs of top skill repos from sweep | rows/github-skills.jsonl | sweep itself | 40 | top-10 by stars unread |
| 3 | mcp-registries | every MCP registry/directory/gateway | web, modelcontextprotocol org | single MCP servers | 40 | official/Smithery/Glama/mcp.so/PulseMCP missing |
| 4 | plugin-marketplaces | Claude Code plugins, Cursor, ChatGPT apps, Gemini ext, VS Code agent ext, workflow-template galleries | web, gh | MCP registries | 40 | Anthropic's official marketplace missing |
| 5 | harnesses | coding/general agent harnesses and how they structure skills/sub-agents | web, docs, gh | model benchmarks | 40 | <15 harnesses |
| 6 | orchestration | sub-agent and multi-agent structures, frameworks, patterns | web, docs, papers | single-agent harness features | 40 | no orchestrator-worker refs |
| 7 | playbooks-prompts | playbooks, prompt banks, system-prompt leaks, rules files, context-engineering guides | web, gh | skills hubs | 40 | no leaked-system-prompts repo |
| 8 | papers-evals | white papers and evals on skills, tool use, agents, memory | arXiv, Semantic Scholar, benchmark sites | vendor blogs | 40 | <20 papers |
| 9 | vendors | what Anthropic, OpenAI, Google (and MS, Meta, xAI) publish about agents/skills | official docs/blogs/cookbooks | third-party commentary | 40 | Agent Skills spec post missing |
| 10 | communities | awesome-lists, subreddits, Discords, newsletters, X people, YouTube | web, x, reddit | — | 40 | <10 awesome lists |

## Revision after the blind map (14 Oct, 10:00)
Blind map: 113 rows. Blind-1 fetched no pages (snippets only), so site rows need fetch-confirmation. New categories it
surfaced: crawl-everything skill indexes, an install-telemetry leaderboard (skills.sh), paid/scanned skill stores,
per-harness rule hubs, trust grading (Glama A-F, Docker signed/SBOM, Anthropic Verified). Code search: 768 distinct
repos hold a SKILL.md in the first 1,000 hits (capped).
Final slices (11 directed + 2 README readers after the sweep):
| # | slice | objective | falsifier |
|---|---|---|---|
| 1 | skill-sites | fetch-confirm every skill index/leaderboard/store; real count, UI pattern, install cmd; find more | <25 confirmed sites |
| 2 | harness-hubs | per-harness extension hubs: Cursor, Windsurf, Copilot, Continue, Cline, Roo, Kilo, Amp, Kiro, Zed, Warp, Gemini ext, Codex plugins, Factory, JetBrains, OpenClaw | a harness with a hub but no row |
| 3 | mcp-registries | confirm + extend MCP registries, directories, gateways, hosting | <25 confirmed |
| 4 | plugin-marketplaces | Claude plugin dir + community marketplaces, ChatGPT apps, GPT store, VS Code agent plugins, workflow-template galleries | Anthropic marketplace or n8n missing |
| 5 | harnesses | >=25 harnesses and how each structures skills/sub-agents/hooks/memory | <25 |
| 6 | orchestration | multi-agent frameworks, SDKs, protocols (A2A), session orchestrators | no orchestrator-worker ref |
| 7 | playbooks-prompts | prompt banks, system-prompt leaks, spec-driven kits, method packs, context-eng guides | no spec kit |
| 8 | papers | white papers: skills, tool use, MCP security, memory, multi-agent failure, context engineering | <20 papers |
| 9 | evals | agent/tool/MCP benchmarks and leaderboards with live sites | <15 boards |
| 10 | vendors | Anthropic, OpenAI, Google, MS, AWS, Meta, xAI, Mistral, Vercel, Cloudflare | Agent Skills post missing |
| 11 | communities | awesome lists, subreddits, Discords, newsletters, X people, YouTube, HN | <10 awesome lists |
| 12 | readme-skills | READMEs of the top 30 skill/plugin repos from the sweep | top-10 unread |
| 13 | readme-mcp-harness | READMEs of the top 30 MCP/harness/subagent repos from the sweep | top-10 unread |
