# Sub-agent economics (researched 2026-10-14)

- **Saves tokens:** verbose, self-contained work (search, test/log output, doc fetches). Only the final message returns, so the parent context stays small. One measured case: parent input 47.8k to 2.1k, but total billed only 49.5k to 21.8k (-56%), because the subagent's run is billed too.
- **Costs more:** every spawn pays its own startup context (a cold start is ~37k tokens per a third-party transcript measure, ~80% rewritten, not cached) plus its own 5-minute cache writes. Small tasks lose. Fan-outs multiply this, and Anthropic says multi-agent runs use ~15x chat tokens.
- **Fork** (inherits parent history) reuses the parent's cache prefix and "costs less than a fresh subagent for tasks that need the same context". Use it when the parent already holds the context.
- **Agent teams** are the expensive mode (~7x in plan mode per Anthropic costs doc); use only for parallel work that needs peer debate.
- **Gaps:** no Anthropic number for fresh-subagent startup size; the parent-cache-sharing claim (issue 57751) conflicts with the official prompt-caching doc; the 14% saving (issue 74318) is modeled, not billed.
- **Rule of thumb:** delegate when the output is much bigger than the conclusion; stay in the main agent for iterative or shared-context work.
