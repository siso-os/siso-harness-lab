#!/usr/bin/env python3
"""ship-latency — how long built work waits before it is live, from git and a list of deploys.

Shaan, 3 Oct ~01:30: "Is there not a more efficient way to run this? ... whatever the bottlenecks are we should be solving".
For each deploy (sha, the time it went live), every lane commit that became live in it (non-merge commits in prev..sha)
gets three times: built (its committer time), merged (the committer time of the earliest first-parent commit of the
deployed sha that contains it: when it reached the integration line) and live (the deploy). Read-only.

  ship-latency.py --repo DIR --deploys FILE [--json]
FILE: one deploy per line, "<sha> <ISO time or HH:MM on --day>" in time order (or a JSON-lines deploy log with sha and at).
Prints per-deploy counts and the medians of built->merged, merged->live and built->live in minutes, and the worst items.
"""
import datetime as dt, json, statistics, subprocess, sys

LOCAL = dt.datetime.now().astimezone().tzinfo


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True).stdout


def when(s, day):
    s = s.strip()
    if "T" in s or len(s) > 8:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=LOCAL)
    h, m = (int(x) for x in s.split(":")[:2])
    return dt.datetime.combine(day, dt.time(h, m), LOCAL)


def deploys(path, day):
    out = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            d = json.loads(line)
            out.append((d["sha"], when(d["at"], day)))
        else:
            sha, t = line.split()[:2]
            out.append((sha, when(t, day)))
    # a deploy after midnight belongs to the next day when given as HH:MM
    for i in range(1, len(out)):
        if out[i][1] < out[i - 1][1]:
            out[i] = (out[i][0], out[i][1] + dt.timedelta(days=1))
    return out


def measure(repo, dep):
    items = []
    for (prev, _), (sha, live) in zip(dep, dep[1:]):
        fp = [l.split() for l in git(repo, "log", "--first-parent", "--format=%H %ct", f"{prev}..{sha}").splitlines()]
        fp.reverse()  # oldest first
        for line in git(repo, "log", "--no-merges", "--format=%H %ct %s", f"{prev}..{sha}").splitlines():
            c, ct, subj = line.split(" ", 2)
            built = dt.datetime.fromtimestamp(int(ct), LOCAL)
            merged = None
            for m, mt in fp:
                if m == c or subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", c, m]).returncode == 0:
                    merged = dt.datetime.fromtimestamp(int(mt), LOCAL)
                    break
            merged = merged or live
            items.append({"deploy": sha[:7], "commit": c[:7], "subject": subj[:90], "built": built.strftime("%H:%M"),
                          "merged": merged.strftime("%H:%M"), "live": live.strftime("%H:%M"),
                          "built_to_merged": round((merged - built).total_seconds() / 60, 1),
                          "merged_to_live": round((live - merged).total_seconds() / 60, 1),
                          "built_to_live": round((live - built).total_seconds() / 60, 1)})
    return items


def main(argv):
    if "--repo" not in argv or "--deploys" not in argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    repo = argv[argv.index("--repo") + 1]
    day = dt.date.fromisoformat(argv[argv.index("--day") + 1]) if "--day" in argv else dt.date.today()
    dep = deploys(argv[argv.index("--deploys") + 1], day)
    items = [i for i in measure(repo, dep) if i["built_to_live"] >= 0]
    med = lambda k: round(statistics.median([i[k] for i in items]), 1) if items else None
    summary = {"deploys": len(dep) - 1, "items": len(items), "median_built_to_merged": med("built_to_merged"),
               "median_merged_to_live": med("merged_to_live"), "median_built_to_live": med("built_to_live"),
               "max_built_to_live": max((i["built_to_live"] for i in items), default=None),
               "over_20_min": sum(i["built_to_live"] > 20 for i in items)}
    if "--json" in argv:
        print(json.dumps({"summary": summary, "items": items}, indent=1))
        return 0
    print(json.dumps(summary))
    for i in sorted(items, key=lambda i: -i["built_to_live"])[:8]:
        print(f"  {i['built_to_live']:>6.0f} min  built {i['built']} merged {i['merged']} live {i['live']}  {i['commit']} {i['subject'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
