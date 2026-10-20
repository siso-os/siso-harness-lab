#!/usr/bin/env python3
"""shape.py: what one day of spend is made of, and what each big lever would save. Counts and $ only.

Shaan, 16 Oct: "we crash through 30% on a standard day ... how can we optimize this to be like three times less and
we still got the same amount of work done?"

  shape.py [--hours 24]

Splits the window's Claude $ into: the fixed floor every call re-reads (system prompt, tools, brain, skill list),
the context above it, cache writes, output; and by seat class (owner seats vs Lane workers vs sub-agents). Then prices
each lever on the same calls: workers on Sonnet or Haiku, a smaller floor, a context cap with fresh sessions, 5-min
cache on workers.
"""
import argparse, collections, importlib.util, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ledger", os.path.join(HERE, "ledger.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)


def klass(c, seats):
    if c["sub"]:
        return "sub-agent"
    name = seats.get(c["session"], "")
    return "worker lane" if "lane" in name.lower() else "owner seat" if name else "unnamed"


def reprice(c, model, ctx=None):
    t = c["tok"]
    r_in, r_w5, r_w1, r_rd, r_out = L.tw.price(model, ctx if ctx is not None else c["ctx"])
    w1 = c["w1"]
    return (t["in"] * r_in + (t["write"] - w1) * r_w5 + w1 * r_w1 + t["read"] * r_rd + t["out"] * r_out) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    t1 = time.time()
    calls = L.scan(t1 - a.hours * 3600, t1)
    seats = L.seat_map()
    for c in calls:
        L.cost(c)
    tot = sum(c["total"] for c in calls)
    by_sess = collections.defaultdict(list)
    for c in calls:
        by_sess[c["file"]].append(c)
    floor = {}
    for f, cs in by_sess.items():
        cs.sort(key=lambda c: c["ts"])
        floor[f] = min(c["ctx"] for c in cs[:5])
    main_opus = [c for c in calls if not c["sub"] and "opus" in c["model"]]
    pc = lambda v: f"${v:,.0f} ({v / tot:.0%})"
    print(f"# {a.hours:g} h: ${tot:,.0f} over {len(calls):,} calls ({len(main_opus):,} Opus main)\n")

    print("## By seat class\n| class | $ | calls | avg ctx | $/call |\n|---|---|---|---|---|")
    g = collections.defaultdict(list)
    for c in calls:
        g[klass(c, seats)].append(c)
    for k, cs in sorted(g.items(), key=lambda x: -sum(c["total"] for c in x[1])):
        s = sum(c["total"] for c in cs)
        print(f"| {k} | {pc(s)} | {len(cs):,} | {sum(c['ctx'] for c in cs) / len(cs) / 1000:.0f}k | {s / len(cs):.3f} |")

    rd = sum(c["usd"]["read"] for c in main_opus)
    fl = sum(min(floor[c["file"]], c["tok"]["read"]) * c["r_rd"] / 1e6 for c in main_opus)
    fls = sorted(floor[f] for f, cs in by_sess.items() if not cs[0]["sub"] and "opus" in cs[0]["model"])
    print(f"\n## What an Opus main call pays for\n- cache read {pc(rd)}: the fixed floor (first-call context, median "
          f"{fls[len(fls) // 2] / 1000:.0f}k) is {pc(fl)}; the conversation above it {pc(rd - fl)}")
    print(f"- cache write {pc(sum(c['usd']['write'] for c in main_opus))}, of it 1-hour cache "
          f"{pc(sum(c['w1'] * 8 / 1e6 for c in main_opus))}")
    print(f"- output (incl. thinking) {pc(sum(c['usd']['out'] for c in main_opus))}, "
          f"{sum(c['tok']['out'] for c in main_opus) / len(main_opus):,.0f} tokens per call")

    print("\n## Levers, priced on these same calls\n| lever | saves $/day | share |\n|---|---|---|")
    lanes = g["worker lane"]
    for model in ("claude-sonnet-5-5", "claude-haiku-5-5"):
        s = sum(c["total"] - reprice(c, model) for c in lanes)
        print(f"| worker lanes on {model.split('-')[1].title()} 5.5 | {s:,.0f} | {s / tot:.0%} |")
    owners = g["owner seat"] + g["unnamed"]
    s = sum(c["total"] - reprice(c, "claude-sonnet-5-5") for c in owners)
    print(f"| owner seats on Sonnet 5.5 too | {s:,.0f} | {s / tot:.0%} |")
    for cut in (10_000, 20_000):
        s = sum(min(cut, c["tok"]["read"]) * c["r_rd"] / 1e6 for c in main_opus)
        print(f"| floor {cut // 1000}k smaller | {s:,.0f} | {s / tot:.0%} |")
    for cap in (80_000, 120_000):
        saved = resets = 0.0
        for f, cs in by_sess.items():
            if cs[0]["sub"]:
                continue
            over = False
            for c in cs:
                if c["ctx"] > cap:
                    saved += (c["ctx"] - cap) * c["r_rd"] / 1e6
                    if not over:
                        resets += 1
                over = c["ctx"] > cap
        cost = resets * (floor_med := fls[len(fls) // 2] + 15_000) * 8 / 1e6
        print(f"| fresh session at {cap // 1000}k (notes carry over) | {saved - cost:,.0f} | {(saved - cost) / tot:.0%} |")
    s = sum(c["w1"] * 3 / 1e6 for c in lanes)
    print(f"| 5-min cache on worker lanes (before cold re-writes) | {s:,.0f} | {s / tot:.0%} |")


if __name__ == "__main__":
    main()
