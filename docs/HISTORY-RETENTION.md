# Harness history retention (seam 7)

Owner: agent stack (siso-harness-lab). Placement and the vault move: the workspace organiser, after "checkpoint: go"
in `docs/operations/restructure-2026-09-23/COORDINATION.md`. Measured 2026-09-23 with the disk at 94% (29 GB free).
Nothing is deleted except caches proven rebuildable: Shaan keeps his history (`cleanupPeriodDays: 99999`), and his
transcripts are raw material for recall.

## Who reads history

| Reader | Reads | Window |
|---|---|---|
| `scripts/corrections.py`, `scripts/audit.py` | Claude `~/.claude/projects/**/*.jsonl`, Codex `~/.codex/sessions/**` | 14 days (default) |
| `hooks/closeout-check.mjs`, checkpoint hooks | the current session's transcript | live |
| `hooks/project-memory.mjs` | `~/.claude/projects/*/memory` (links into repos), not transcripts | live |
| `claude --resume`, `codex resume` | the session's own transcript or rollout | as far back as you resume |
| `cold_quiz.py` | nothing: it starts fresh agents | — |

So the instruments need 14 days hot. Everything older is read only by a human resuming or researching, and that works
from the archive once restored.

## The rule

| Class | What | Rule |
|---|---|---|
| **Hot** | Claude transcripts and Codex rollouts modified in the last **15 days** (the 14-day window plus a day of margin); all of `~/.omp/agent/sessions` (74 MB) | Stay in place, untouched. |
| **Archive** | Claude transcripts older than 15 days, with each session's sidecar folder (`subagents/`, `tool-results/`); Codex rollouts in `~/.codex/sessions/YYYY/MM/DD` older than 15 days; Claude job folders in `~/.claude/jobs` not updated for 7 days and not running | Move to the vault, one gzip file per original, same relative path, plus a manifest line per file (original path, bytes, sha256 of the original). Leave `ARCHIVE.md` in the source folder naming the vault path. Never upload it to a third-party service, because transcripts can contain secrets. |
| **Rebuildable cache** | `~/.omp/agent/cache/tiny-models` (7.1 GB): seven ONNX models downloaded 19 Sep 08:31–08:35 and never read since (atime = download time); omp's `smol` role is `opencode-go/deepseek-v4.1-flash`, not a local model. `~/.codex/.tmp` (203 MB). | Delete after the proof below. |
| **Hold** | `~/.codex/thread_history_1.sqlite` (8.7 GB) and `~/.codex/logs_2.sqlite` (1.5 GB): live Codex databases. The first is a projection of the rollouts (`thread_history_projection_state` stores per-thread byte offsets), so it is probably rebuildable, but that is not proven. | Do not touch while any Codex process runs, and not at all until a throwaway-home test proves Codex recreates and re-projects it. That test must not copy `auth.json`. |
| **Not history** | `~/.codex/generated_images` (2.9 GB, image work), `~/.codex/site-archives` (941 MB, BykonzYard deploy tarballs), `~/.codex/worktrees` (1.7 GB, live checkouts) | Out of seam 7; they belong to their owning lanes (S7 zone table). |
| **Never move** | `~/.claude/projects/*/memory` (links into repos), settings, skills, agents, hooks, `~/.codex/{config.toml,*.config.toml,AGENTS.md,auth.json,hooks.json,skills}`, `~/.codex/{state_5,goals_1,memories_1,queue_1}.sqlite`, `~/.omp/agent/{AGENTS.md,config.yml,natives}` | Configuration and live state. |

Sizes on 23 Sep: Claude transcripts 3.8 GB (2.1 GB under 14 days), Codex rollouts 15 GB (7.7 GB under 14 days,
about 0.55 GB a day), jobs 2.2 GB (the 2.1 GB job 27b44e91 has been idle since 10 Sep; its `tmp/` holds about 1,800
images and 100 `.opus` audio files, which may be Shaan's voice notes, so it goes to the vault intact and is never
deleted). The first pass archives about 12 GB and deletes 7.1 GB of models.

## How to move (organiser)

1. Select by mtime against the 15-day line. Skip anything a live process has open.
2. For each file: `gzip -9` into the vault path, `gzip -t`, compare the sha256 of the decompressed stream with the
   original's, append the manifest line, and only then remove the original.
3. Before and after the move, run `python3 scripts/corrections.py --days 14`: the counts must match exactly, because
   the hot window is untouched. The cold quiz must stay 72/72.
4. Models: rename `tiny-models` aside while no omp session runs, then run `omp -p --model smol "reply ok"`. If that
   works, delete the folder. If omp needs one of them, it downloads it again.
5. Restore one session: `gunzip -c <vault>/<path>.gz > <original path>`, then resume as normal.
