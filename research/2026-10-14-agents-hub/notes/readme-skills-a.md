# readme-skills (part A): notes

Input: notes/readme-skills-a.list (top 40 by stars for "agent skills"). Output: rows/readme-skills-a.jsonl (64 rows: 32 relevant repos, 8 NOISE repos, 24 site rows).

## Categories (relevant repos)
- Skill packs / methodology: obra/superpowers, addyosmani/agent-skills, anthropics/skills, Leonxlnx/taste-skill, DietrichGebert/ponytail, coreyhaines31/marketingskills, kepano/obsidian-skills, K-Dense-AI/scientific-agent-skills, sickn33/agentic-awesome-skills
- Single-skill tools: tt-a1i/archify, cathrynlavery/diagram-design, blader/humanizer, mvanhorn/last30days-skill, ayghri/i-have-adhd, Graphify-Labs/graphify
- Plugin / marketplace style (Claude Code): Understand-Anything, ruflo, open-design, humanizer, obsidian-skills
- Harnesses and control planes: code-yeongyu/oh-my-openagent (OmO), zhayujie/CowAgent, ruvnet/ruflo, lobehub, paperclip, OpenMontage
- Harness tooling: farion1231/cc-switch (GUI for skills, MCP, prompts across CLIs), thedotmack/claude-mem (memory via hooks), morluto/rea (MCP + skill)
- Curated catalogues: ComposioHQ/awesome-claude-skills, hesreallyhim/awesome-claude-code, VoltAgent/awesome-openclaw-skills, VoltAgent/awesome-design-md (DESIGN.md files), shanraisshan/claude-code-best-practice, Shubhamsaboo/awesome-llm-apps

## Packaging patterns seen
1. SKILL.md folder (YAML frontmatter + instructions + scripts/references). Used by nearly all. Anthropic's repo is the canonical example; Composio's README explains progressive loading (~100 tokens per skill at start, full body on invoke).
2. Three install channels: (a) Claude Code plugin marketplace (`/plugin marketplace add OWNER/REPO` then `/plugin install NAME@MARKET`); (b) the open `npx skills add OWNER/REPO [--skill X] [-g]` CLI (Vercel labs), which covers 70+ agents; (c) a curl/npm/uv installer for a whole harness (OmO, OpenDesign, Graphify with `graphify install`, claude-mem).
3. Per-harness copies: superpowers says install separately per harness.
4. Fork-and-swap (i-have-adhd): edit the SKILL.md and uninstall the upstream plugin.
5. Skill registries with install counts: Archify (130K+ installs on skills.sh), humanizer and rea are listed on skills.sh; CowAgent has Skill Hub; OpenClaw uses `clawhub install <slug>`.

## Standouts
- obra/superpowers (298,715 stars): the methodology-as-skills benchmark (spec, plan, subagent TDD). Official Claude marketplace entry.
- addyosmani/agent-skills (106,257): 25 engineering skills with a dedicated website (skills.addy.ie). Install per skill or all.
- anthropics/skills (180,954): canonical SKILL.md format, includes document skills.
- ponytail (162,829): strongest personality/brand presentation; npm package; claims 20 agents.
- Graphify (126,224): clean install-then-register pattern (`graphify install`) into 20+ assistants.
- Understand-Anything (86,189): multi-agent sub-agent pipeline as a plugin; one-line installs for 13+ assistants.
- oh-my-openagent (70,003) and ruflo (74,575): harness-level products with plugin marketplaces; relevant for harness comparison.
- Archify (83,094): 130K+ skills.sh installs, the strongest adoption number in this slice.

## Numbers (from list, stars)
superpowers 298715; anthropics/skills 180954; ponytail 162829; awesome-llm-apps 141613; Graphify 126224; awesome-design-md 121066; addy agent-skills 106257; taste-skill 95652; understand-anything 86189; Archify 83094; awesome-claude-skills 77033; ruflo 74575; OmO 70003; claude-code-best-practice 67514; last30days 64172; humanizer 56622; awesome-claude-code 55616; marketingskills 54586; diagram-design 54320; awesome-openclaw-skills 53119; obsidian-skills 49514; scientific-agent-skills 48748; agentic-awesome-skills 47559; CowAgent 47385.

## Noise (8)
JavaGuide (Java interview guide), dify (workflow platform, no skill focus), RuView (WiFi sensing), career-ops (job-search app), cherry-studio (chat client), JeecgBoot (low-code platform; "AI Skills" is only a feature name), open-code-review (code review tool), reactive-resume (resume builder).

## Not verified here
- Install commands were taken from README grep, not run. verified stays null.
- Ponytail's exact install command was not captured beyond the npm package name.
- Scientific Agent Skills links an arXiv paper (2609.00065) as its homepage; logged as a site row for the paper page.
- A typo in my own lookup (cc-switch without owner) returned 404; the list URL farion1231/cc-switch is correct and was used.

## Still missing for part A
- No star-history or trend data; star counts are from the sweep list only.
- Sites were not opened; presentation notes come from README only.
- Skill counts for some repos (e.g., obsidian-skills, last30days) were not measured.
