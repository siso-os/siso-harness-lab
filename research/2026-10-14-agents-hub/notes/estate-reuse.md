# Estate reuse: agent skills, hubs, MCP, harnesses, sub-agents, prompt banks (read-only check, 2026-10-14)

Scope: what the estate already holds. No files were changed outside this note. siso-skills-hub was not touched.

## Sources

1. **`estate where skills | mcp | harness`** (ran)
   - skills: `SISO_Agents/siso-skills-hub` (Agent guide, ours, active), `jev-agent-skills`, `siso-agent-stack`, `siso-estate`, `unfuck-the-project`.
   - mcp: `SISO_Agents/siso-workspace` (DevSpace, MCP server); one legacy kellman repo (archived).
   - harness: `SISO_Agents/siso-harness-lab` (ours, active) with `brain/`, `tools/herdr-resurrect`, `tools/fleet-meter`, `integrations/headroom`.

2. **`Great_Library_of_SISO/banks/siso-repo-bank`** (10 top-level files plus 5 folders)
   - `bank/bank_agent_pattern.jsonl`: 62 rows of agent/prompt patterns. About 17 source repos, e.g. Piebald-AI/claude-code-system-prompts, anthropics/skills, obra/superpowers, wshobson/agents, msitarzewski/agency-agents, Yeachan-Heo/oh-my-claudecode, github/spec-kit, thedotmack/claude-mem, safishamsi/graphify.
   - `bank/category.jsonl`: 264 category rows, including "AI & Agent Tooling" (agentic CLIs, agent SDKs, skill/config/MCP packs).
   - `catalog-pipeline/harvest/ai-coding-agents.jsonl`: 480 rows (top: affaan-m/ECC, NousResearch/hermes-agent, google-gemini/gemini-cli, cline, punkpeye/awesome-mcp-servers, ComposioHQ/awesome-claude-skills).
   - `catalog-pipeline/harvest/prompt-engineering.jsonl`: 395 rows (top: f/prompts.chat, dair-ai/Prompt-Engineering-Guide, asgeirtj/system_prompts_leaks, wshobson/agents, github/awesome-copilot).
   - 102 harvest rows mention MCP.
   - `capability-shelf/source-registry.jsonl`: 3,010 sources, generic. A keyword match on "mcp|agent|skill|harness|plugin" hits 729 rows, but it is loose (many are unrelated apps). Use `registry-summary.json` for real counts.
   - `github-farm/`: 56,674 GitHub URL rows (star-banded), repo URLs only, no READMEs.
   - Note: `catalog-pipeline/` holds about 3,066 files. No categories were parsed as agent/MCP; the 264-row taxonomy has no `category` key.

3. **foundry**: the `foundry` command is not on PATH in this shell (`command not found`). Skipped. Its catalog is in `banks/siso-repo-bank/catalog-pipeline/foundry_browser.html` and `foundry_categorize.py` (not read).

4. **`SISO_Agents/agent-zero/siso-agent-zero/research/harness-rob/`** (Agent Zero's 4 Oct collation)
   - `INDEX.md` (39 KB), `items.json`: 100 findings, fields `id, harness, angle, rank, thing, why, theirs, ours, rob, size`.
   - `themes.json` (8 KB): grouped themes with vote counts (e.g. auto worktree per agent, fork/rewind, diff review: 5 of 5 harnesses each).
   - `ROB-{OPENCODE,T3CODE,GROK,CONDUCTOR,VIBEKANBAN}-{A,B}.md`: 10 research reports; `threads.txt` holds 12 Codex thread ids; `deep/`: 18 deep-dive files.
   - Covers 5 harnesses: OpenCode, T3 Code, Grok Build, Conductor, Vibe Kanban.

5. **`SISO_Agents/siso-skills-hub/registry/skills_registry.json`** (read-only)
   - Top key `skills`, **52 skills**. Fields: `skill_id, name, description, category, tags, version, author, repo_url, remote_url, commit_hash, published_at, dependencies, install_commands, files, metadata`.
   - By category: global 16, code 11, devops 9, system 4, pipeline 4, communication 3, data 3, testing 2.
   - Sources: almost all "bundled" from our own repo. Only `siso-workspace` is "independent". Only one repo_url is recorded (sisodias/siso-workspace).
   - Also: `INDEX.md` (generated), `source-provenance.json` (SISO_Agent_Base origin), `promotion-assessments.json` (41 KB), `agent-base-source-inventory.json` (40 KB), `skills/` (8 category folders).

6. **`_data/app-factory/research/`** (6 files)
   - Only `RESEARCH-SKILL-DRAFT.md` and `proposed-tasks.json` mention an agents hub (`AGENTS-HUB`, tasks `agents-hub-1` to `agents-hub-4`). No external URLs.
   - `people-graph.md`, `partners.md`, `lawbook.md`, `questions.md`: no agent-hub content found.
   - No kunchenguid or agent-registry map here.

7. **`SISO_Agents/siso-harness-lab/.agents/memory`** (39 files)
   - `kunchenguid-fleet-research.md`: kunchenguid fleet (firstmate 1.4k★, treehouse 957★, gnhf 3.3k★, wheelhouse, axi 1.5k★, plus the -axi family). Full write-ups in SISO_Agent_Base `research/kunchenguid-fleet-digests/` and `FIRSTMATE-INTEGRATION-PLAN-20260718.html` (not opened here).
   - `jev-decision-model.md`, `jev-kill-list.md`, `jev-judgment-and-ui-pick.md`: Jev (TypeSafe) endpoint, decomposition rule (48.3% to 98.3%), kill list, two shipped skills (`jev-judgment`, `ui-pick`, 137 curated picks in `banks/siso-ui-base/registry/curated/picks.jsonl`). The 111-regex Stop-gate retrofit is moot (gates unregistered).

## Known external URLs and repos (bullet list, up to 60)

- https://github.com/affaan-m/ECC
- https://github.com/NousResearch/hermes-agent
- https://github.com/google-gemini/gemini-cli
- https://github.com/punkpeye/awesome-mcp-servers
- https://github.com/ComposioHQ/awesome-claude-skills
- https://github.com/cline/cline
- https://github.com/f/prompts.chat
- https://github.com/dair-ai/Prompt-Engineering-Guide
- https://github.com/asgeirtj/system_prompts_leaks
- https://github.com/wshobson/agents
- https://github.com/github/awesome-copilot
- https://github.com/Piebald-AI/claude-code-system-prompts
- https://github.com/anthropics/skills
- https://github.com/obra/superpowers
- https://github.com/msitarzewski/agency-agents
- https://github.com/Yeachan-Heo/oh-my-claudecode
- https://github.com/github/spec-kit
- https://github.com/thedotmack/claude-mem
- https://github.com/safishamsi/graphify
- https://github.com/multica-ai/andrej-karpathy-skills
- https://github.com/affaan-m/everything-claude-code
- https://github.com/langgptai/LangGPT
- https://github.com/daveshap/SparsePrimingRepresentations
- https://github.com/dave1010/tree-of-thought-prompting
- https://github.com/ghuntley/claude-code-source-code-deobfuscation
- https://github.com/Yuyz0112/claude-code-reverse
- https://github.com/liuup/claude-code-analysis
- https://github.com/microsoft/ai-agents-for-beginners
- https://github.com/microsoft/generative-ai-for-beginners
- https://github.com/JuliusBrussee/caveman
- https://github.com/linshenkx/prompt-optimizer
- https://github.com/web-infra-dev/midscene-skills
- https://github.com/vibheksoni/stealth-browser-mcp
- https://github.com/alfonsograziano/node-code-sandbox-mcp
- https://github.com/yellenlegal/clio-mcp
- https://github.com/pingdotgg/t3code
- https://github.com/BloopAI/vibe-kanban
- https://github.com/xai-org/grok-build
- https://www.conductor.build/docs/concepts/git-worktrees
- https://www.conductor.build/docs/reference/checkpoints
- https://opencode.ai/docs/server/
- https://www.vibekanban.com/docs/workspaces/changes
- https://github.com/kunchenguid/firstmate (name from memory; URL inferred, not stored)
- https://github.com/kunchenguid/gnhf (inferred)
- https://github.com/kunchenguid/treehouse (inferred)
- https://github.com/kunchenguid/wheelhouse (inferred)
- https://github.com/kunchenguid/axi (inferred)
- https://github.com/code-yeongyu/oh-my-opencode (Agent Base sources)
- https://github.com/sisodias/first-principles (Agent Base sources)
- https://github.com/jo-inc/camofox-browser (in use)
- https://github.com/GautamVhavle/CatGPT-Gateway (in use)
- https://github.com/Waishnav/devspace (in use)
- https://github.com/zephel01/Jev-sample (Jev measurements)
- https://github.com/tamaratran/fast-jev-compaction (failed negative control)
- https://github.com/shiftynick/jev-axi (read, not adopted)
- https://openrouter.ai/api/alpha/decisions (Jev endpoint, not a repo)
