#!/usr/bin/env python3
"""crash.py: what a crash or restart cost. Counts and $ only.

Agent Zero, 15 Oct: "count the turns killed by today's crashes and restarts (13:02, 13:07, 14:26-14:34) and what they
cost in re-reads after resuming."

  crash.py --crash 2026-10-15T13:02+07:00 --crash 2026-10-15T13:07+07:00 --crash 2026-10-15T14:26+07:00/14:34

A session counts as killed when it made an API call in the 10 min before the crash and its turn had not ended (the
last call before the crash asked for a tool). After the crash: did it resume, the first call's cache write (the
context rebuilt), and in the next 30 min the calls that re-read a file it had read before the crash, plus all
read-only calls (finding its place again).
"""
import argparse, datetime as dt, glob, importlib.util, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("seat", os.path.join(HERE, "seat.py"))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
L, LP = S.L, S.LP


def parse(w):
    a, _, b = w.partition("/")
    t0 = dt.datetime.fromisoformat(a).timestamp()
    if not b:
        return a[11:16], t0, t0
    end = dt.datetime.fromisoformat(a[:11] + b + a[16:]).timestamp()
    return a[11:16] + "-" + b, t0, end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crash", action="append", required=True)
    a = ap.parse_args()
    seats = L.seat_map()
    files = [f for root in L.LOGINS.values() for f in glob.glob(root + "/*/*.jsonl")]
    print("| crash | sessions killed | resumed | never resumed | rebuild write $ | re-reads after (calls, $) | "
          "read-only in 30 min after (calls, $) |\n|---|---|---|---|---|---|---|")
    tot = 0.0
    for w in a.crash:
        name, c0, c1 = parse(w)
        killed = resumed = 0
        wr = rr_n = rr_usd = ro_n = ro_usd = 0.0
        who = []
        for f in files:
            if os.path.getmtime(f) < c0 - 600:
                continue
            cs = S.session(f, c0 - 6 * 3600, c1 + 4 * 3600)
            for c in cs:
                L.cost(c)
            before = [c for c in cs if c["ts"] < c0]
            if not before or before[-1]["ts"] < c0 - 600 or not before[-1]["uses"]:
                continue
            killed += 1
            who.append(seats.get(os.path.basename(f)[:-6], os.path.basename(f)[:8])[:28])
            seen = set()
            for c in before:
                for n, i in c["uses"]:
                    seen.update(S.read_paths(n, i))
            after = [c for c in cs if c["ts"] > c1]
            if not after:
                continue
            resumed += 1
            wr += after[0]["usd"]["write"]
            for c in after:
                if c["ts"] > after[0]["ts"] + 1800:
                    break
                names = [n for n, _ in c["uses"]]
                if any(p in seen for n, i in c["uses"] for p in S.read_paths(n, i)):
                    rr_n += 1
                    rr_usd += c["total"]
                if names and all(n in L.tw.FETCH for n in names) and all(
                        n != "Bash" or LP.reads_only(i.get("command", "")) for n, i in c["uses"]):
                    ro_n += 1
                    ro_usd += c["total"]
        tot += wr + ro_usd + rr_usd
        print(f"| {name} | {killed} | {resumed} | {killed - resumed} | {wr:,.2f} | {rr_n:.0f}, ${rr_usd:,.2f} | "
              f"{ro_n:.0f}, ${ro_usd:,.2f} |")
        print(f"|  ↳ {', '.join(who[:8])}{' …' if len(who) > 8 else ''} | | | | | | |")
    print(f"\nupper bound of what the crashes cost (rebuild + re-reads + read-only after; overlaps): ${tot:,.2f}")


if __name__ == "__main__":
    main()
