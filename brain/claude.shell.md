## Claude Code
- **Context is the cost.** Batch independent calls. Read windows, not whole files. Don't re-read what you have.
- **Delegation:** no Claude sub-agents (the Agent tool), ever: Shaan, 4 Oct, "no opus sub-agents ... no clawed sub-agents". Do it yourself, or hand it to Codex Sol 6.1 (`codex-run`; Shaan, 4 Oct: "stop using Luna, just use Sol 6.1").
- **Compaction:** compact at a clean break (`self-compact`) after writing `.agents/HANDOFF.md`.
- **Waiting:** wait on one event (a background command, a task notification), never a polling loop.
