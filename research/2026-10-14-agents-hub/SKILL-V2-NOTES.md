# hub-research: what was clumsy or wasteful in the v1 pilot (14 Oct 2026)

Already fixed in `~/.claude/skills/hub-research/merge.py` (backup and MANIFEST in `~/.claude/backups/2026-10-14-hub-research/`):
1. A duplicate URL kept the first row's empty fields, so README readers' enrichment was dropped. Merge now fills empty fields from later rows.
2. A text `numbers` field from a Haiku crashed the top-15 sort. It now tolerates text.
3. The coverage verdict credited a URL only to the first file merged (alphabetical), so blind maps stole credit: mcp-registries showed 8 rows when it wrote 29. Every slice that found a row is now credited, NOISE rows are excluded from counts and the top 15, and `zz-` verify files are hidden.

For v2:
1. **Rule 0 (load) was missing.** Six-plus Haikus and camofox pushed load to 58 and filled swap. Agent Zero added rule 0 mid-run (at most 4 Haikus, 1 browser, load under 16, swap under 6 GB). Put a `wait-for-headroom` one-liner in the skill so the Opus doesn't hand-roll it.
2. **gh-sweep writes only at the end.** A server restart lost the harness sweep after ~25 minutes. Append rows per query, and resume by skipping queries already done (keep a `.done` list).
3. **gh-sweep is slow** (~10 min per 10 queries × 5 bands) because of the search rate limit. Default `--limit 100` for bands below 200 stars, and print progress per query.
4. **`gh search code` quotes the whole query as one phrase.** Pass qualifiers as separate args (`--filename SKILL.md "path:skills"`) and sleep about 65 s between calls (10/min limit). Add a `gh-census.py` script beside gh-sweep: the census (2,172 SKILL.md repos and so on) was one of the best numbers per token.
5. **The blind map was snippet-only.** Blind-1 fetched no pages, so a whole directed slice was spent confirming it. Tell blind Haikus to fetch the top 10 they find.
6. **The coverage target was a fixed 40 rows per slice,** which marked well-covered slices LIGHT. A slice's falsifier is the real test. Replace `--target` with each slice's falsifier in PLAN.md, and make the blind-probe overlap the global stop rule. It worked: 37%, then two long-tail Haikus, then ~14%.
7. **Make the blind probe a named step.** It was the single most useful falsifier, so add a `probe-overlap.py` script (domains new vs known).
8. **Verify by script first.** Star counts via the GitHub API (206 rows in about 1 minute, free) before checkers. Checkers with a curl-batch method did ~100 rows each in about 20 calls; specify that method in the checker definition.
9. **WebFetch can't see client-rendered boards.** One camofox renderer Haiku was needed. Give the renderer slice a fixed site list from the start, and close tabs (one tab was left open).
10. **README readers need the noise rule.** Keyword sweeps pull unrelated giants (JavaGuide, JeecgBoot). Readers marked 37 NOISE; merge now drops them from counts.
11. **"The rows file changed on disk" was reported by 4 Haikus.** Cause unknown, possibly a hook or another reader. Worth one look.
12. **Budget.** About 30 Haiku runs at 58-104k tokens each (~2.4M Haiku tokens), roughly double the 1.2M in the draft, because of 3 extra rounds plus 4 checkers. Opus stayed around 90k. Raise the budget line or cap rounds at 2.
