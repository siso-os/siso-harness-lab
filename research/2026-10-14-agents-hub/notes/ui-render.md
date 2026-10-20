# ui-render notes (14 Oct 2026, camofox)

17 rows in rows/ui-render.jsonl. HAL (hal.cs.princeton.edu) did not render (camofox session expired twice), so it has no row. cursor.directory and lobehub needed a retry; both rendered on the second try.

## The 5 best UIs and what to steal

1. **skills.sh** (leaderboard of installs). Steal:
   - The install line in the hero: `npx skills update` with a copy button.
   - The per-agent logo strip (20 agents), each linking to /agent/<slug>, as an install-target filter.
   - An 8-week sparkline column beside the install total, so rank and momentum read together.
   - Tabs All Time (count in label) / Trending (24h) / Hot, plus an "Audits" nav item as the trust surface.

2. **Glama MCP servers** (facet directory, 97,619 servers). Steal:
   - A count after every facet label (Python 40,815; Remote 40,169; Local 35,284).
   - Remote / Local / Hybrid as a facet ("does it run where I need it").
   - Deep Search as a separate button from plain search, and a Sort-by combobox defaulting to relevance.
   - The "Add Server" button in the toolbar, not hidden in the nav.

3. **LMArena WebDev** (ranked table with confidence). Steal:
   - A Rank Spread column (best and worst rank the confidence interval allows) next to the score.
   - A Ranking | Pareto segmented toggle on the same data.
   - A left facet rail in order: Category (Overall, Fullstack, Frontend, Technology), then Domain, then a Score Range slider.
   - Models | Labs sub-tabs, and a Votes column so the sample size is visible.

4. **Terminal-Bench leaderboard** (table with three views). Steal:
   - A TABLE | PARETO | WAFFLE switch on one dataset.
   - "Copy filters link" (shareable view state) and "Export view" as toolbar icons.
   - A Columns chooser, and AGENT as its own column so the harness is ranked, not just the model.
   - The +/- CI in muted text beside each bold resolution rate.

5. **Cursor Directory** (ranked plugin cards). Steal:
   - A large rank digit on each card, a Verified badge where earned, and the install count on the right.
   - Sort tabs Trending | Top | New under the search field.
   - The developer count ("90.4k+ developers") as a social proof line in the one-sentence hero.

Runners-up worth a single steal each:
- **LobeHub skills**: "I'm an Agent / I'm a Human" toggle with an agent-first prompt box.
- **claude-plugins.dev**: Quick Start with copy-paste install / list / enable lines and owner-scoped ids (`@owner/marketplace`) in mono.
- **Artificial Analysis coding agents**: "agent - model (effort)" bar labels, and Cost per Task / Cost to Run panels beside quality.
- **Smithery**: verified badge plus "N uses" on each card, and one "Add to toolbox" button.

## Gaps and caveats
- HAL did not render; retry from a fresh camofox session before using it.
- The AA insights URL returns 404; the working page is /agents/coding-agents.
- Smithery's header "715" has no label in the snapshot, and Glama's grade badge (from the blind map) was not seen; check both before quoting.
- skillsmp shows several unlabelled counts (3,497,595 collected SKILL.md files is the hero figure).
- Scale's "Performance Comparison" list mixes model generations; treat as a snapshot.
