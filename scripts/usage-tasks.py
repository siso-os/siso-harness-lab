#!/usr/bin/env python3
"""usage-tasks.py: plan-token cost per seat and per task, with the waste named.

Shaan, 13 Oct ~02:00: "have we got the system to track the usage and usage per task and wasted tokens".
Same transcripts and list prices as token-where.py (imported, not copied). Agent Base reads the JSON on its Tokens
screen (node services/node: GET /api/usage/tasks runs this when the file is older than 15 min and the screen asks).

A task: in a seat's main conversation, from the first request after a finish (to the next finish). A finish is the
seat writing .agents/HANDOFF.md, a DONE line to the A0 inbox, seat-fresh, or a compaction. Its label is the first
A0 task id (t-NNNN) in its requests, else the first request's opening words. Sub-agents count to the task running
when they started.

Waste, in dollars, per task and per seat:
  fetch      Opus/Fable calls that only read/search (Bash only when it reads), in runs of 3+ (Haiku 5.5's job, ~1/40 the price)
  reread     a file Read again in the same conversation: its tokens written again and carried on every later call
  bash       Bash output carried on every later call as cached input (part of it is needed; the big share is not)
  stale      after a finish, the finished task's context re-read on every later call until a fresh start/compaction

  usage-tasks.py [--hours 24] [--json OUT]
"""
import argparse, glob, importlib.util, json, os, re, time
from collections import defaultdict

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("tw", os.path.join(here, "token-where.py"))
tw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tw)

HOSTS = os.path.expanduser("~/.local/state/agent-base/hosts")
TASK_ID = re.compile(r"\bt-\d{4}\b")
WASTE = ("fetch", "reread", "bash", "stale")


def seat_names():
    """session id -> Agent Base seat name, from live and archived host records."""
    out = {}
    for f in glob.glob(HOSTS + "/**/*.json", recursive=True):
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("session") and d.get("name"):
            out[d["session"]] = d["name"]
    return out


def finish(tool, inp):
    if tool in ("Edit", "Write", "MultiEdit"):
        return str(inp.get("file_path", "")).endswith(".agents/HANDOFF.md")
    if tool == "Bash":
        cmd = str(inp.get("command", ""))
        return "seat-fresh" in cmd or ("a0/inbox.log" in cmd and ">>" in cmd and "DONE" in cmd)
    return False


def label_of(text):
    t = " ".join(text.split())
    m = TASK_ID.search(t)
    return (m.group(0), t[:90]) if m else (None, t[:90])


def ts_of(o):
    try:
        return time.mktime(time.strptime(o.get("timestamp", "")[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except ValueError:
        return 0


def new_task(seat, sid, start, text):
    tid, lab = label_of(text)
    return {"seat": seat, "session": sid[:8], "task": tid, "label": lab, "start": start, "end": start, "usd": 0.0,
            "sub_usd": 0.0, "calls": 0, "requests": 0, "max_ctx": 0, "waste": {w: 0.0 for w in WASTE}}


def scan(f, since, seat, sid, tasks_out, sub_into=None):
    """One transcript. Main: appends tasks to tasks_out. Sub-agent (sub_into(ts) -> task): adds to that task."""
    sub = sub_into is not None
    names, reads, pending = {}, {}, []  # pending: [tokens, tool, reread?]
    task, stale, armed, seen = None, 0, False, set()
    last_ctx = 0
    toolsof, seq = defaultdict(set), []  # an assistant message streams as several lines, one block each

    for line in open(f, errors="ignore"):
        if '"type":"user"' not in line and '"type":"assistant"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        msg, ts = o.get("message") or {}, ts_of(o)
        c = msg.get("content")
        if o["type"] == "user":
            first = c if isinstance(c, str) else (c[0].get("text", "") if isinstance(c, list) and c and isinstance(c[0], dict) and c[0].get("type") == "text" else None)
            if first is not None and not sub and not o.get("isSidechain"):
                kind = tw.trigger(first)
                if kind == "compaction":
                    pending, reads, stale = [], {}, 0
                    armed = True
                elif kind in ("Shaan", "another agent") and ts >= since:
                    if task is None or armed:
                        task = new_task(seat, sid, ts, first)
                        tasks_out.append(task)
                        armed = False
                    task["requests"] += 1
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        tool, path = names.get(b.get("tool_use_id"), ("?", None))
                        rr = tool == "Read" and path in reads
                        if tool == "Read" and path:
                            reads[path] = 1
                        pending.append([tw.size(b.get("content")), tool, rr])
            continue
        mid = msg.get("id") or o.get("requestId")
        ends = False
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                    names[b.get("id")] = (b.get("name", "?"), inp.get("file_path"))
                    # a Bash that builds, deploys or commits is work, not fetching (token-where's strict measure)
                    toolsof[mid].add("Bash:act" if b.get("name") == "Bash" and not tw.READ_CMD.match(str(inp.get("command", ""))) else b.get("name", "?"))
                    ends = ends or (not sub and finish(b.get("name"), inp))
        if ends and o.get("timestamp", "") and ts >= since:
            stale, armed = last_ctx, True
        if not mid or mid in seen:
            continue
        seen.add(mid)
        u, model = msg.get("usage") or {}, msg.get("model", "?")
        if model == "<synthetic>" or not u or ts < since:
            continue
        t = sub_into(ts) if sub else task
        if t is None:
            continue
        rd, inp_t, out = u.get("cache_read_input_tokens", 0), u.get("input_tokens", 0), u.get("output_tokens", 0)
        cw = u.get("cache_creation_input_tokens", 0)
        r_in, r_w5, r_w1, r_rd, r_out = tw.price(model, inp_t + rd + cw)
        w1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0)
        usd = (inp_t * r_in + (cw - w1h) * r_w5 + w1h * r_w1 + rd * r_rd + out * r_out) / 1e6
        ctx = inp_t + cw + rd
        for n, tool, rr in pending:
            if rr:
                t["waste"]["reread"] += n * r_rd / 1e6
            elif tool == "Bash":
                t["waste"]["bash"] += n * r_rd / 1e6
        if stale:
            t["waste"]["stale"] += min(stale, rd) * r_rd / 1e6
        if sub:
            t["sub_usd"] += usd
        else:
            t["usd"] += usd
            t["calls"] += 1
            t["end"] = ts
            t["max_ctx"] = max(t["max_ctx"], ctx)
        seq.append((mid, t, usd, model))
        last_ctx = ctx
    run = []
    for mid, t, usd, model in seq + [(None, None, 0, "")]:
        if mid and toolsof[mid] and toolsof[mid] <= tw.FETCH and ("opus" in model or "fable" in model):
            run.append((t, usd))
            continue
        if len(run) >= 3:
            for rt, ru in run:
                rt["waste"]["fetch"] += ru * (1 - 1 / 40)
        run = []


def proof(hours):
    import subprocess, tempfile
    # fetch_share is Opus reading for itself (Bash only when it reads). The old "any Bash" share (75%) mostly counted
    # builds, deploys and commits; measured the strict way 12-13 Oct was 17% (72 h) to 23% (24 h).
    out = {"baseline": {"at": "12-13 Oct, before the restarts", "per_shaan_request": 1.90, "fetch_share": 0.20}}
    with tempfile.NamedTemporaryFile(suffix=".json") as t:
        try:
            subprocess.run(["python3", os.path.join(here, "token-where.py"), "--hours", str(hours), "--json", t.name],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600, check=True)
            d = json.load(open(t.name))
            out.update(shaan_requests=d["shaan_requests"], per_shaan_request=d["usd_per_shaan_request"],
                       fetch_share=d["opus_read_loops"]["share"], any_bash_share=d["opus_fetch_loops"]["share"])
        except Exception:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--json")
    a = ap.parse_args()
    since = time.time() - a.hours * 3600
    names = seat_names()
    files = set()
    for r in tw.ROOTS:
        for x in glob.glob(r + "/projects/**/*.jsonl", recursive=True):
            try:
                if os.path.getmtime(x) >= since:
                    files.add(os.path.realpath(x))
            except OSError:
                pass
    mains = sorted(f for f in files if "/subagents/" not in f)
    tasks, by_session = [], defaultdict(list)
    for f in mains:
        sid = os.path.basename(f)[:-6]
        cwd_seat = None
        for line in open(f, errors="ignore"):
            if '"cwd"' in line:
                try:
                    cwd_seat = tw.seat(json.loads(line).get("cwd"))
                    break
                except ValueError:
                    pass
        seat = names.get(sid) or cwd_seat or "?"
        before = len(tasks)
        scan(f, since, seat, sid, tasks)
        by_session[sid] = tasks[before:]
    for f in files:
        if "/subagents/" not in f:
            continue
        sid = f.split("/subagents/")[0].rsplit("/", 1)[-1]
        ts_list = by_session.get(sid)
        if not ts_list:
            continue

        def into(ts, ts_list=ts_list):
            cur = None
            for t in ts_list:
                if t["start"] <= ts:
                    cur = t
            return cur or ts_list[0]
        scan(f, since, ts_list[0]["seat"], sid, tasks, sub_into=into)

    seats = defaultdict(lambda: {"usd": 0.0, "tasks": 0, "requests": 0, "waste": {w: 0.0 for w in WASTE}})
    for t in tasks:
        s = seats[t["seat"]]
        s["usd"] += t["usd"] + t["sub_usd"]
        s["tasks"] += 1
        s["requests"] += t["requests"]
        for w in WASTE:
            s["waste"][w] += t["waste"][w]
    total = sum(s["usd"] for s in seats.values()) or 1
    waste_tot = {w: sum(s["waste"][w] for s in seats.values()) for w in WASTE}
    r2 = lambda x: round(x, 2)
    res = {"at": int(time.time() * 1000), "hours": a.hours, "usd": r2(total),
           "requests": sum(s["requests"] for s in seats.values()),
           "waste": {w: r2(v) for w, v in waste_tot.items()},
           # The proof Shaan asked for (13 Oct 04:00): token-where.py's own two numbers, so there is one truth.
           "proof": proof(a.hours),
           "waste_share": {w: round(v / total, 4) for w, v in waste_tot.items()},
           "seats": sorted([{"seat": k, "usd": r2(v["usd"]), "tasks": v["tasks"], "requests": v["requests"],
                             "per_request": r2(v["usd"] / max(v["requests"], 1)), "waste": {w: r2(x) for w, x in v["waste"].items()}}
                            for k, v in seats.items()], key=lambda s: -s["usd"]),
           "tasks": [{**t, "usd": r2(t["usd"] + t["sub_usd"]), "sub_usd": r2(t["sub_usd"]),
                      "waste": {w: r2(x) for w, x in t["waste"].items()}, "start": int(t["start"] * 1000), "end": int(t["end"] * 1000)}
                     for t in sorted(tasks, key=lambda t: -(t["usd"] + t["sub_usd"]))[:80] if t["usd"] + t["sub_usd"] >= 0.01]}
    if a.json:
        tmp = a.json + ".tmp"
        json.dump(res, open(tmp, "w"), indent=1)
        os.replace(tmp, a.json)
    pr = res["proof"]
    if "fetch_share" in pr:
        print(f"proof (token-where): ${pr['per_shaan_request']}/Shaan request over {pr['shaan_requests']} (13 Oct: $1.90), Opus reading loops {pr['fetch_share'] * 100:.0f}% (12-13 Oct: ~20%)")
    print(f"{a.hours:g}h ${total:.0f} over {res['requests']} requests; waste " +
          ", ".join(f"{w} ${v:.0f} ({res['waste_share'][w] * 100:.0f}%)" for w, v in waste_tot.items()))
    for s in res["seats"][:8]:
        print(f"  {s['seat'][:22]:22} ${s['usd']:7.2f} {s['tasks']:3} tasks ${s['per_request']}/req  waste {s['waste']}")
    for t in res["tasks"][:8]:
        print(f"  ${t['usd']:6.2f} {t['seat'][:14]:14} {t['task'] or '':7} {t['label'][:60]}")


if __name__ == "__main__":
    main()
