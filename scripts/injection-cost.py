#!/usr/bin/env python3
"""injection-cost: what do the things the harness adds to a conversation (reminders, hook output, listings) cost?

  injection-cost [--days 2]

Claude Code records every injected block as an `attachment` entry in the transcript (it reaches the model as a
system reminder). An injected token is paid once as a 1h cache write and then as a cache read on every later call
until the next compaction. This walks each main transcript in order and charges each injection that way, at the
session's own model prices, grouped by kind (hook output by hook). Size is JSON chars / 4, a slight overestimate.
George (via Shaan, 12 Oct): "we might be burning extra tokens for maybe hooks or something".
"""
import argparse, glob, json, os, re, time
from collections import defaultdict
import importlib.util

spec = importlib.util.spec_from_file_location("tw", os.path.join(os.path.dirname(__file__), "token-where.py"))
tw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tw)
NOT_SENT = {"prompt_snapshot", "hook_success", "queued_command"}  # transcript records / Shaan's own words, not overhead


def kind(a):
    t = a.get("type") or "?"
    if t == "hook_additional_context":
        cmd = str(a.get("command") or a.get("hookName") or "")
        return "hook: " + (os.path.basename(cmd.split()[-1]) if cmd.split() else a.get("hookName", "?"))[:40] + f" ({a.get('hookEvent') or a.get('hookName', '')})"[:40]
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=2)
    a = ap.parse_args()
    since = time.time() - a.days * 86400
    cost, toks, n = defaultdict(float), defaultdict(float), defaultdict(int)
    total = 0.0
    for r in tw.ROOTS:
        for f in glob.glob(r + "/projects/*/*.jsonl"):
            try:
                if os.path.getmtime(f) < since:
                    continue
            except OSError:
                continue
            live, seen = defaultdict(float), set()
            for line in open(f, errors="ignore"):
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("timestamp", "") and time.mktime(time.strptime(o["timestamp"][:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone < since:
                    continue
                if o.get("type") == "system" and o.get("subtype") == "compact_boundary":
                    live = defaultdict(float)
                    continue
                at = o.get("attachment")
                if at and at.get("type") not in NOT_SENT:
                    k, t = kind(at), len(json.dumps(at)) / 4
                    live[k] += t
                    toks[k] += t
                    n[k] += 1
                    continue
                if o.get("type") == "assistant":
                    m = o.get("message") or {}
                    u = m.get("usage")
                    if not u or m.get("id") in seen:
                        continue
                    seen.add(m.get("id"))
                    p = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                    r_in, r_w5, r_w1, r_rd, r_out = tw.price(m.get("model"), p)
                    total += (u.get("input_tokens", 0) * r_in + u.get("cache_read_input_tokens", 0) * r_rd + u.get("cache_creation_input_tokens", 0) * r_w1 + u.get("output_tokens", 0) * r_out) / 1e6
                    for k, t in live.items():
                        cost[k] += t * r_rd / 1e6
                    # first carry of a fresh injection is a cache write, not a read
            # charge each injection's one write at the 1h rate of the session's main model (Opus 5.5 $8/M)
            # (approximation: done once per injected token)
    for k in toks:
        cost[k] += toks[k] * 8 / 1e6
    print(f"Main-chat cost {a.days:g} days (list): ${total:,.0f}. Injected blocks, write + carry until compaction:")
    print(f"{'kind':48}{'count':>8}{'tokens':>11}{'cost':>9}{'share':>7}")
    for k, c in sorted(cost.items(), key=lambda kv: -kv[1])[:20]:
        print(f"{k[:47]:48}{n[k]:8}{toks[k]:11.0f}{c:9.2f}{c / total * 100:6.1f}%")
    s = sum(cost.values())
    print(f"{'ALL INJECTED':48}{sum(n.values()):8}{sum(toks.values()):11.0f}{s:9.2f}{s / total * 100:6.1f}%")


if __name__ == "__main__":
    main()
