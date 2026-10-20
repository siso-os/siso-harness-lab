# Vendors slice: principles by vendor (research 2026-10-14)

Scope: canonical vendor pages only. Rows are in `../rows/vendors.jsonl` (22 rows). Items marked UNVERIFIED were not read at source.

## Anthropic (fetched primary pages)
- **Simplicity first** (Building effective agents, 2024-12-19): simplest design; make planning visible; invest in tool docs and tests.
- **Multi-agent pays only for parallel, breadth-heavy work** (multi-agent research, 2025-06-13): +90.2% over single Opus 4; about 15x tokens of chat. Subagents need objective, output format, tools and boundaries; effort rules scale with query complexity.
- **Context is the scarce resource** (context engineering, 2025-09-29): the smallest high-signal token set; just-in-time retrieval; compaction, notes and sub-agents for long tasks.
- **Tools: few, scoped, token-efficient** (writing tools, 2025-09-11): return high-signal results; prompt-engineer descriptions; Claude Code caps tool output at 25k tokens.
- **Skills load in tiers** (Agent Skills, 2025-10-16, upd. 2025-12-18): metadata, then SKILL.md, then linked files. Evaluate on real tasks first; audit untrusted skills.
- **Verification closes the loop** (Claude Code best practices, undated): give a check the agent can run; explore, plan, then code; prune CLAUDE.md; hooks for must-happen rules.
- **Long-running work needs a harness** (effective harnesses, 2025-11-26): an initializer plus one-feature-at-a-time workers, with git and progress logs; end-to-end test before "done".
- **Retrieval:** contextual retrieval (2024-09-19): chunk context plus hybrid search plus rerank cut top-20 failure 5.7% to 1.9%.

## OpenAI
- **Build from three parts; start with workflows** (practical guide PDF, UNVERIFIED): model, tools, instructions; single agent first; manager or handoff patterns; layered guardrails and human-in-the-loop.
- **Few primitives, works out of the box** (Agents SDK docs, fetched home page): handoffs as transfer tools, agents-as-tools, guardrails, default tracing.
- **Repo instructions are scoped and capped** (Codex AGENTS.md): closer files override; 32 KiB combined cap; fallback names.
- **Skills: description drives matching** (Codex/ChatGPT build-skills): progressive loading; explicit or implicit invocation; allow_implicit_invocation can disable auto-match.

## Google
- **A2A for agent-to-agent interop, built on web standards** (2025-04-09): agents collaborate without exposing internal state or tools; enterprise auth built in.
- **ADK: start simple, scale out, deploy anywhere** (adk.dev): five languages; "build production agents, not prototypes".
- **Agents Companion** (UNVERIFIED, Kaggle): evaluation of trajectories and final responses, AgentOps, agentic RAG. Not opened.

## Microsoft
- **Graph workflows with checkpoints and human-in-the-loop** (Agent Framework, preview 2025-10-01, RC 2026-02-19): orchestration patterns (sequential, concurrent, group chat, handoff, Magentic manager with task ledger). Built on MCP, A2A and OpenAPI interop. Snippets only.

## AWS
- **Model plans; the harness supplies tools and memory** (Strands, AgentCore Harness): vendor claims 28% cost reduction. Secondary sources only; AWS primary not fetched.

## Cloudflare
- **Remote MCP with auth and per-user tool permissions** (Agents SDK, 2025-04-07 changelog): McpAgent; acts as both MCP server and client. Guide not fetched.

## Hugging Face
- **Code as the action format** (smolagents README): CodeAgent writes Python in a sandbox; about 1,000 lines of core. Launch blog not found.

## Vercel
- **Skills as a portable package, discovered and installed by CLI** (2026-01-20): `npx skills add`; skills.sh directory. Lists 17 agents in the changelog.

## Cross-vendor: standards convergence
- **Tools:** MCP is the tool standard (donated to the Agentic AI Foundation, 2025-12-09 with goose and AGENTS.md). Cloudflare, AWS, Microsoft and Google all ship MCP.
- **Agent-to-agent:** Google A2A is cited by Microsoft and AWS.
- **Skills:** the open SKILL.md spec is used by Anthropic, OpenAI Codex/ChatGPT and Vercel's CLI. Progressive disclosure is the shared rule.
- **Repo instructions:** AGENTS.md (OpenAI-origin) is now a foundation standard; Claude Code uses CLAUDE.md.

## Where vendors agree
1. Start with the simplest design (Anthropic, OpenAI, Google "start simple", AWS "start with single agents").
2. Context is finite; load it progressively (Anthropic, OpenAI skills, Vercel, the skills spec).
3. Tools must be few, well described and testable (Anthropic tools, OpenAI guardrails on tools, AWS and Microsoft tool wiring).
4. Verification and evaluation are first-class (Anthropic verify-loop, Google evaluation, AWS evaluators).
5. Human-in-the-loop and guardrails are layered (OpenAI, Microsoft checkpoints and HITL).

## Where they disagree
- **Code vs JSON actions:** HF smolagents argues code actions (fewer round trips). Anthropic and OpenAI default to structured tool calls. Treat as a real fork.
- **Multi-agent by default?** Anthropic says multi-agent only for breadth-heavy work and costs about 15x tokens. Microsoft and Google ship orchestration patterns as first-class, and AWS starts with single agents.
- **Instruction scope:** CLAUDE.md is loaded every session (advisory, keep short); Codex composes root-to-cwd AGENTS.md with a byte cap. Hooks are Claude's deterministic layer; OpenAI has no equivalent in the fetched pages.
- **Long tasks:** Anthropic recommends an initializer plus progress files; Microsoft and AWS rely on checkpoints and managed runtimes.

## Gaps (not covered in this slice)
- Not fetched: Anthropic Agent SDK post (redirects to claude.com/blog/building-agents-with-the-claude-agent-sdk), Anthropic skills, subagents, hooks and plugins docs as pages, the agentskills.io homepage.
- Not covered: OpenAI cookbook, Apps SDK, Gemini CLI extensions, Agent Garden, Microsoft Copilot extensibility, MCP in Windows, Meta, xAI, Mistral, Hugging Face skills.
- Verification: the OpenAI PDF, Google Agents Companion and AWS primaries are unverified. Dates shown in the snippets (MS RC, Cloudflare changelog) were not fetched.
