# 07 hooks: why fetch-nudge misses the loops, and three changes (Haiku read of siso-harness-lab/hooks, 14 Oct)

Why 72 nudges did not stop hundreds of read-only calls:
- Bash counts only if it starts with a read verb (READ_CMD, fetch-nudge.mjs line 24): `echo`, `for`, `git -C`, `python`,
  `sort`, `cut`, `diff`, `du`-led reads never count, and they reset the streak.
- Any non-fetch tool resets the streak (line 30): Serena reads, TodoWrite, ToolSearch, TaskOutput.
- Nudge only at run===3 and at most once per 15 fetches; turnback once per streak and once per 20 fetches.
- Nothing is logged, so the hook's effect cannot be measured.

Changes (design, not applied; owner HARNESS):
1. Classify Bash by every piece of a pipeline/chain: drop echo/printf/true/for/done pieces; a fetch when every piece
   reads (add sort, uniq, cut, nl, du, diff, sed without -i, git -C/--no-pager read subcommands). Any >, >>, tee,
   sed -i, cp, mv, rm, mkdir, git add/commit/push/checkout/reset makes it a non-fetch. Tests in tests/fetch-nudge.test.mjs.
2. Add mcp__serena__ find/search/get/list, ToolSearch and TaskOutput to FETCH; TodoWrite neutral (neither counts nor
   resets); only Edit, Write, MultiEdit, Agent and mutating Bash reset.
3. Sliding window: nudge when 5 of the last 8 calls are fetches; turn back the 6th of 8 (repeat still passes);
   append each event to ~/.local/state/fetch-nudge/events.jsonl.
Also: context-ping env CONTEXT_PING_AT=280000 / BOUNDARY=250000 in both settings files.
