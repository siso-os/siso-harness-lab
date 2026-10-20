# Harnesses slice notes (2026-10-14)

23 rows in rows/harnesses.jsonl. Target was 25+; Manus, OpenAI Operator/agent mode, Factory, Warp and Trae got no usable source this pass, so they are missing, not covered.

## Comparison table (what the official or fetched page says)

| Harness | Skills / rules file | Subagents | Hooks | Memory | Compaction | Permissions | Headless |
|---|---|---|---|---|---|---|---|
| Claude Code | CLAUDE.md, skills (load on invoke) | MD+YAML in .claude/agents; tools, model, permissionMode, hooks, skills, memory scope; nest depth 3 | ~30 events incl. PreCompact, SubagentStop; command/http/mcp_tool/prompt/agent | CLAUDE.md, auto memory per agent (user/project/local) | CLAUDE.md re-read after; subagent own window | 7 modes incl. plan, auto, dontAsk | not checked |
| Codex CLI | AGENTS.override.md > AGENTS.md, root-to-cwd, 32 KiB cap | TOML in .codex/agents; default/worker/explorer; sandbox inherited | beta (community index only) | not on fetched page | not on page | sandbox + approval, inherited | not checked |
| Gemini CLI | GEMINI.md; custom commands TOML (3rd party) | ~/.gemini/agents; no nesting (3rd party) | 4-layer settings.json; BeforeModel/AfterModel, PreCompress; exit 2 blocks | GEMINI.md | PreCompress hook | not checked | not checked |
| Cursor | .cursor/rules/*.mdc (alwaysApply, globs, description), AGENTS.md | not fetched | not fetched | rules only | not fetched | not fetched | not fetched |
| Windsurf | .devin/rules/*.md 12k chars; global 6k; AGENTS.md; workflows | not fetched | not covered | auto Memories (~/.codeium/windsurf/memories) | not fetched | not fetched | not fetched |
| Copilot coding agent | custom instructions, agent skills | custom agents | yes (validation/logging) | Copilot Memory | not fetched | PR review gate | cloud, not CLI |
| Devin | Knowledge (trigger-based) -> Skills in Plugins | not covered | not covered | Knowledge, trigger recall | not covered | not covered | CLI exists |
| opencode | agent key or .opencode/agents; skill permission | Build/Plan primary; General/Explore/Scout subagents | not covered | not covered | hidden compaction agent | edit/bash/webfetch/task allow/ask/deny with globs | run/serve (not read) |
| OpenHands | repo instructions (not read) | not read | not read | not read | condenser (not read) | headless auto-approves all | openhands --headless, --json JSONL |
| Roo Code | .roo/rules-{slug}/ rules; .roomodes | modes + Orchestrator new_task | not covered | not covered | not covered | tool groups, fileRegex narrowing | not covered |
| Aider | CONVENTIONS.md via --read / read: | not covered | not covered | not covered | not covered | not covered | scripting (not read) |
| Kiro | .kiro/steering (always, fileMatch, manual, auto) | not covered | described, no detail | steering | not covered | not covered | not covered |
| Amp | AGENTS.md, skills, plugins, MCP | not read | not read | threads | not read | not read | execute mode |
| Zed | .rules / AGENTS.md (not read) | threads, worktree isolation | not covered | not covered | checkpoints | profiles + allow/deny/confirm per tool | not covered |
| Jules | AGENTS.md read from repo root | not covered | not covered | not covered | not covered | plan approval before writes | CLI + REST API |
| Kilo Code | AGENTS.md; Memory Bank legacy | general + explore built-in; kilo.json or md | not covered | AGENTS.md | not covered | per-subagent permissions | not covered |
| Junie | .junie/AGENTS.md > AGENTS.md > custom path | not covered | not covered | guidelines | not covered | not covered | not covered |
| Claude for Chrome | none | none | none | none | none | 3 modes (manual, auto, skip-all) + per-site | n/a |
| Augment | .augment/rules (always, manual, description) | not found | not found | not found | not found | not found | not found |

## Coverage gaps
- Missing entirely: Manus, OpenAI Operator/ChatGPT agent mode (search returned only third-party pieces), Factory (docs.factory.com URL 404), Warp (docs.warp.dev 404), Trae (no official docs in search).
- Thin (repo row only, docs 404 or not reached): Cline, goose, Qwen Code, Crush.
- Not read (page was an index or the subpage was linked, not fetched): Amp execute mode, opencode headless, Aider architect mode, OpenHands condenser and sandbox, Cursor subagents and hooks.

## Notes
- Official doc hosts moved: developers.openai.com redirects to learn.chatgpt.com; docs.windsurf.com redirects to docs.devin.ai; docs.all-hands.dev to docs.openhands.dev; docs.roocode.com to roocodeinc.github.io; docs.factory.ai to docs.factory.com.
- Gemini CLI third-party claim: hosted CLI retired for free and Pro/Ultra tiers on 18 June 2026 in favor of Antigravity CLI (banner on the hooks page; not verified against a Google notice).
- Stars (gh api, 14 Oct 2026): Claude Code 150677; Codex 129067; Gemini CLI 107328; OpenHands 90838; opencode 213282; goose 55256; Aider 49532; Cline 70283; Crush 28628; Kilo 27599; Qwen Code 28471; Roo 24281.
- Next pass, if wanted: Cursor docs for subagents and hooks, OpenHands condenser docs, Amp /docs/customize/agents-md, Kilo subagent page, Cline docs.cline.bot current URL, and Manus/Operator help centers.
