#!/usr/bin/env python3
"""compact-window-sim: what would each auto-compact window have cost on our real Opus chats? (price only, not quality)

  compact-window-sim [--days 7] [--base 50000] [--summary 8000]

Replays every main Opus 5.5 chat: the context grows by each call's real growth; when it passes the window W, a
compaction happens (one call reading the whole context plus a summary of --summary output tokens), and the context
drops to --base tokens (system prompt + summary + re-read files; our measured median after a compaction is ~50k),
which is written to the 1h cache again. Every call reads the cached prefix ($0.20/M) and writes its growth ($8/M);
output is the same in every arm and left out. Shaan, 12 Oct: "we've gotta make potentially a better way of
auto-compacting". Quality (context rot) is not in this number; see .agents/runs/2026-10-12-harness/README.md.
"""
import argparse, glob, os, time
import importlib.util

spec = importlib.util.spec_from_file_location("ttl", os.path.join(os.path.dirname(__file__), "cache-ttl-sim.py"))
ttl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ttl)
RD, W1H, OUT = 0.20, 8.0, 20.0  # Opus 5.5 $/M: cache read, 1h cache write, output


def sim(cs, window, base, summary):
    usd, comps, ctx, prev = 0.0, 0, None, None
    for ts, model, p, _ in cs:
        if ctx is None:
            ctx, prev = p, p
            usd += p * W1H / 1e6
            continue
        grow = max(0, p - prev) if p >= prev * 0.6 else 0  # a real compaction drops p; don't count the drop as growth
        prev = p
        if ctx + grow > window:
            usd += (ctx * RD + summary * OUT + base * W1H) / 1e6
            comps += 1
            ctx = base
        usd += (ctx * RD + grow * W1H) / 1e6
        ctx += grow
    return usd, comps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--base", type=int, default=50000)
    ap.add_argument("--summary", type=int, default=8000)
    a = ap.parse_args()
    since = time.time() - a.days * 86400
    files = set()
    for r in ttl.tw.ROOTS:
        for x in glob.glob(r + "/projects/**/*.jsonl", recursive=True):
            try:
                if "/subagents/" not in x and os.path.getmtime(x) >= since:
                    files.add(os.path.realpath(x))
            except OSError:
                pass
    chats = [cs for cs in ([c for c in ttl.calls(f) if c[0] >= since and "opus-5" in (c[1] or "")] for f in files) if len(cs) > 5]
    print(f"{len(chats)} Opus 5.5 chats, {sum(map(len, chats))} calls, last {a.days:g} days; prompt-side list price")
    print(f"{'window':>8}{'cost':>9}{'compactions':>13}{'vs 300k':>9}")
    rows = {w: [0.0, 0] for w in (100_000, 150_000, 200_000, 300_000, 500_000, 967_000)}
    for cs in chats:
        for w in rows:
            u, c = sim(cs, w, a.base, a.summary)
            rows[w][0] += u
            rows[w][1] += c
    ref = rows[300_000][0]
    for w, (u, c) in rows.items():
        print(f"{w // 1000:>7}k{u:9.0f}{c:13}{(u / ref - 1) * 100:+8.0f}%")


if __name__ == "__main__":
    main()
