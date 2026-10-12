#!/usr/bin/env python3
"""cache-ttl-sim: would 5-minute or 1-hour prompt caching have been cheaper, replayed on our real calls?

  cache-ttl-sim [--days 7] [--by seat|model|kind]

Every API call in the transcripts has a prompt size (input + cache read + cache write) and a timestamp. Replay each
transcript in order under a TTL: if the gap since the previous call is within the TTL, the previous prompt is a cache
read and only the new tail is written; otherwise the whole prompt is written again. Writes cost 1.25x input at 5m and
2x at 1h; reads 0.05x (Opus 5.5, Haiku 5.5) or 0.1x. Output is the same both ways and left out. Also replays "mixed":
1h for main chats, 5m for sub-agents (CLAUDE_CODE_PROMPT_CACHE_TTL is per process, so a seat could run that way).
Shaan, 12 Oct: "I'm pretty sure increasing the cache limit might help but I'm not sure how to test this".
"""
import argparse, glob, json, os, re, time
from collections import defaultdict
import importlib.util

spec = importlib.util.spec_from_file_location("tw", os.path.join(os.path.dirname(__file__), "token-where.py"))
tw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tw)


def calls(f):
    """(ts, model, prompt tokens, actual cost of the prompt side) per unique message id, in order."""
    out, seen = [], set()
    for line in open(f, errors="ignore"):
        if '"type":"assistant"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        m = o.get("message") or {}
        u, mid = m.get("usage"), m.get("id")
        if not u or mid in seen or m.get("model", "").startswith("<"):
            continue
        seen.add(mid)
        try:
            ts = time.mktime(time.strptime(o.get("timestamp", "")[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
        except ValueError:
            continue
        inp, rd, cw = u.get("input_tokens", 0), u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0)
        w1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0)
        p = inp + rd + cw
        r_in, r_w5, r_w1, r_rd, _ = tw.price(m.get("model"), p)
        actual = (inp * r_in + (cw - w1h) * r_w5 + w1h * r_w1 + rd * r_rd) / 1e6
        out.append((ts, m.get("model"), p, actual))
    return out


def replay(cs, ttl):
    usd, prev_ts, prev_p = 0.0, None, 0
    for ts, model, p, _ in cs:
        r_in, r_w5, r_w1, r_rd, _ = tw.price(model, p)
        w = r_w5 if ttl == 300 else r_w1
        hit = prev_ts is not None and ts - prev_ts <= ttl
        rd = min(prev_p, p) if hit else 0
        usd += (rd * r_rd + (p - rd) * w) / 1e6
        prev_ts, prev_p = ts, p
    return usd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--by", default="kind", choices=["seat", "model", "kind"])
    a = ap.parse_args()
    since = time.time() - a.days * 86400
    files = set()
    for r in tw.ROOTS:
        for x in glob.glob(r + "/projects/**/*.jsonl", recursive=True):
            try:
                if os.path.getmtime(x) >= since:
                    files.add(os.path.realpath(x))
            except OSError:
                pass
    tot = defaultdict(lambda: [0.0, 0.0, 0.0, 0, 0])  # key -> actual, 5m, 1h, calls, gaps 5-60 min
    for f in files:
        cs = [c for c in calls(f) if c[0] >= since]
        if not cs:
            continue
        sub = "/subagents/" in f
        model = cs[-1][1] or "?"
        key = {"kind": "sub-agent" if sub else "main chat", "model": re.sub(r"^claude-|\[.*", "", model),
               "seat": "sub-agent" if sub else tw.seat(os.path.dirname(f).rsplit("/projects/", 1)[-1].replace("-", "/"))}[a.by]
        t = tot[key]
        t[0] += sum(c[3] for c in cs)
        t[1] += replay(cs, 300)
        t[2] += replay(cs, 3600)
        t[3] += len(cs)
        t[4] += sum(1 for x, y in zip(cs, cs[1:]) if 300 < y[0] - x[0] <= 3600)
    print(f"Prompt-side cost (no output), last {a.days:g} days, list prices. 'gaps' = calls 5-60 min after the previous one.")
    print(f"{'':16}{'actual':>10}{'all 5m':>10}{'all 1h':>10}{'calls':>9}{'gaps':>7}")
    s = [0.0, 0.0, 0.0, 0, 0]
    for k, t in sorted(tot.items(), key=lambda kv: -kv[1][0]):
        print(f"{k[:15]:16}{t[0]:10.0f}{t[1]:10.0f}{t[2]:10.0f}{t[3]:9}{t[4]:7}")
        s = [x + y for x, y in zip(s, t)]
    print(f"{'TOTAL':16}{s[0]:10.0f}{s[1]:10.0f}{s[2]:10.0f}{s[3]:9}{s[4]:7}")
    if a.by == "kind":
        main_ = tot.get("main chat", [0] * 5)
        subs = tot.get("sub-agent", [0] * 5)
        print(f"mixed (main 1h, sub-agents 5m): {main_[2] + subs[1]:.0f}")


if __name__ == "__main__":
    main()
