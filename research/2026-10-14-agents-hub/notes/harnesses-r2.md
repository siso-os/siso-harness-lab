# harnesses-r2: packaging units and hubs (gap fill)

Round 2, slice harnesses. 13 rows in rows/harnesses-r2.jsonl. Official pages fetched unless the row's note says otherwise. Not yet fetched: OpenAI Operator/agent mode/Codex cloud (redirect not followed), Qwen Code, Crush, Continue hub, Warp Workflows.

| Harness | Packaging unit (name) | Subagent unit | Hub URL (count) |
|---|---|---|---|
| Factory | plugin (.factory-plugin/); skills/, hooks/hooks.json, mcp.json | droids/<name>.md | github.com/Factory-AI/factory-plugins (3 official) |
| Warp | Rules: AGENTS.md (WARP.md legacy); Global Rules | not documented | none documented; Warp Drive personal store |
| Cline | rules: .clinerules/ or .cline/rules/ (paths frontmatter); workflows: .clinerules/workflows/*.md | not documented | github.com/cline/mcp-marketplace (MCP only) |
| goose | recipe (YAML) and sub-recipe | sub-recipe (own session, no nesting, summon) | GOOSE_RECIPE_GITHUB_REPO; no count |
| Devin | Playbook (!macro, Procedure/Spec/Forbidden sections, versioned) | not documented | Settings > Playbooks (Org/Enterprise); no public hub |
| OpenHands | skill: .agents/skills/<name>/SKILL.md; path-rule; keyword skill | not documented | github.com/OpenHands/extensions (no count) |
| Manus | Skill: SKILL.md + assets (.zip/.skill/folder) | not documented | "Add from official" library (no count); Team library upcoming |
| JetBrains Junie | agent skills (open format); guidelines | .junie/agents/*.md (tool restrictions) | none found; .aiignore for scope |
| Qoder | rules: .qoder/rules/ (100k char cap); skills: SKILL.md | built-in CLI subagents | skills.sh (de facto; no Qoder hub) |
| Kilo Code | agent: .kilo/agents/<name>.md (mode primary/subagent/all) | mode: subagent | kilo.ai/marketplace (no count on page) |
| GitHub Copilot coding agent | custom agent: .github/agents/<name>.agent.md | the agent file itself | github.com/copilot/agents; github.com/github/awesome-copilot |
| Cursor | Cloud Agents; BugBot PR reviewer | not confirmed | cursor.com/marketplace (round 1) |
| Trae | .trae/project_rules.md, .trae/user_rules.md (unverified) | not found | none verified |

Takeaways for the hub:
1. Factory and Copilot both put subagent tool allowlists in the repo file, the enforcement pattern for review roles.
2. Kilo and Junie split user-facing modes from delegate-only subagents with a mode or tool field; OpenHands fires path-triggered rules only when a matching file is touched.
3. Devin's playbook schema (Procedure, Forbidden Actions, versioned macros) is the most structured official playbook format seen.
