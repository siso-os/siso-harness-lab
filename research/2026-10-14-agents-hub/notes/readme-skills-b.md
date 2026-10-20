# readme-skills part B (ranked 41-80 by stars)

Classification: 32 RELEVANT, 8 NOISE (rows 010, 012, 014, 015, 020, 030, 032, 036).
Rows: 40 repo rows + 22 site rows = 62 (site rows only where the repo homepage is a website; Discord, author pages and one article are marked as such in the note field).

Packaging seen in this slice:
- SKILL.md folder packs: vercel-labs/agent-skills, google/skills (npx skills add), JimLiu/baoyu-skills, op7418/Humanizer-zh, khazix-skills, notebooklm-py, cloudflare/security-audit-skill, planning-with-files (skill plus per-turn hook).
- Plugin marketplaces: wshobson/agents (one Markdown source compiled to 7+ harnesses; make install-*), anthropics/claude-plugins-official (/plugin install X@claude-plugins-official), pm-skills (9 plugins), context-mode (Claude Code plugin with routing hooks).
- CLI or installer: vercel-labs/skills (npx skills, 75+ agents), googleworkspace/cli (gws, 40+ skills), OfficeCLI (skill file curl-ed by the agent).
- Harnesses or GUIs over CLI agents: AionUi, QwenPaw (pip install qwenpaw), nanoclaw.
- Format specs: agentskills/agentskills, agents.md, google-labs-code/design.md.
- Method or tooling about skills: SkillOpt (text-space optimiser, arXiv 2605.23904, pip install skillopt), NVIDIA/SkillSpector (scanner; README stats 26.1% of 31,132 skills vulnerable, 5.2% likely malicious; verify before citing).

Strongest finds for the hub:
1. wshobson/agents: single source compiled to Claude Code, Codex, Cursor, OpenCode, Copilot, Pi (94 plugins, 202 agents, 184 skills).
2. NVIDIA/SkillSpector plus SkillOpt: skill safety scanning and skill-as-trainable-artefact with validation gates (both are method claims needing checks).
3. context-mode (98% claimed tool-output reduction) and planning-with-files (3 of 3 blind A/B claimed): both are context-budget measures to check against our own instruments.

Still missing / not read:
- Install commands for several repos were not captured (only the headline or the grep hit): cognee and the NOISE rows were not read beyond the list line.
- Star numbers are as listed in the sweep; not re-fetched.
- No measured numbers were checked; all figures are repo claims.
- Hosted pages (planning-with-files landing, distilly, khazix) are unverified; the planning-with-files subdomain looks temporary.
- Homepages that are only author or Discord pages were recorded as site rows with a note, not as product sites.
