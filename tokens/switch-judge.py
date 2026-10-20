#!/usr/bin/env python3
"""switch-judge.py: judge a seat-model switch, and read both weekly plans. Counts and $ only, no message text.

Agent Zero, 16 Oct 16:00: judge the 15 seats moved to Sonnet 5.5 at ~15:30 (and UI-HUB, AGENTS-HUB at ~11:50) by dollars
per Shaan request and tasks finished, before vs after, plus failed or interrupted runs since; then how much is left on
each weekly plan and when each runs out at the last two hours' burn.

  switch-judge.py [--cut 2026-10-16T15:30+07:00] [--before-h 4] [--seats A,B,...] [--plans]

Seat = the SISO Code thread title (ledger.seat_map). Requests and tasks come from scripts/usage-tasks.py (its JSON), $ and
the model per call from tokens/ledger.py scan. Runs come from SISO Code's statev2.sqlite (read-only).
--plans reads each login's plan buckets (the endpoint Claude Code's /usage reads; the token stays in memory), and
prices the weekly % in list-price dollars from the transcripts since the window opened to get hours left.
"""
import argparse, collections, datetime as dt, importlib.machinery, importlib.util, json, os, sqlite3, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


L = load("ledger", os.path.join(HERE, "ledger.py"))
ALL15 = ["PEOPLE-GRAPH", "SOFTWARE-HUB", "INDUSTRIES-HUB", "VIDEO-HUB", "SISO-BENCH", "SISO-VOICE", "LAWBOOK",
         "SISO-HEALTH", "CAMS-LAPTOP", "TOKENS", "DAD-TRADING", "DAD-PROPERTY", "MUSIC", "BROWSER", "AGENT-EFFICIENCY"]


def label_for(session_full, seats):
    return seats.get(session_full) or "?"


def judge(a):
    cut = dt.datetime.fromisoformat(a.cut).timestamp()
    now = time.time()
    t0 = cut - a.before_h * 3600
    seats = L.seat_map()
    calls = L.scan(t0, now)
    for c in calls:
        L.cost(c)
    want = [s.upper() for s in a.seats.split(",")]

    def norm(label):
        u = (label or "").upper()
        for w in want:
            if u == w or u.startswith(w + " ") or u.startswith(w + "-") and w in ("HALO",):
                return w
        return None

    rows = {w: {"b": collections.Counter(), "a": collections.Counter(), "models": collections.Counter()} for w in want}
    for c in calls:
        if c["sub"]:
            continue
        w = norm(seats.get(c["session"]))
        if not w:
            continue
        side = "a" if c["ts"] >= cut else "b"
        r = rows[w][side]
        r["usd"] += c["total"]
        r["calls"] += 1
        r["ctx"] += c["ctx"]
        if side == "a":
            rows[w]["models"][L.short_model(c["model"])] += 1
    # requests and tasks from usage-tasks
    hours = (now - t0) / 3600 + 0.5
    out = subprocess.run([sys.executable, os.path.join(LAB, "scripts", "usage-tasks.py"), "--hours", f"{hours:.1f}", "--json", "/tmp/switch-judge-ut.json"],
                         capture_output=True, text=True)
    ut = json.load(open("/tmp/switch-judge-ut.json"))
    by_prefix = {}
    for full, lab in seats.items():
        by_prefix[full[:8]] = lab
    for t in ut["tasks"]:
        w = norm(by_prefix.get(t["session"]))
        if not w:
            continue
        side = "a" if t["start"] / 1000 >= cut else "b"
        r = rows[w][side]
        r["tasks"] += 1
        r["requests"] += t.get("requests") or 0
    # runs since the cut
    runs = collections.defaultdict(collections.Counter)
    try:
        c = sqlite3.connect(f"file:{L.STATEV2}?mode=ro", uri=True)
        titles = dict(c.execute("select thread_id, title from orchestration_v2_projection_threads"))
        cutz = dt.datetime.fromtimestamp(cut, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")
        for tid, st, at in c.execute("select thread_id, status, requested_at from orchestration_v2_projection_runs where requested_at >= ?", (cutz,)):
            w = norm(titles.get(tid))
            if w:
                runs[w][st] += 1
    except sqlite3.Error as e:
        print("runs: BLOCKED", e)
    print(f"## Switch judged at {a.cut} (before = {a.before_h:g} h earlier; after = {(now - cut) / 60:.0f} min)\n")
    print("| seat | model after (calls) | before $/req (reqs, tasks) | after $/req (reqs, tasks) | avg ctx before→after | failed/interrupted since |")
    print("|---|---|---|---|---|---|")
    tb = collections.Counter(); ta = collections.Counter()
    for w in want:
        r = rows[w]
        b, af = r["b"], r["a"]
        if not (b["calls"] or af["calls"]):
            continue
        pr = lambda x: f"${x['usd'] / x['requests']:.2f} ({x['requests']}, {x['tasks']})" if x["requests"] else f"${x['usd']:.1f}, 0 reqs ({x['tasks']} tasks)"
        cx = lambda x: f"{x['ctx'] / x['calls'] / 1000:.0f}k" if x["calls"] else "-"
        bad = runs[w]["failed"] + runs[w]["interrupted"]
        print(f"| {w} | {dict(r['models'])} | {pr(b)} | {pr(af)} | {cx(b)}→{cx(af)} | {bad} of {sum(runs[w].values())} runs |")
        tb.update(b); ta.update(af)
    print(f"\nTotal before: ${tb['usd']:.0f}, {tb['requests']} requests ({tb['usd'] / max(tb['requests'], 1):.2f}/req), {tb['tasks']} tasks, {tb['calls']} calls."
          f"\nTotal after:  ${ta['usd']:.0f}, {ta['requests']} requests ({ta['usd'] / max(ta['requests'], 1):.2f}/req), {ta['tasks']} tasks, {ta['calls']} calls.")


def plans(a):
    cc = importlib.machinery.SourceFileLoader("cc", os.path.join(LAB, "bin", "claude-credits"))
    spec = importlib.util.spec_from_loader("cc", cc)
    m = importlib.util.module_from_spec(spec)
    cc.exec_module(m)
    now = time.time()
    roots = {"claude-siso": [L.LOGINS["fuze+claude"]], "claude-siso-3": [L.LOGINS["lord"]]}
    print("## Weekly plans\n")
    for login, cfg in m.LOGINS:
        tok = m.token(cfg)
        use = None
        for i in range(3):
            try:
                use = m.get("/api/oauth/usage", tok)
                break
            except Exception as e:
                err = f"{type(e).__name__} {getattr(e, 'code', '')}"
                time.sleep(20)
        if not use:
            print(f"- {login}: BLOCKED, usage endpoint said {err}")
            continue
        wk = use.get("seven_day") or {}
        fh = use.get("five_hour") or {}
        reset = dt.datetime.fromisoformat(wk["resets_at"]).timestamp()
        opened = reset - 7 * 86400
        left_h = (reset - now) / 3600
        # list-price $ on this laptop's transcripts for this login since the window opened, and in the last 2 h
        calls = L.scan(opened, now)
        for c in calls:
            L.cost(c)
        key = "lord" if login == "claude-siso-3" else "fuze+claude"
        mine = [c for c in calls if c["login"] == key]
        since = sum(c["total"] for c in mine)
        last2 = sum(c["total"] for c in mine if c["ts"] >= now - 7200)
        pct = wk.get("utilization") or 0
        per_pct = since / pct if pct else None
        rate = (last2 / 2) / per_pct if per_pct else None  # % per hour
        print(f"- **{login}**: week {pct:.0f}% used, resets {dt.datetime.fromtimestamp(reset, dt.timezone(dt.timedelta(hours=7))):%a %d %b %H:%M +07} "
              f"({left_h:.0f} h away, {100 - pct:.0f}% left); 5-hour {fh.get('utilization')}% used.")
        if per_pct:
            print(f"  This laptop since the window opened: ${since:,.0f} list = {pct:.0f}% so ${per_pct:,.1f} per 1%. Last 2 h: ${last2:,.0f} = {rate:.2f}%/h, "
                  f"so {(100 - pct) / rate if rate else float('inf'):.1f} h to 100% vs {left_h:.0f} h to reset. "
                  f"To last to the reset it can burn {(100 - pct) / left_h:.2f}%/h = ${((100 - pct) / left_h) * per_pct:.1f}/h.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut", default="2026-10-16T15:30:00+07:00")
    ap.add_argument("--before-h", type=float, default=4)
    ap.add_argument("--seats", default=",".join(ALL15))
    ap.add_argument("--plans", action="store_true")
    a = ap.parse_args()
    if a.plans:
        plans(a)
    else:
        judge(a)
