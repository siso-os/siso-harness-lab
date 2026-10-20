# 08 papers: five strongest numbers

1. Complexity Trap (arXiv 2508.21433): observation masking cut SWE-agent cost 50.9% to 57.1% across 5 configs, and solve rate moved -11.8% to +8.5% relative; LLM summarization cut 41.5% to 55.4% and adds a 0.65% to 7.2% summarizer overhead.
2. Anthropic context management (claude.com/blog/context-management): context editing cut token use 84% in a 100-turn web-search eval; +29% alone, +39% with the memory tool (vendor-reported, no threshold given).
3. Anthropic multi-agent research (anthropic.com/engineering/multi-agent-research-system): agents use about 4x chat tokens, multi-agent about 15x; token use explains 80% of variance; +90.2% performance over single Opus 4.
4. ACON (arXiv 2510.00615): peak tokens down 26% to 54%; AppWorld cost per task $0.331 to $0.272 (about -18%); distilled compressor at $0.0004 per example vs $0.045 (-99.1%) keeps over 95% of teacher accuracy.
5. Memory condensation eval (arXiv 2605.18854): observation masking -8.6% tokens per task, LLM summarizing +23.6% tokens; heuristic condensers 100% completion vs LLM 93% to 98%; no significant quality difference (60 tasks, GPT-4o only).

Gap for (b) compaction thresholds: none of the sources gives a validated trigger point. The fixed settings used were masking window M=10, summary N=21 with M=10 tail, and max_size=8 on short tasks. Our own trigger needs measurement with the usage instruments.
