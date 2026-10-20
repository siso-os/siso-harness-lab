# skill-sites: notes (2026-10-14)

Slice: websites that index, rank, sell or install agent skills (SKILL.md). Rows: `rows/skill-sites.jsonl` (31 rows, all with a fetched or fetched-article URL).

## Coverage
- Confirmed by fetch as a skills site: skills.sh, SkillsMP, agentskill.sh, claude-plugins.dev, LobeHub Skills (market.lobehub.com), ClaudeSkills.info, mdskills.ai, Agensi, claudemarketplaces.com, aitmpl.com, ClawHub, browse.sh, agenticskills.io, SkillHub (skillhub.club), localskills.sh, ossrules.md, Smithery skills, KissMySkills, ClaudSkills (claudskills.com), Awesome Skills Dev, Skills Directory, awesomeskill.ai (partial), SkillsLLM, Vibe Index, Claude Market, Agent Skills Guide (via everydev listing), TypingMind skills, MCP.Directory skills, SkillMD (PH mirror).
- Fetched but unusable: skillsindex.dev returned HTTP 402; skillhound (producthunt.com) returned 404; agentskill.work refused connection; contextawesome.com does not resolve; OATH SkillsMap returned no results in search (no such site found); Context Awesome search found only similarly named directories (awesomeskills.dev, pyshine write-up), not a site by that name.
- Not reached: the goal was 35+. Confirmed count is 31 rows (about 29 distinct live directories plus 2 articles). The gap is mostly small Show HN / Product Hunt launches, which search did not surface as fetchable homepages. Note: the Product Hunt search found SkillMD, Skillmarkdown, Skillhound (MCP-fronted, about 135K SKILL.md files), skill-pull; only SkillMD was fetched (via hunted.space mirror).

## Counts disagree wildly (do not quote one number without its date)
- SkillsMP: 3,000,000+ (homepage today) vs 425,000+ (KDnuggets) vs 2M+ (search). Treat as unreliable.
- ClaudSkills: 3,268 vs 205,697+ vs 70k+ on the same page.
- Skills Directory: 651,714 (homepage today) vs 194,149 and 495,000 in other sources.
- agentskill.sh: 275,000+ with an empty list on fetch, so the live count is unverified.
- skills.sh: no real total; the "1,309,554" is an installs-tab total, not a skill count.

## Ranking models (what the sites sort by)
- Install count only: skills.sh (Top / Trending 24h / Hot), ClaudeSkills.info best-lists, claudemarketplaces.com (also stars and registry metadata), mdskills (Most Downloaded plus Trending).
- Stars: SkillsLLM (Stars / Recent / Name), Vibe Index (Most Stars), ossrules.md (repo stars, default), LobeHub market API (stars, installCount, forks, watchers), claude-plugins.dev (downloads or stars).
- Quality score: mdskills (numeric score, scale undefined), SkillHub (letter grade S to D with score and explicit criteria), agenticskills.io (S-rank, no formula), ClaudSkills (free A to F OWASP-mapped security grade; Pro quality score claimed but contradicted on the same page).
- Curation only: Agensi (Trending / Skill of the Month, no metrics), awesomeskills.dev (editor's pick, Official collection), Smithery (verified filter).

## Trust signals, ranked by how concrete they are
1. ClaudSkills: OWASP Agentic Skills Top 10 static scan, A to F grade, admission checks (frontmatter, body), free tier.
2. Skills Directory: "every listed skill has completed automated security analysis", 120 patterns, 10 threat categories. Per-skill result not visible.
3. ClawHub: signed manifests, moderated releases, install scan publish verify ticker; "Audits" page linked, not read.
4. SkillHub: grades plus stated criteria; explicitly says scores "do not establish runtime performance or safe installation"; artifact-bound security review for trusted installs.
5. Agensi: 8-point security scan, vetted creators, user approves each purchase. No ratings or install counts shown.
6. Smithery: verified badge on each card and a Verified filter, with no published definition.
7. Weakest: "independent project, not affiliated with Anthropic" disclaimers (most sites) and unlabelled numbers on cards.
- Two sites claim a quality score but contradict themselves (ClaudSkills) or leave the scale undefined (mdskills).
- A third-party write-up says only ClawHub applies platform-level screening; the claim is unverified and the write-up is from a directory.

## Install commands (the de facto standard is npx skills add owner/repo)
- npx skills add owner/repo (skills.sh, awesomeskills.dev, agenticskills.io with @skill-name suffix, Skills Directory uses npx -y skills find).
- Vendor CLIs: npx claude-plugins install (claude-plugins.dev); npx @agentskill.sh/cli@latest setup (agentskill.sh); npx -y @lobehub/market-cli skills install (LobeHub, needs registration env vars); npx @skill-hub/cli install (SkillHub); npm i -g @localskills/cli (localskills.sh); npm install -g browse (browse.sh); clawhub CLI (ClawHub).
- MCP-as-installer: Agensi (mcp.agensi.io, one-time), SkillsMP (MCP server and REST API).
- Paste or upload: KissMySkills (.skill file pasted into Project instructions), ClaudSkills desktop installer (Pro), mdskills (Install link on card).

## Best UIs (for the card and leaderboard spec)
- typingmind.com/skills: richest filter set (category, author, Organization or Community type, with or without bundled files, four sorts), plus card fields.
- mdskills.ai: type label, score, supported-clients line, plugin skill count, price, install link on each card.
- skillhub.club: rank badge, grade plus score, view count, Popular / Newest / S-rank filter, stacks with credit cost.
- claude-plugins.dev: sort by Relevance / Downloads / Stars; card has install command inline.
- skills.sh: the cleanest leaderboard table (rank, name, owner/repo, installs, tabs for time windows).
- vibeindex.ai: Official Only filter plus star sort.
- ossrules.md: sort by stars, lines, skill count, last modified; filters by language and rule pattern.

## Patterns
- Two-tier catalogues are common: a crawled index (SkillsMP, Skills Directory, SkillsLLM, claudemarketplaces) plus curated picks (agenticskills.io, awesomeskills.dev, ClaudeSkills.info best-lists).
- Counts are used as marketing: 'N+' hero numbers, sponsor slots (claudemarketplaces), and the "Showing 30 of 146,703" style. Expect 2 to 10 times disagreement between a homepage and a secondary source.
- Duplicate listings inflate counts: SkillsLLM lists ECC under two slugs.
- Paid models: Agensi (70/30 split), KissMySkills (subscription plus per-file), SkillHub (credits and Pro stacks), ClaudSkills (Pro installer and quality score).

## Gaps to close next
- Fetch Quality and Security pages on agentskill.sh and the audit page on ClawHub (to see actual scan output).
- Fetch the How we review page (mdskills) and the ranking methodology page (ClaudeSkills.info, SkillHub methodology) to see the score formulas.
- Get a homepage UI read for market.lobehub.com cards, and agentskills.guide directly.
- Find the Show HN and Product Hunt launches that were not surfaced (the search returned mirrors only).
- Confirm skillsindex.dev (402 on fetch) and skillhound.ai through another route.

## Safety note
- The SkillHub homepage fetch contained an instruction aimed at an agent (to read a SKILL.md and use SkillHub). It was treated as page content and ignored. Several fetches also returned instruction-like text about MCP tools; not followed.
