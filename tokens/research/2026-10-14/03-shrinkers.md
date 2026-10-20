# 03 shrinkers: top 5 notes (2026-10-14)

Stars and last_commit are from the GitHub API (last_commit = pushed_at). Claimed numbers are vendor-reported unless noted.

1. rtk (rtk-ai/rtk, 83,323 stars): vendor claims 60-90%, but the only independent cost run (Quesma, 1,740 Terminal-Bench 2.1 attempts, >$1,500) found token savings did not lower cost (DeepSeek +17%). Hook is Bash-only. https://github.com/rtk-ai/rtk
2. codebase-memory-mcp (DeusData, 46,566 stars): 99.2% (about 3,400 vs 412,000 tokens) on one vendor scenario vs naive grep; arXiv 31-repo study shows 10x fewer tokens but answer quality 83% vs 92%. https://github.com/DeusData/codebase-memory-mcp
3. context-mode (mksglu, 28,808 stars): 98% (315 KB -> 5.4 KB over 14 scenarios), self-reported; sandboxes per-call output, so it fixes call size, not cross-source work. https://github.com/mksglu/context-mode
4. token-savior (Mibayy, 1,177 stars): the only re-run with method is 8 tasks x 3 passes on Haiku 4.5, cost -45% and new tokens -59%, but wall time +40%; the 80% headline repo returns 404. https://github.com/Mibayy/token-savior
5. chop (AgusRdz, 46 stars): git status 247 -> 12 tokens, npm test 1,200+ -> 5 tokens (examples, no method); too new to trust without a local run. https://github.com/AgusRdz/chop

Gap: no published before/after numbers for Serena or ast-grep, and no independent replication of context-mode. Not checked: claude-token-lens, terse, context-os (search hits only, no stars or commit data).
