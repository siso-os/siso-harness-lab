#!/usr/bin/env python3
"""loops.py: were the Opus reads needed? What each read-only call costs, what it leaves behind, and what would be cheaper.

Shaan, 14 Oct: "Is this stuff that Opus could have avoided or did we actually need these read and writes?"

For every Opus main-conversation call in the window (counts and command shapes only, never text):
  footprint  its own price + the result it adds, re-read on every later call until the next compaction ("carry")
  kind       grep/rg, file slice (sed/head/tail/cat), ls/find, git, Read, Read again (same file), ...
  shape      one read per call (could have been one batched call) vs several in parallel
  per run of 3+ read-only calls, two counterfactuals:
             batch   one Opus call runs all the reads: saves the context re-read and overhead of N-1 calls
             haiku   a Haiku 5.5 sub-agent does the run and returns ~15% of the raw output: saves the Opus calls and
                     85% of the carry; costs N Haiku calls at 40k context + its output

  loops.py [--hours 24]
"""
import argparse, glob, importlib.util, json, os, re, time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ledger", os.path.join(HERE, "ledger.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)
tw = L.tw
H_IN, _, H_W1, H_RD, H_OUT = tw.RATES["haiku-5"]


reads_only = L.reads_only


def kind_of(name, inp, seen):
    if name == "Read":
        p = inp.get("file_path", "")
        k = "Read again" if p in seen else "Read"
        seen.add(p)
        return k
    if name != "Bash":
        return name
    cmd = re.sub(r"^\s*(cd [^;&|]+(&&|;)\s*)+", "", inp.get("command", ""))
    w = cmd.split()[:2]
    if not w:
        return "Bash ?"
    if w[0] == "git":
        return "git " + (w[1] if len(w) > 1 else "")
    if w[0] in ("sed", "head", "tail", "cat", "awk", "jq"):
        return "file slice (sed/head/tail/cat/jq)"
    if w[0] in ("grep", "rg", "ugrep"):
        return "grep/rg"
    if w[0] in ("ls", "find", "fd", "tree", "stat", "wc", "file"):
        return "ls/find/wc"
    return "Bash " + w[0]


def chars(cont):
    """Text length of a tool result; an image counts as ~1,600 tokens (6,400 chars), not its base64 length."""
    if isinstance(cont, str):
        return len(cont)
    n = 0
    for x in cont or []:
        if isinstance(x, dict):
            n += 6_400 if x.get("type") == "image" else len(x.get("text") or "")
    return n


def scan(t0, t1):
    out = []
    for login, root in L.LOGINS.items():
        for f in glob.glob(root + "/*/*.jsonl"):
            if os.path.getmtime(f) < t0:
                continue
            msgs, rsize = {}, {}
            for line in open(f, errors="replace"):
                if '"assistant"' in line and '"usage"' in line:
                    try:
                        d = json.loads(line)
                        m = d["message"]
                        ts = L.iso(d["timestamp"])
                    except (ValueError, KeyError, TypeError):
                        continue
                    if not (t0 <= ts < t1) or "opus" not in (m.get("model") or ""):
                        continue
                    c = msgs.setdefault((m.get("id"), d.get("requestId")), {"file": f, "model": m["model"], "ts": ts,
                                                                            "u": m["usage"], "uses": []})
                    for b in m.get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            c["uses"].append((b.get("name"), b.get("input") or {}, b.get("id")))
                elif '"tool_result"' in line:
                    try:
                        for b in json.loads(line)["message"]["content"]:
                            if isinstance(b, dict) and b.get("type") == "tool_result":
                                rsize[b.get("tool_use_id")] = chars(b.get("content"))
                    except (ValueError, KeyError, TypeError):
                        continue
            for c in msgs.values():
                c["rchars"] = sum(rsize.get(u[2], 0) for u in c["uses"])
                c["tools"] = [u[0] for u in c["uses"]]
                c["sub"] = False
                out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    t1 = time.time()
    calls = scan(t1 - a.hours * 3600, t1)
    for c in calls:
        L.cost(c)
    calls.sort(key=lambda c: (c["file"], c["ts"]))
    by_file = defaultdict(list)
    for c in calls:
        by_file[c["file"]].append(c)
    # carry: a result's tokens (~chars/4) are re-read on each later call until the context drops (compaction)
    for cs in by_file.values():
        later = 0
        for i in range(len(cs) - 1, -1, -1):
            if i + 1 < len(cs) and cs[i + 1]["ctx"] < cs[i]["ctx"] * 0.6:
                later = 0
            cs[i]["later"] = later
            later += 1
        for c in cs:
            c["rtok"] = c["rchars"] / 4
            c["carry"] = c["rtok"] * c["later"] * c["r_rd"] / 1e6
            c["write_res"] = c["rtok"] * 8 / 1e6  # written once to the 1h cache
    allusd = sum(c["total"] for c in calls)
    # what kind of reads, and are they read-only
    K = defaultdict(lambda: defaultdict(float))
    for cs in by_file.values():
        seen = set()
        for c in cs:
            kinds = [kind_of(n, i, seen) for n, i, _ in c["uses"]]
            ro = bool(kinds) and all(n in tw.FETCH for n in c["tools"]) and all(
                n != "Bash" or reads_only(i.get("command", "")) for n, i, _ in c["uses"])
            c["ro"] = ro
            if not ro:
                continue
            share = 1 / len(kinds)
            for k in kinds:
                K[k]["calls"] += share
                K[k]["usd"] += c["total"] * share
                K[k]["carry"] += (c["carry"] + c["write_res"]) * share
                K[k]["rtok"] += c["rtok"] * share
    ro = [c for c in calls if c["ro"]]
    single = [c for c in ro if len(c["uses"]) == 1]
    print(f"Opus main calls {len(calls):,} (${allusd:,.0f}); read-only {len(ro):,} (${sum(c['total'] for c in ro):,.0f} "
          f"own + ${sum(c['carry'] + c['write_res'] for c in ro):,.0f} carry/write of their results); "
          f"{len(single)/max(len(ro),1):.0%} of them hold one read only")
    print("\n| read kind | calls | own $ | result write+carry $ | avg result tokens |\n|---|---|---|---|---|")
    for k, v in sorted(K.items(), key=lambda kv: -(kv[1]["usd"] + kv[1]["carry"]))[:14]:
        print(f"| {k} | {v['calls']:,.0f} | {v['usd']:,.0f} | {v['carry']:,.0f} | {v['rtok']/max(v['calls'],1):,.0f} |")
    # runs of 3+
    runs = []
    for cs in by_file.values():
        cur = []
        for c in cs + [None]:
            if c is not None and c["ro"]:
                cur.append(c)
                continue
            if len(cur) >= 3:
                runs.append(cur)
            cur = []
    n = sum(len(r) for r in runs)
    own = sum(c["total"] for r in runs for c in r)
    carry = sum(c["carry"] + c["write_res"] for r in runs for c in r)
    batch = sum(c["usd"]["read"] + c["usd"]["in"] + c["usd"]["write"] * 0 for r in runs for c in r[1:])
    haiku_cost = sum(len(r) * (40_000 * H_RD + 3_000 * H_W1 + 300 * H_OUT) / 1e6 for r in runs)
    haiku_save = own + 0.85 * carry - haiku_cost - sum(r[0]["total"] for r in runs)  # parent still pays one spawn call
    lens = Counter(min(len(r), 10) for r in runs)
    print(f"\nRuns of 3+ read-only Opus calls: {len(runs):,} runs, {n:,} calls; own ${own:,.0f}, result write+carry ${carry:,.0f}")
    print("run length (10 = 10+): " + ", ".join(f"{k}:{v}" for k, v in sorted(lens.items())))
    print(f"batch counterfactual (one call per run): saves ${batch:,.0f}")
    print(f"Haiku counterfactual (sub-agent per run, 15% returned): saves ${haiku_save:,.0f} (Haiku cost ${haiku_cost:,.0f})")
    # big tool results
    big = [c for c in calls if c["rtok"] > 10_000]
    print(f"\nTool results over 10k tokens: {len(big):,} calls, {sum(c['rtok'] for c in big)/1e6:.1f}M tokens, "
          f"write+carry ${sum(c['carry'] + c['write_res'] for c in big):,.0f}")
    tc = sum(c["carry"] + c["write_res"] for c in calls)
    print(f"All tool results on Opus main: {sum(c['rtok'] for c in calls)/1e6:.1f}M tokens, write+carry ${tc:,.0f} "
          f"({tc/max(allusd,1):.0%} of Opus main $)")


if __name__ == "__main__":
    main()
