# 09 Harnesses: top 5 to steal for Claude Code

Source rows: `09-harnesses.jsonl` (11 rows). Verified = official page read; secondary = blog or fork report.

1. Spill big tool output to a file and return a head plus the path (Cursor, blog read). Keep full chat history on disk so post-compaction recovery can grep it.
2. Cap each tool result in tokens, with a per-MCP-tool override (Codex `tool_output_token_limit`, official key confirmed; the 10000 default is secondary only).
3. Goal-directed handoff with a generated starter prompt and relevant-file list instead of a rolling summary (Amp Handoff, official post). This matches seat-fresh; the goal line is the input.
4. Background-summarise tool results older than the last ~10 calls, keep recent ones verbatim (Goose `GOOSE_TOOL_CALL_CUTOFF`, official docs), plus dedupe repeat reads of one file (OpenCode DCP, community plugin).
5. Fixed-budget ranked repo map at session start (Aider `--map-tokens` 1k, official docs), so orientation does not cost file reads. Also: keep ~15k recent tokens verbatim and retry once on a too-long rejection (OpenCode v2 docs).

Still missing: Claude Code's own truncation and compaction limits (not in this slice); Amp's official manual on subagents (fetch returned no content); Codex's official default for `tool_output_token_limit`; Cline's core context source (its docs give no thresholds). The Cursor 46.9% MCP number is the only A/B figure found.
