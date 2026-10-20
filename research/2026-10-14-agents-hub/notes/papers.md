# Papers slice (found_by: papers), 14 Oct 2026

38 rows in rows/papers.jsonl. Most numbers come from arXiv abstracts or search snippets; rows say which. verified is null everywhere.

## Grouped findings

**Skills (ecosystem and value)**
- 26.1% of 31,132 marketplace skills carry a vulnerability; script-bundling skills are 2.12x as likely (2601.10338).
- Scanners over-flag: marketplace scanners call up to 46.8% malicious, repo context cuts that to 0.52% (2603.16572, snippet).
- Skill value is uneven: curated skills +16.2 pp on SkillsBench, self-written skills about 0 (2602.12670); 39 of 49 SWE skills gave no gain and some raised token cost up to 451% (2603.15401).
- Skill-library lineage: Voyager (2305.16291) to SkillWeaver (2504.07079, +31.8% and +39.8% relative; strong-agent APIs lift weak agents up to 54.3%).

**MCP (security, ecosystem, retrieval)**
- Tool poisoning works on most agents: o1-mini 72.8% attack success, refusals under 3% (MCPTox 2508.14925).
- Ecosystem quality is poor: more than half of listed projects invalid or low value (2509.25292); a random registry draw has 48.8% initialize success vs 66.7% for curated (2609.10962, snippet).
- Retrieval is the bottleneck at scale: retrieval errors account for nearly half of LiveMCPBench failures (2508.01780, third-party read); top model 78.95%.

**Failure, long horizon, evaluation**
- Multi-agent failures are mostly design, not model: 14 modes, kappa 0.88 (MAST 2503.13657).
- Degradation follows step count: per-step reliability sets a geometric decay, and capping context steepened it (2609.01660). Treat blanket context truncation as suspect.
- Horizon measurement: METR 50% horizon doubles about every 7 months (2503.14499). BFCL (PMLR, no arXiv) says memory and long-horizon remain open.

**Self-improvement and prompt/context optimisation**
- DGM: archive-based empirical self-rewrite takes SWE-bench 20% to 50% with models frozen (2505.22954).
- ACE: playbook with delta updates avoids context collapse; +10.6% agents, +8.6% finance (2510.04618).
- GEPA: language reflection beats GRPO by up to 20% with up to 35x fewer rollouts (2507.19457, v2). DSPy (2310.03714) is the base idea.

**Memory and harness**
- Mem0 cuts p95 latency 91% and token cost over 90% vs full context (2504.19413). A-MEM (2502.12110) lets new memories rewrite old notes. MemGPT (2310.08560) gives the core vs archival split.
- Harness ablations (2609.00006): long-term memory +5.6 pp, tools +3.3 pp, middleware +2.2 pp; a bare system prompt -2.3 pp.

## The 5 most useful principles
1. Treat every skill or MCP tool description as code-level trust: most bundled-script skills and most tool-poisoning cases are unsafe by default (2601.10338, 2508.14925).
2. Prune by measured gain: most skills and tools add nothing and some cost tokens; keep a skill only if its pass-rate delta is positive (2603.15401, 2602.12670).
3. Retrieval, not execution, limits tool use at scale; invest in tool search and query-specific refinement (2508.01780, 2604.04323).
4. Failures are system-design failures: audit the harness and the protocol before the model (2503.13657, 2609.00006).
5. Improve prompts and context with language feedback and small deltas, not rewrites or RL rollouts (2507.19457, 2510.04618).

## Gaps
- No primary-source read for SkillWeaver, A-MEM, Gorilla, MemGPT, MCP-Zero, MCPVerse and most 2026 security papers; numbers are snippet-level.
- No 2026 controlled study on edit or search tool design in coding harnesses was found (SWE-agent and OpenHands are 2024).
- METR Time Horizon 1.1 (Jan 2026) figures are on METR's site, not checked.
- MIPROv2 (arXiv 2406.11695 per a secondary source) and ToolSearcher (reported on arXiv Sep 2026) not checked.
- Vendor blogs are out of scope for this slice.
