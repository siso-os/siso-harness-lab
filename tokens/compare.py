#!/usr/bin/env python3
"""compare.py: did a change help? The same clock window before and after it, Opus main conversations, counts only.

Shaan, 15 Oct: "try this out please and see what you improved and how it helps".

  compare.py --at 2026-10-14T15:17:20Z            # after = --at..now, before = the same hours 24 h earlier
  compare.py --at ... --before-days 7             # or a week earlier (same weekday)

Per window: calls, $, $/call, avg and max context, calls over 250k, compactions, read-only calls, runs of 3+, rr and
Serena use, and how often the spend-glance and fetch-nudge texts were injected. Never prints message text.
"""
import argparse, glob, importlib.util, json, os, re, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("loops", os.path.join(HERE, "loops.py"))
LP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LP)
L = LP.L

MARKS = {"spend-glance text": "Budget before you launch", "fetch-nudge text": "read/search/command calls in a row",
         "compactions": '"compact_boundary"'}


def marks(t0, t1):
    n = dict.fromkeys(MARKS, 0)
    for root in L.LOGINS.values():
        for f in glob.glob(root + "/*/*.jsonl"):
            if os.path.getmtime(f) < t0:
                continue
            for line in open(f, errors="replace"):
                hit = [k for k, m in MARKS.items() if m in line]
                if not hit:
                    continue
                ts = re.search(r'"timestamp":"([^"]+)"', line)
                if ts and t0 <= L.iso(ts.group(1)) < t1:
                    for k in hit:
                        n[k] += 1
    return n


def window(t0, t1):
    calls = LP.scan(t0, t1)
    for c in calls:
        L.cost(c)
    calls.sort(key=lambda c: (c["file"], c["ts"]))
    ro_flags, runs, cur, last = [], 0, 0, None
    rr = serena = 0
    for c in calls:
        cmds = [i.get("command", "") for n, i, _ in c["uses"] if n == "Bash"]
        rr += sum(bool(re.match(r"\s*(cd [^;&|]+&&\s*)?rr\s", x)) for x in cmds)
        serena += sum("serena" in x for x in cmds) + sum("serena" in (n or "").lower() for n in c["tools"])
        ro = bool(c["uses"]) and all(n in L.tw.FETCH for n in c["tools"]) and all(
            n != "Bash" or LP.reads_only(i.get("command", "")) for n, i, _ in c["uses"])
        ro_flags.append(ro)
        if c["file"] != last:
            runs += cur >= 3
            cur, last = 0, c["file"]
        if ro:
            cur += 1
        else:
            runs += cur >= 3
            cur = 0
    runs += cur >= 3
    usd = sum(c["total"] for c in calls)
    n = len(calls) or 1
    out = {"Opus calls": len(calls), "$": round(usd), "$ per call": round(usd / n, 3),
           "avg context k": round(sum(c["ctx"] for c in calls) / n / 1000),
           "max context k": round(max((c["ctx"] for c in calls), default=0) / 1000),
           "calls over 250k": sum(c["ctx"] > 250_000 for c in calls),
           "read-only calls %": round(100 * sum(ro_flags) / n), "runs of 3+ reads": runs,
           "rr calls": rr, "Serena calls": serena}
    out.update(marks(t0, t1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", required=True, help="when the change went live (ISO, UTC)")
    ap.add_argument("--before-days", type=float, default=1)
    a = ap.parse_args()
    t_at, now = L.iso(a.at), time.time()
    shift = a.before_days * 86400
    after, before = window(t_at, now), window(t_at - shift, now - shift)
    print(f"window {(now - t_at) / 3600:.1f} h; before = same hours {a.before_days:g} day(s) earlier\n")
    print("| | before | after |\n|---|---|---|")
    for k in after:
        print(f"| {k} | {before[k]:,} | {after[k]:,} |")
    print(json.dumps({"before": before, "after": after}))


if __name__ == "__main__":
    main()
