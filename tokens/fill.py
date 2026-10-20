#!/usr/bin/env python3
"""fill.py: what fills an Opus context, by block type and tool (chars/4, images 1,600 tokens). Counts only, no text.

Shaan, 14 Oct: "maybe there's a way to get context to fill up slower".
  fill.py [--hours 24]
"""
import argparse, glob, importlib.util, json, os, time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("loops", os.path.join(HERE, "loops.py"))
LP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LP)
L = LP.L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    t0 = time.time() - a.hours * 3600
    T = defaultdict(float)
    names = {}
    for root in L.LOGINS.values():
        for f in glob.glob(root + "/*/*.jsonl"):
            if os.path.getmtime(f) < t0:
                continue
            opus = False
            for line in open(f, errors="replace"):
                try:
                    d = json.loads(line)
                    if L.iso(d.get("timestamp", "1970-01-01T00:00:00Z")) < t0:
                        continue
                except ValueError:
                    continue
                m = d.get("message") or {}
                if d.get("type") == "assistant":
                    opus = "opus" in (m.get("model") or "")
                    if not opus:
                        continue
                    for b in m.get("content") or []:
                        if not isinstance(b, dict):
                            continue
                        t = b.get("type")
                        if t == "text":
                            T["out: text to the user/narration"] += len(b.get("text") or "")
                        elif t == "tool_use":
                            names[b.get("id")] = b.get("name")
                            T["out: tool call input: " + str(b.get("name"))] += len(json.dumps(b.get("input") or {}))
                elif d.get("type") == "user" and opus:
                    c = m.get("content")
                    if isinstance(c, str):
                        T["in: typed prompt or injected text"] += len(c)
                        continue
                    for b in c or []:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "tool_result":
                            T["in: result of " + str(names.get(b.get("tool_use_id")))] += LP.chars(b.get("content"))
                        elif b.get("type") == "text":
                            T["in: typed prompt or injected text"] += len(b.get("text") or "")
                        elif b.get("type") == "image":
                            T["in: image"] += 6400
                elif d.get("type") == "attachment" and opus:
                    T["in: attachment (reminders, listings, hook text)"] += len(json.dumps(d.get("attachment") or {}))
    tot = sum(T.values())
    print(f"Opus main context growth, last {a.hours:g} h: {tot/4/1e6:.1f}M tokens (chars/4; thinking not included)\n")
    print("| what | M tokens | share |\n|---|---|---|")
    for k, v in sorted(T.items(), key=lambda kv: -kv[1])[:22]:
        print(f"| {k} | {v/4/1e6:.2f} | {v/tot:.0%} |")


if __name__ == "__main__":
    main()
