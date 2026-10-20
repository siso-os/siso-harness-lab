# Round 2: vendors gap fill (2026-10-14)

Rows: `../rows/vendors-r2.jsonl` (26 rows, found_by `vendors-r2`). Round 1 is in `vendors.md`; it covered Anthropic and the first-pass OpenAI, Google, Microsoft, AWS, Cloudflare, HF and Vercel pages. This round replaces several UNVERIFIED round-1 items with primary text.

## Coverage
- **Read at source:** OpenAI practical guide (pp.1-10 of the PDF; orchestration and guardrails pp.11-32 NOT read), Agents SDK guardrails and handoffs, Codex AGENTS.md, Codex/ChatGPT skills, OpenAI plugins (Apps SDK URL), openai/skills and openai/plugins repos, OpenAI cookbook index, A2A spec, ADK home, Agent Garden, Gemini CLI extensions, Microsoft Agent Framework, Foundry Agent Service, Windows MCP, M365 Copilot extensibility, AgentCore, Strands repo, xAI tools, Mistral agents, Vercel AI SDK agents, Cloudflare Agents, smolagents docs, huggingface/skills.
- **Not fetched or dead:** Kaggle Agents whitepaper and Companion (title-only pages); Llama Stack (developer.meta.ai and dev.meta.ai both 404 or unreadable); Strands docs site (404); Mistral /agents/ (404); Copilot /microsoft-365-copilot/ path (404); Agentspace (no primary page found).

## Principles stated at source (this round)
- **Build an agent only when a rule engine is the wrong tool.** OpenAI guide: three triggers (complex judgment, rules too brittle to maintain, unstructured data); otherwise a deterministic solution "may suffice". Microsoft says the same in its own words: "If you can write a function to handle the task, do that instead of using an AI agent."
- **Measure before you downsize the model.** OpenAI: eval baseline with the strongest model, then swap in smaller ones. Google ADK's eval taxonomy (criteria, user simulation, custom metrics) is the concrete tooling.
- **Hand off vs call.** OpenAI Agents SDK: a handoff transfers the conversation; `as_tool` keeps control. Mistral and Microsoft ship handoffs too, so this is now the common primitive.
- **Guard at the edges, halt on tripwire.** OpenAI SDK: input guardrails only on the first agent, output only on the final one, tripwires stop the run. Microsoft Foundry and Windows MCP add containment and per-agent consent at the platform layer.
- **Progressive loading with a hard budget.** Codex skills: name and description only at start, capped at 2% of context (8,000 chars fallback). Codex AGENTS.md: 32 KiB cap, nearest file wins. Gemini CLI, OpenAI and HF all ship skill+MCP bundles as installable plugins.
- **Interop by open protocol.** A2A 1.0 names five principles (simple, enterprise-ready, async-first, modality-agnostic, opaque execution). Foundry's docs say A2A 1.0 is GA, which corroborates the version.
- **Durable state as the platform.** Cloudflare: durable identity, local SQL, scheduled work, recoverable execution. Microsoft Harness Agent: compaction and memory built in. ADK: managed context (filter, summarize, lazy-load).

## Where vendors agree
1. **Simplest design first, graduate on evidence.** OpenAI (single agent first), ADK (progressive complexity), Microsoft (function before agent), Vercel (structured workflows when predictability matters).
2. **Few, well-scoped tools.** OpenAI (standardized reusable tool definitions), OpenAI Apps SDK (a "focused MCP tool surface"), Foundry (Toolboxes curate tools once), Windows MCP (only approved resources).
3. **Tools are the gate for risk.** Foundry content filters for cross-prompt injection, Windows MCP containment, AgentCore gateway with auth, Mistral connectors. Every vendor now puts MCP behind a managed gateway or registry.
4. **Skills and plugins are the distribution unit.** OpenAI (plugin = MCP + skills + optional UI), Gemini CLI (prompts, MCP, commands, hooks, sub-agents, skills), HF (25 skills, install via marketplace), Microsoft M365 (lifecycle to retirement).
5. **Traces plus evals close the loop.** OpenAI cookbook (improvement loop), Foundry (trace, evaluate, optimize, monitor), AgentCore (traces and tests on real traffic), ADK (evaluate pages).

## Where they disagree
- **Code actions vs structured calls.** smolagents makes code the action format and sandboxes it (Modal, Blaxel, E2B, Docker). OpenAI, Mistral, xAI and Foundry default to structured function or tool calls. Still a real fork.
- **Server-side vs local execution.** xAI runs built-in tools on its servers and bills per call; Mistral and Foundry hold connectors and state server-side too; Codex, Gemini CLI and Claude Code run skills and hooks locally. Cost and data-residency logic differ by side.
- **Who owns the loop.** Strands, Vercel ToolLoopAgent and Microsoft Harness Agent each ship a loop; Vercel's HarnessAgent wraps Claude Code and Codex instead of competing with them. Cloudflare moves the loop into a durable object. No consensus on whether the vendor or the app owns the loop.
- **Instruction scope.** Codex composes root-to-cwd AGENTS.md under a byte cap; Gemini CLI relies on extensions; Microsoft has no repo-instruction file in the fetched pages. Only Codex states a hard byte budget.
- **Status of the catalog.** OpenAI deprecated openai/skills in favour of openai/plugins; Gemini CLI was replaced by Antigravity CLI on 2026-06-18 for some tiers. Vendors are moving their own packaging under them, so pin versions.

## Caveats for the parent
- OpenAI PDF orchestration and guardrail sections were not read; the principles above on those topics come from the SDK pages instead.
- Google Agents whitepaper and Companion are unverified; their rows say so.
- Dates are sparse: many pages have none. ms.date values (Microsoft) and "last updated" stamps (Google Agent Garden 2026-10-13, Cloudflare 2026-09-18, Gemini CLI 2026-02-17) are the only ones recorded.
