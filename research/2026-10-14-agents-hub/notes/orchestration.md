# Orchestration slice notes (2026-10-14)

Scope: sub-agent and multi-agent structures. 44 rows in rows/orchestration.jsonl. Star counts from `gh api` on 2026-10-14 unless marked; GitHub search hit a rate limit mid-run, so a few counts come from fetched pages.

## Strongest finds
1. Anthropic multi-agent research system (orchestration-037): measured orchestrator-worker, +90.2% over single-agent on the internal eval, with cost (about 15x chat tokens) and effort-scaling rules.
2. Claude Agent SDK subagents guide (orchestration-002): depth, concurrency and spend caps as env vars and options; context-isolation table.
3. Ralph loop (orchestration-038): fresh context per loop, progress in files and git, backpressure gates.

## Structural ideas worth stealing
- Handoff vs agent-as-tool (OpenAI Agents SDK, orchestration-003): transfer control vs return a structured result.
- Workflow agents vs LLM routing (ADK, orchestration-004): deterministic control flow for plan-execute, LLM routing only where needed.
- Session-to-worktree-to-branch (claude-squad, ccmanager, uzi, Crystal): one task, one worktree, one branch, one agent. Container-per-agent (Container Use, Sculptor) is the stronger isolation.
- Broadcast-and-compare (uzi, GitHub Agent HQ): send one task to several agents and pick the winner.
- Protocol layering: MCP (tools), A2A (agents), ACP (editor to agent), AG-UI (agent to UI event stream). MCP sampling requires a human to review requests.

## Caveats
- Vibe Kanban (BloopAI, 28350 stars) says it is SUNSETTING. Crystal (3129) is DEPRECATED in favour of Nimbalyst. Do not build on either.
- Conductor is closed source with no GitHub repo; details are from third-party reviews and the vendor workflow page.
- Terragon: secondary sources say the repo is stale.
- ruvnet/claude-flow and ruvnet/ruflo are the same repo (74575 stars); high star count, low evidence checked.
- uzi license conflicts across listings; check the repo LICENSE.
- microsoft/autogen vs AG2 (ag2ai/ag2): the AG2 slug was not checked.
- The agent-framework and ADK pages the fetch returned as redirect stubs (adk.dev, LangGraph multi-agent concepts and hierarchical tutorial, LangChain plan-and-execute). Their pattern descriptions are from memory; re-check before quoting.

## Not done (budget)
- Frameworks not read in depth: Pydantic AI, smolagents, Agno, DSPy, Letta, Swarms, CAMEL, Mastra, MS Agent Framework, CrewAI.
- Stars for ruflo, uzi and AG2 unverified or ambiguous.
- Blackboard and hierarchical sources are general knowledge with a Wikipedia or tutorial URL that was not fetched.
- Event names in AG-UI (TEXT_MESSAGE, TOOL_CALL, STATE_DELTA) not confirmed.
- No check of the Claude Code agent-team or Workflow tool (dynamic workflows) beyond the SDK doc mention; that sits in the harness slice.
