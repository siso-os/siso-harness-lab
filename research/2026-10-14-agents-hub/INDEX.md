# AGENTS-HUB: the map of everything that makes agents good (14 Oct 2026)

hub-research v1 pilot. Opus planned and judged; 30 Haiku runs (1 estate reuse, 3 blind, 11 directed, 3 README readers,
3 gap fillers, 1 renderer, 2 long-tail, 2 blind probes, 4 checkers) did the reading; scripts did the GitHub sweep, code-search census,
star checks and merge. Files: `PLAN.md`, `COVERAGE.md`, `SITES.md` (every website, grouped), `merged.jsonl` (13,030
rows), `rows/`, `notes/` (one per slice), `themes.json`.

## 1. The numbers
- **13,030 unique rows**: 12,392 GitHub repos (sweep with API star counts), 406 sites, 70 products, 62 lists, 48
  papers, 15 people.
- **400 distinct website URLs** in `SITES.md` (failed checks removed).
- **GitHub census** (`gh search code`, each query capped at 1,000 hits, so these are floors): 2,172 repos with a
  SKILL.md, 853 with `.claude-plugin/plugin.json`, 775 with a `.claude-plugin/marketplace.json`, 796 with
  `.claude/agents/*.md`. Repo sweep: 8,314 skill repos (631 with 1k+ stars), 1,949 MCP repos, 3,039 plugin and
  sub-agent repos.
- **Verification**: 405 Haiku-written rows re-opened (every row with a number or a "best" claim, plus 20% of the
  rest): 336 confirmed, 69 failed (about 21 of them unreadable). 206 star counts checked against the GitHub API: 202
  matched; the other 4 were stale undercounts. Ecosystem counts are marketing: homepages and secondary sources
  disagree by 2-10x (SkillsMP 425k to 3M; Skills Directory 194k vs 651,714 live). Never quote one without its date.
- **Coverage falsifier**: blind probe 1 found 37% new domains, so two long-tail Haikus ran; blind probe 2 then found
  ~14% new *directory* sites (32% new domains overall, mostly blog articles). That is under the 20% line, so collection
  stopped. Estimated coverage of directory sites: ~85%.

## 2. The map of the domain
1. **Standards** (the floor everyone builds on): the SKILL.md / Agent Skills spec (agentskills.io; Anthropic, OpenAI
   Codex/ChatGPT, Vercel, HF, Gemini all ship it), MCP and AGENTS.md (both under the Agentic AI Foundation since Dec
   2025, with goose), A2A 1.0 (agent to agent), ACP (editor to agent), AG-UI (agent to UI).
2. **Skill hubs** (~45 confirmed): install-telemetry leaderboards (skills.sh, the `npx skills add` de facto standard),
   crawl-everything indexes (SkillsMP, Skills Directory 651k, agentskill.sh 275k+, claude-plugins.dev, LobeHub),
   graded or curated stores (SkillHub S-D grades, ClaudSkills A-F OWASP scan, mdskills, Agensi paid 70/30, Vibe Index
   with Cisco scan status), plus China (agent-skills.cc, 63k).
3. **MCP registries** (~45): the official registry, Glama (97,619 servers, facet counts), Smithery, mcp.so, PulseMCP,
   mcptoplist (141,379), Docker MCP Catalog (signed, SBOM), Cline marketplace (written review rubric), ModelScope MCP
   square and Alibaba Bailian (China), plus gateways (ContextForge, Microsoft, ToolHive, MetaMCP, Tyk, Kong) and
   auth-managed tool platforms (Composio, Arcade, Pipedream Connect, Apify Store).
4. **Plugin marketplaces and agent stores** (~45): anthropics/claude-plugins-official (315 manifest entries),
   community marketplaces (claudemarketplaces, aitmpl, buildwithclaude, claudemarket.ai), the ChatGPT apps directory
   and Apps SDK (openai/skills deprecated for openai/plugins), Gemini CLI extensions, M365 Agent Store, AgentExchange,
   AWS AgentCore, Agent Garden, Dify Marketplace, n8n (10k+ templates), Zapier, Make.
5. **Per-harness hubs**: cursor.directory and the Cursor marketplace, Kiro Powers (76), ClawHub, Factory plugins
   (they accept Claude Code layouts), Copilot custom agents, Kilo modes, the Roo marketplace (archived), Continue hub
   (didn't resolve).
6. **Harnesses** (36 rows; comparison table in `notes/harnesses.md`): Claude Code, Codex, Gemini CLI (now Antigravity
   CLI for some tiers), Cursor, Windsurf (docs moved under Devin), Copilot agent, Devin, opencode, OpenHands, Roo,
   Kilo, Aider, Kiro, Amp, Zed, Jules, Junie, Factory, goose, Cline, Crush, Qwen Code. Each has its own name for the
   same unit: rules, steering, knowledge, playbooks, recipes, modes, powers, droids, skills.
7. **Orchestration** (43): SDKs (Claude Agent SDK, OpenAI Agents SDK, ADK, LangGraph, CrewAI, AG2, MS Agent Framework,
   Mastra, smolagents, Strands), session orchestrators (Conductor, claude-squad, ccmanager, uzi, Container Use,
   Sculptor, GitHub Agent HQ; Vibe Kanban is sunsetting and Crystal is deprecated), and named patterns
   (orchestrator-worker, handoff vs agent-as-tool, Ralph loop, broadcast-and-compare).
8. **Method packs and prompt banks** (34): obra/superpowers (299k stars, the biggest repo in the domain), github/spec-kit,
   BMAD, 12-factor agents, Kiro specs, Agent OS, wshobson/agents (one source compiled to 7+ harnesses),
   system-prompt archives (x1xhlol 144k), prompts.chat, fabric.
9. **Evals** (29): SWE-bench (Verified, Pro, Bash Only), Terminal-Bench 4.0 (ranks *agent + model*), HAL (cost vs
   accuracy, agent as the unit), Artificial Analysis coding agents, LMArena WebDev, tau2, BFCL, OSWorld, MCP-Universe,
   MCPMark, LiveMCPBench, METR horizons, SkillsBench.
10. **Papers** (48) and **vendors** (48): see sections 4 and 5.
11. **Communities** (80): 35 awesome-lists (awesome-mcp-servers 96k, awesome-claude-code 55.6k,
    awesome-agent-skills 35.7k), r/ClaudeAI ~1.2M, r/ClaudeCode ~446k, 16 HN threads, newsletters (Latent Space,
    Simon Willison).

## 3. Heavy and light
- **Heavy**: GitHub (12.4k repos plus the census), skill hubs, MCP registries, marketplaces, vendor guidance, papers,
  orchestration, awesome-lists. Enough to build a leaderboard from today.
- **Light**:
  - X people: the 15 handles are from memory, with no follower counts, because X blocked scraping.
  - Live leaderboard numbers: the boards render client-side, and HAL never rendered.
  - Reddit and Discord member counts.
  - Japanese, Korean and German ecosystems.
  - Primary reads of framework docs (Pydantic AI, Agno, Mastra, CrewAI).
  - The OpenAI guide PDF pp. 11-32.
  - Manus and Operator internals.
- **Harness-repo sweep** (re-run after the server restart): 2,668 repos in `rows/github-harness.jsonl`; the merge is
  now 15,168 unique rows. Its READMEs are not read yet.

## 4. Top picks, with reasons (all verified)
1. **skills.sh**: the distribution standard (`npx skills add owner/repo`), ranked by install telemetry, works across
   20 agents. Our installer should speak it, not compete with it.
2. **Glama**: the best directory UX at scale. It shows a count on every facet, a Remote/Local/Hybrid filter and
   license/quality/maintenance grades.
3. **anthropics/claude-plugins-official + the Agent Skills spec**: the canonical packaging. A plugin is skills + agents
   + hooks + MCP. Factory, OpenAI plugins and Gemini extensions have all converged on the same bundle.
4. **Terminal-Bench and HAL**: the only boards that rank the *harness* (agent + model) with cost. That is the shape SISO
   Bench needs.
5. **SkillsBench (2602.12670)** and **the 49-skill SWE study (2603.15401)**: curated skills add +16.2 pp and
   self-written skills add ~0. Most skills give no gain, and some cost up to 451% more tokens. This is the rating we
   should sell.
6. **Agent Skills in the Wild (2601.10338)** and **MCPTox (2508.14925)**: 26.1% of 31,132 skills have a vulnerability,
   and tool poisoning succeeds 72.8% of the time. Trust grading is the gap in the market.
7. **Anthropic engineering posts**: building effective agents, multi-agent research (+90.2%, ~15x tokens), context
   engineering, writing tools, Agent Skills, and harnesses for long-running agents. This is the doctrine our brain
   already follows.
8. **obra/superpowers, spec-kit, 12-factor agents, the Ralph loop**: the method packs people actually install.
9. **wshobson/agents**: one source compiled to 7+ harnesses. That is the cross-harness projection Skills Hub should
   copy.
10. **ClaudSkills, SkillHub and Vibe Index**: the only hubs that grade trust per listing (OWASP A-F, S-D with stated
    criteria, Cisco scan status).

## 5. Principles worth distilling (for the harvesting bank)
1. **Rate by measured gain.** Keep a skill only if its pass-rate delta is positive on real tasks; curated skills beat
   self-written ones (SkillsBench, 2603.15401). This is the leaderboard metric no hub has.
2. **Trust is code-level.** Treat every skill script and tool description like code you're installing: scan it,
   grade it, sign it (2601.10338, MCPTox, Docker, ClaudSkills). Scanners over-flag without repo context (46.8% down to
   0.52%), so grade with context.
3. **Progressive disclosure under a hard budget.** Load the name and description first, then the body, then files.
   Codex caps skill metadata at 2% of context, AGENTS.md at 32 KiB, and Claude Code caps tool output at 25k tokens.
4. **Simplest design first.** Write a function before an agent, and use multi-agent only for parallel, breadth-heavy
   work. All five vendors say this.
5. **Few, well-described, tested tools.** Retrieval, not execution, is the bottleneck at scale: retrieval errors cause
   about half of LiveMCPBench failures. Invest in tool search.
6. **Failures are system design.** MAST found 14 failure modes, most of them harness or protocol design, not the
   model. Audit the harness before swapping models.
7. **Verification closes the loop.** Give the agent a check it can run; long work needs an initializer, one feature
   per worker, and progress files plus git (Anthropic harness post, the Ralph loop).
8. **Improve context with deltas, not rewrites.** ACE playbooks with delta updates (+10.6%) and GEPA reflection beat RL
   with 35x fewer rollouts.
9. **One source, many harnesses.** Author once, project to Claude, Codex, Gemini, Cursor and the rest (wshobson,
   Factory, the cross-vendor plugin bundle).
10. **Hand off vs call.** A handoff transfers control; agent-as-tool returns a result. Pick per edge, deliberately.

## 6. UI references worth stealing (rendered; detail in `notes/ui-render.md`, `notes/skill-sites.md`)
| Site | Steal |
|---|---|
| skills.sh | the copy-command hero, the per-agent logo strip as an install-target filter, an 8-week sparkline beside the install total, All-time / Trending 24h / Hot tabs, and an Audits page |
| glama.ai/mcp/servers | a count on every facet, a Remote/Local/Hybrid facet, Deep Search separate from search, Add Server in the toolbar, A-F grades |
| tbench.ai | a TABLE / PARETO / WAFFLE switch on one dataset, a copy-filters link, a column chooser, AGENT as its own column, ±CI in muted text |
| lmarena.ai/leaderboard/webdev | a Rank Spread column, a Ranking / Pareto toggle, a facet rail (category, domain, score slider), and votes so sample size is visible |
| cursor.directory | a big rank digit per card, a Verified badge, the install count on the right, Trending / Top / New tabs, a social-proof hero line |
| typingmind.com/skills | the richest filter set (category, author, org vs community, bundled files, 4 sorts) |
| skillhub.club | a rank badge, an S-D grade with stated criteria, an S-rank filter |
| lobehub.com/skills | an "I'm an Agent / I'm a Human" toggle with an agent-first prompt box |
| claude-plugins.dev | a Quick Start with copyable install/list/enable lines and mono `@owner/marketplace` ids |
| artificialanalysis.ai/agents/coding-agents | "agent - model (effort)" labels with Cost per Task beside quality |
| vibeindex.ai | an Official Only filter and a security-scan status per listing |

The composite SISO should build: skills.sh's leaderboard + Glama's facets + Terminal-Bench's view switch +
LMArena's confidence columns + a trust grade on every card, with "measured gain" as the headline number.

## 7. Gaps and what to research next
1. **A measured-gain leaderboard pilot.** Pick the top 30 skills by installs and run each through our harness bench
   (with vs without the skill, pass rate and tokens). No hub has this column, so it's the moat.
2. **Trust scan pilot.** Run SkillSpector / mcp-scan-style static checks on the same 30 and publish A-F grades.
3. **People.** Use xsearch or a logged-in X session to rank the 50 people who matter, with follower counts.
4. **Live boards.** Run one camofox pass (one browser, rule 0) for HAL, Smithery and the Glama grade badge.
5. **Framework primaries.** Read Pydantic AI, Agno, Mastra, CrewAI and the MS Agent Framework.
6. **Then the hubs Shaan named next.** SISO Bench reuses section 2.9 and the Terminal-Bench/HAL shape; SISO Voice
   runs the same skill.
