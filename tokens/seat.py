#!/usr/bin/env python3
"""seat.py: where one seat's dollars went. Counts, $ and command shapes only, never message text.

Agent Zero, 15 Oct: "HALO and UI-HUB: where their dollars went ... context size, reads that should have been Haiku,
re-reads, idle polling turns. Name the top 3 wastes with $ each."

  seat.py --seat '^HALO$' [--hours 24]       # regex on the seat name (ledger.seat_map), or on the session id

Per matching seat: $ main vs sub-agents (by model) and spawns; main $ by part (cache read/write/output); context;
and the waste buckets, each priced at the Opus calls it covers:
  over100k   cache reads beyond 100k of context (what a smaller context would not pay)
  readruns   runs of 3+ read-only Opus calls (Haiku's job); haiku_save = what a scout per run would have saved
  rereads    a file read again (Read, or sed/cat/head/tail on the same path) since the last compaction
  polling    calls that only wait or check (sleep, thread/task status, gh checks, TaskOutput, Monitor, ...)
  woken      turns started by a notification/system event rather than a prompt (all calls in that turn)
  cold       cache re-writes after a gap past the TTL
"""
import argparse, glob, importlib.util, json, os, re, time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("loops", os.path.join(HERE, "loops.py"))
LP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(LP)
L = LP.L
H_IN, _, H_W1, H_RD, H_OUT = L.tw.RATES["haiku-5"]

POLL_TOOLS = re.compile(r"(TaskOutput|TaskGet|TaskList|Monitor|ScheduleWakeup|t3_thread_(wait|read|list)|task_status|"
                        r"list_thread_pull_requests|t3_pending_request_list)$")
POLL_BASH = re.compile(r"(^|[;&|(]\s*)(sleep \d|until\b|while\b.*sleep|gh (pr|run) (checks|watch)|tail -f|curl -s\S* "
                       r"\S*(health|status))")
WOKEN = ("<task-notification>", "SYSTEM NOTIFICATION", "<system-reminder>\n[SYSTEM")
PATH = re.compile(r"(?:sed -n \S+|\bcat|\bhead(?: -n ?\d+| -\d+)?|\btail(?: -n ?\d+| -\d+)?)[ \t]+(['\"]?)([\w~./-]*[./][\w./-]+)\1")


def files_for(rx, seats):
    out = []
    for login, root in L.LOGINS.items():
        for f in glob.glob(root + "/*/*.jsonl"):
            sid = os.path.basename(f)[:-6]
            if rx.search(seats.get(sid, "")) or rx.search(sid):
                out.append((seats.get(sid, sid[:8]), f))
    return out


def read_paths(name, inp):
    if name == "Read":
        return [inp.get("file_path", "")]
    if name == "Bash":
        return [m.group(2) for m in PATH.finditer(inp.get("command", ""))]
    return []


def session(f, t0, t1):
    """Ordered Opus/other main calls with their uses, the turn trigger and per-call waste."""
    calls, order, trigger = {}, [], "prompt"
    for line in open(f, errors="replace"):
        if '"type":"user"' in line or '"type": "user"' in line:
            if '"tool_result"' in line:
                continue
            trigger = "woken" if any(w in line for w in WOKEN) else "prompt"
            continue
        if '"assistant"' not in line or '"usage"' not in line:
            continue
        try:
            d = json.loads(line)
            m = d["message"]
            ts = L.iso(d["timestamp"])
        except (ValueError, KeyError, TypeError):
            continue
        if not (t0 <= ts < t1) or m.get("model") in (None, "<synthetic>"):
            continue
        k = (m.get("id"), d.get("requestId"))
        c = calls.get(k)
        if c is None:
            c = calls[k] = {"model": m["model"], "u": m["usage"], "ts": ts, "uses": [], "trigger": trigger}
            order.append(c)
        for b in m.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                c["uses"].append((b.get("name") or "", b.get("input") or {}))
    return order


def subagents(f, t0, t1):
    by = Counter()
    for g in glob.glob(f[:-6] + "/subagents/**/*.jsonl", recursive=True):
        if os.path.getmtime(g) < t0:
            continue
        seen = set()
        for line in open(g, errors="replace"):
            if '"usage"' not in line or '"assistant"' not in line:
                continue
            try:
                d = json.loads(line)
                m = d["message"]
                ts = L.iso(d["timestamp"])
            except (ValueError, KeyError, TypeError):
                continue
            k = (m.get("id"), d.get("requestId"))
            if k in seen or not (t0 <= ts < t1) or m.get("model") in (None, "<synthetic>"):
                continue
            seen.add(k)
            c = {"model": m["model"], "u": m["usage"]}
            L.cost(c)
            by[L.short_model(c["model"])] += c["total"]
    return by


def analyse(files, t0, t1):
    R = defaultdict(float)
    sub, spawns = Counter(), Counter()
    ctxs = []
    did, bash = Counter(), Counter()
    for _, f in files:
        sub.update(subagents(f, t0, t1))
        cs = session(f, t0, t1)
        seen, prev, run = set(), None, []

        def close_run():
            if len(run) >= 3:
                R["readruns"] += sum(x["total"] for x in run)
                R["readruns_n"] += 1
                R["readruns_calls"] += len(run)
                R["haiku_cost"] += len(run) * (40_000 * H_RD + 3_000 * H_W1 + 300 * H_OUT) / 1e6
                R["readruns_first"] += run[0]["total"]

        for c in cs:
            L.cost(c)
            opus = "opus" in c["model"]
            R["usd"] += c["total"]
            if not opus:
                R["usd_other_main"] += c["total"]
                continue
            R["opus_calls"] += 1
            ctxs.append(c["ctx"])
            for p, v in c["usd"].items():
                R["part_" + p] += v
            if c["ctx"] > 100_000:
                R["over100k"] += min(c["tok"]["read"], c["ctx"] - 100_000) * c["r_rd"] / 1e6
            if prev is not None and c["ctx"] < prev["ctx"] * 0.6:
                seen = set()  # compaction: earlier reads are gone
            gap = c["ts"] - (prev["ts"] if prev else c["ts"])
            if c["tok"]["write"] >= 30_000 and gap > (3600 if c["w1"] else 300):
                R["cold"] += c["usd"]["write"]
            prev = c
            if c["trigger"] == "woken":
                R["woken"] += c["total"]
                R["woken_calls"] += 1
            names = [n for n, _ in c["uses"]]
            kind = ("talk (no tool)" if not names else "edit/write" if any(n in ("Edit", "Write", "MultiEdit") for n in names)
                    else "spawn agent" if any(n in ("Agent", "Task", "Workflow") for n in names)
                    else "read-only" if all(n in L.tw.FETCH for n in names) and all(
                        n != "Bash" or LP.reads_only(i.get("command", "")) for n, i in c["uses"])
                    else "run bash" if "Bash" in names else "mcp/other: " + names[0].split("__")[-1][:24])
            did[kind] += c["total"]
            for n, i in c["uses"]:
                if n == "Bash" and kind == "run bash":
                    w = re.sub(r"^\s*(cd [^;&|]+(&&|;)\s*)+", "", i.get("command", "")).split()
                    bash[(w[0] if w else "?")[:20] + (" " + w[1][:16] if len(w) > 1 and w[0] in ("git", "gh", "npm", "pnpm", "bun", "heavy", "npx", "node", "python3") else "")] += c["total"] / len(names)
            for n, i in c["uses"]:
                if n in ("Agent", "Task"):
                    spawns[(i.get("subagent_type") or "general") + ":" + (i.get("model") or "default")] += 1
            if names and all(POLL_TOOLS.search(n) or (n == "Bash" and POLL_BASH.search(i.get("command", "")))
                             for n, i in c["uses"]):
                R["polling"] += c["total"]
                R["polling_calls"] += 1
            for n, i in c["uses"]:
                if n in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                    seen.discard(i.get("file_path", ""))  # reading back what you just changed is not a waste
            paths = [p for n, i in c["uses"] for p in read_paths(n, i) if p and not p.startswith("-")]
            if any(p in seen for p in paths):
                R["rereads"] += c["total"]
                R["rereads_calls"] += 1
            seen.update(paths)
            ro = bool(c["uses"]) and all(n in L.tw.FETCH for n in names) and all(
                n != "Bash" or LP.reads_only(i.get("command", "")) for n, i in c["uses"])
            if ro:
                R["ro"] += c["total"]
                R["ro_calls"] += 1
                run.append(c)
            else:
                close_run()
                run = []
        close_run()
    R["did"] = did
    R["bash"] = bash
    R["haiku_save"] = R["readruns"] - R["haiku_cost"] - R["readruns_first"]
    ctxs.sort()
    R["ctx_avg"] = sum(ctxs) / len(ctxs) if ctxs else 0
    R["ctx_p90"] = ctxs[int(len(ctxs) * 0.9)] if ctxs else 0
    return R, sub, spawns


def report(name, files, t0, t1):
    R, sub, spawns = analyse(files, t0, t1)
    subusd = sum(sub.values())
    tot = R["usd"] + subusd
    pc = lambda v: f"${v:,.0f} ({v / max(tot, 1):.0%})"
    print(f"\n## {name}: ${tot:,.0f} in {len(files)} session file(s); Opus main {R['opus_calls']:,.0f} calls, "
          f"avg ctx {R['ctx_avg'] / 1000:.0f}k, p90 {R['ctx_p90'] / 1000:.0f}k")
    print(f"- main {pc(R['usd'])}: cache read ${R['part_read']:,.0f}, write ${R['part_write']:,.0f}, "
          f"output ${R['part_out']:,.0f}, input ${R['part_in']:,.0f}")
    print(f"- sub-agents {pc(subusd)}: " + (", ".join(f"{k} ${v:,.1f}" for k, v in sub.most_common()) or "none"))
    print(f"- spawns: " + (", ".join(f"{k} x{v}" for k, v in spawns.most_common(6)) or "none"))
    print("- what the Opus calls did: " + ", ".join(f"{k} ${v:,.0f}" for k, v in R["did"].most_common(8)))
    print("- top non-read Bash: " + ", ".join(f"{k} ${v:,.1f}" for k, v in R["bash"].most_common(8)))
    print("| waste bucket | $ | calls | note |\n|---|---|---|---|")
    rows = [("context over 100k (cache reads)", R["over100k"], R["opus_calls"], "what a <=100k context would not pay"),
            ("read-only Opus calls (all)", R["ro"], R["ro_calls"], "own cost of calls that only read"),
            ("runs of 3+ reads", R["readruns"], R["readruns_calls"],
             f"{R['readruns_n']:.0f} runs; a scout per run saves ~${R['haiku_save']:,.0f}"),
            ("re-reads of the same file", R["rereads"], R["rereads_calls"], "since the last compaction"),
            ("polling / waiting calls", R["polling"], R["polling_calls"], "sleep, status, TaskOutput, thread wait"),
            ("turns woken by notifications", R["woken"], R["woken_calls"], "all calls in those turns"),
            ("cold cache re-writes", R["cold"], 0, "after a gap past the TTL")]
    for r in rows:
        print(f"| {r[0]} | {r[1]:,.0f} | {r[2]:,.0f} | {r[3]} |")
    return R, sub


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seat", action="append", required=True, help="regex on seat name or session id (repeatable)")
    ap.add_argument("--hours", type=float, default=24)
    a = ap.parse_args()
    t1 = time.time()
    t0 = t1 - a.hours * 3600
    seats = L.seat_map()
    for s in a.seat:
        files = [x for x in files_for(re.compile(s), seats) if os.path.getmtime(x[1]) >= t0]
        report(s, files, t0, t1)


if __name__ == "__main__":
    main()
