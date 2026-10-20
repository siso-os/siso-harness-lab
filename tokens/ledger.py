#!/usr/bin/env python3
"""ledger.py: where every Claude (and Codex) token went, per seat, per day, per kind of work. Counts only, no text.

Shaan, 14 Oct ~20:10: "in 24 hours we spend 30% of our weekly plan ... I don't even know what we really did today".

Reads the session transcripts (0 model tokens), dedupes each API call (one call is written once per content block),
prices it at list price (token-where.py's RATES: cache reads are cheap, cache writes and output are dear) and splits:
  seat       t3-seats.json + SISO Code statev2 (native session -> thread -> title) + Agent Base host records, else repo
  main/sub   sub-agent transcripts live under <session>/subagents/
  model      the model field, never a substring of the path
  waste      big    cache reads above 100k context on each call (what compacting at 100k would save)
             cold   cache writes >=30k after a gap past the cache TTL (an idle seat waking re-writes its whole context)
             fetch  Opus/Fable calls that only read or search (a Haiku's or a script's job)
             opsub  sub-agents running on Opus/Fable

  ledger.py [--hours 24 | --day YYYY-MM-DD] [--top 10] [--json OUT] [--daily [--day D]]  (--daily: a day into LEDGER.md)
"""
import argparse, datetime as dt, glob, importlib.util, json, os, re, sqlite3, sys, time
from collections import defaultdict

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# ~/.claude-siso/projects is a link to ~/.claude/projects: the fuzeheritage and default logins share one folder
LOGINS = {"lord": HOME + "/.config/claude-siso-3/projects", "fuze+claude": HOME + "/.claude/projects"}
STATEV2 = HOME + "/.local/state/siso-code/userdata/statev2.sqlite"
SEATS = HOME + "/.local/state/agent-base/t3-seats.json"
CODEX = HOME + "/.codex/sessions"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tw = _load("tw", os.path.join(REPO, "scripts", "token-where.py"))  # RATES, price(), READ_CMD, FETCH
try:
    ut = _load("ut", os.path.join(REPO, "scripts", "usage-tasks.py"))
except Exception:
    ut = None
DEAR = ("opus", "fable")


def _js_re(name):
    """Pull a regex literal out of hooks/fetch-nudge.mjs so the hook and this report judge Bash the same way."""
    src = open(os.path.join(REPO, "hooks", "fetch-nudge.mjs")).read()
    return re.compile(re.search(r"const " + name + r" = /(.*)/;\n", src).group(1))


READER, SKIP, WRITES = _js_re("READER"), _js_re("SKIP"), _js_re("WRITES")


def reads_only(cmd):
    """Python twin of readsOnly() in hooks/fetch-nudge.mjs: every piece of the command is a read."""
    if not cmd or WRITES.search(cmd):
        return False
    pieces = []
    for p in re.split(r"\n|;|&&|\|\||\|", cmd):
        p = re.sub(r"^(do|then|else)\s+", "", p.strip())
        p = re.sub(r"\s*2>&1", "", re.sub(r"\s*2>/dev/null", "", p))
        p = re.sub(r"^xargs( -\S+( \S+)?)*\s+(?=[a-z])", "", re.sub(r"^heavy --\s+", "", p))
        p = re.sub(r"['\"]\s*$", "", re.sub(r"^ssh( -\S+( \S+)?)* [\w@.-]+\s+['\"]?", "", p))
        if p:
            pieces.append(p)
    real = [p for p in pieces if not SKIP.match(p)]
    return bool(real) and all(READER.match(p) for p in real)


def seat_map():
    """native session id -> seat label."""
    out, thread_seat = {}, {}
    if ut:
        try:
            out.update(ut.seat_names())
        except Exception:
            pass
    try:
        for name, s in json.load(open(SEATS)).items():
            if isinstance(s, dict):
                if s.get("session"):
                    out[s["session"]] = name
                if s.get("thread"):
                    thread_seat[s["thread"]] = name
    except (OSError, ValueError):
        pass
    try:
        c = sqlite3.connect(f"file:{STATEV2}?mode=ro", uri=True)
        titles = dict(c.execute("select thread_id, title from projection_threads"))
        titles.update({k: v for k, v in c.execute("select thread_id, title from orchestration_v2_projection_threads") if v})
        for tid, pj in c.execute("select thread_id, payload_json from orchestration_v2_projection_provider_threads"):
            try:
                nid = json.loads(pj)["nativeThreadRef"]["nativeId"]
            except (ValueError, KeyError, TypeError):
                continue
            label = thread_seat.get(tid) or titles.get(tid)
            if label and nid not in out:
                out[nid] = label
    except sqlite3.Error:
        pass
    return out


def iso(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def scan(t0, t1):
    """One record per API call in [t0, t1): (login, session, sub, cwd, model, ts, usage, tools, readonly-bash)."""
    calls = {}
    for login, root in LOGINS.items():
        for f in glob.glob(root + "/*/*.jsonl") + glob.glob(root + "/*/*/subagents/**/*.jsonl", recursive=True):
            try:
                if os.path.getmtime(f) < t0:
                    continue
            except OSError:
                continue
            sub = "/subagents/" in f
            session = f.split("/subagents/")[0].rsplit("/", 1)[1] if sub else os.path.basename(f)[:-6]
            try:
                fh = open(f, errors="replace")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if '"usage"' not in line or '"assistant"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                        m = d["message"]
                        u = m["usage"]
                        ts = iso(d["timestamp"])
                    except (ValueError, KeyError, TypeError):
                        continue
                    if not (t0 <= ts < t1) or m.get("model") in (None, "<synthetic>"):
                        continue
                    key = (m.get("id"), d.get("requestId"), f)
                    c = calls.get(key)
                    if c is None:
                        c = calls[key] = {"login": login, "session": session, "sub": sub, "file": f, "cwd": d.get("cwd", ""),
                                          "model": m["model"], "ts": ts, "u": u, "tools": [], "rbash": True}
                    for b in m.get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            c["tools"].append(b.get("name"))
                            if b.get("name") == "Bash":
                                cmd = (b.get("input") or {}).get("command", "")
                                c["rbash"] = c["rbash"] and reads_only(cmd)
    return list(calls.values())


def cost(c):
    u = c["u"]
    inp, cr, cw = u.get("input_tokens") or 0, u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0
    out = u.get("output_tokens") or 0
    cc = u.get("cache_creation") or {}
    w1 = cc.get("ephemeral_1h_input_tokens") or 0
    w5 = cw - w1
    r_in, r_w5, r_w1, r_rd, r_out = tw.price(c["model"], inp + cr + cw)
    parts = {"in": inp * r_in, "write": w5 * r_w5 + w1 * r_w1, "read": cr * r_rd, "out": out * r_out}
    parts = {k: v / 1e6 for k, v in parts.items()}
    c["ctx"] = inp + cr + cw
    c["tok"] = {"in": inp, "write": cw, "read": cr, "out": out}
    c["usd"] = parts
    c["total"] = sum(parts.values())
    c["w1"] = w1
    c["r_rd"] = r_rd


def short_model(m):
    m = m.lower()
    for k in ("fable", "opus", "sonnet", "haiku"):
        if k in m:
            return k + ("-" + re.sub(r"[^0-9]+", ".", m.split(k, 1)[1]).strip(".") if m.split(k, 1)[1] else "")
    return m


def analyse(calls, seats):
    for c in calls:
        cost(c)
    calls.sort(key=lambda c: (c["file"], c["ts"]))
    waste = defaultdict(float)
    prev = {}
    for c in calls:
        dear = any(k in c["model"].lower() for k in DEAR)
        # big: cache reads beyond 100k of context, on every call
        if c["ctx"] > 100_000:
            c.setdefault("w", {})["big"] = min(c["tok"]["read"], c["ctx"] - 100_000) * c["r_rd"] / 1e6
        # cold: a big cache write after a gap longer than the cache TTL
        gap = c["ts"] - prev.get(c["file"], c["ts"])
        ttl = 3600 if c["w1"] else 300
        if c["tok"]["write"] >= 30_000 and gap > ttl:
            c.setdefault("w", {})["cold"] = c["usd"]["write"]
        prev[c["file"]] = c["ts"]
        c["isfetch"] = dear and bool(c["tools"]) and all(t in tw.FETCH for t in c["tools"]) and c["rbash"]
        if dear and c["sub"]:
            c.setdefault("w", {})["opsub"] = c["total"]
    # fetch: only runs of 3+ read-only Opus calls in a row (one read before an edit is fine)
    run = []
    for c in calls + [{"file": None, "isfetch": False}]:
        if c["isfetch"] and (not run or run[-1]["file"] == c["file"]):
            run.append(c)
            continue
        if len(run) >= 3:
            for x in run:
                x.setdefault("w", {})["fetch"] = x["total"]
        run = [c] if c["isfetch"] else []
    for c in calls:
        for k, v in c.get("w", {}).items():
            waste[k] += v

    def seat_of(c):
        s = seats.get(c["session"])
        if s:
            return s if len(s) <= 44 else s[:43] + "…"
        tail = [p for p in c["cwd"].split("/") if p][-1:] or ["?"]
        return "(" + tail[0] + ")"

    by = {k: defaultdict(lambda: defaultdict(float)) for k in ("seat", "model", "kind", "login", "session", "hour", "ctx")}
    for c in calls:
        seat = seat_of(c)
        keys = {"seat": seat, "model": short_model(c["model"]), "kind": "sub" if c["sub"] else "main", "login": c["login"],
                "session": (c["session"], seat, c["login"]), "hour": time.strftime("%H", time.localtime(c["ts"])),
                "ctx": next(f"<{b}k" for b in (50, 100, 200, 300, 500, 1100) if c["ctx"] < b * 1000)}
        for dim, k in keys.items():
            row = by[dim][k]
            row["usd"] += c["total"]
            row["calls"] += 1
            row["ctx"] += c["ctx"]
            row["maxctx"] = max(row["maxctx"], c["ctx"])
            for p, v in c["usd"].items():
                row["usd_" + p] += v
            for p, v in c.get("w", {}).items():
                row["w_" + p] += v
            if dim == "seat":
                row["sub_usd"] += c["total"] if c["sub"] else 0
                row["dear_usd"] += c["total"] if any(k in c["model"].lower() for k in DEAR) else 0
    total = sum(c["total"] for c in calls)
    return {"total": total, "calls": len(calls), "waste": dict(waste), "by": by}


def codex(t0, t1):
    """Codex tokens in the window: per file, last cumulative total in window minus last before it."""
    tot = defaultdict(int)
    for f in glob.glob(CODEX + "/**/*.jsonl", recursive=True):
        try:
            if os.path.getmtime(f) < t0:
                continue
            before, last = {}, {}
            for line in open(f, errors="replace"):
                if '"token_count"' not in line:
                    continue
                d = json.loads(line)
                info = (d.get("payload") or {}).get("info") or {}
                t = info.get("total_token_usage")
                if not t:
                    continue
                ts = iso(d["timestamp"])
                if ts < t0:
                    before = t
                elif ts < t1:
                    last = t
            for k, v in last.items():
                if isinstance(v, int):
                    tot[k] += v - (before.get(k) or 0)
        except (OSError, ValueError, KeyError):
            continue
    return dict(tot)


def fmt(r, top, cdx):
    T = r["total"] or 1
    L = [f"Total ${r['total']:,.0f} list-price over {r['calls']:,} API calls."]

    def table(dim, title, n, keyfmt=str):
        rows = sorted(r["by"][dim].items(), key=lambda kv: -kv[1]["usd"])[:n]
        L.append(f"\n## {title}\n")
        if dim == "seat":
            L.append("| seat | $ | share | sub-agent $ | Opus/Fable $ | calls | avg ctx | max ctx | big | cold | fetch |")
            L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        else:
            L.append("| key | $ | share | calls | avg ctx | max ctx | read $ | write $ | out $ |")
            L.append("|---|---|---|---|---|---|---|---|---|")
        for k, v in rows:
            avg = v["ctx"] / max(v["calls"], 1)
            if dim == "seat":
                L.append(f"| {k} | {v['usd']:,.0f} | {v['usd']/T:.0%} | {v['sub_usd']:,.0f} | {v['dear_usd']:,.0f} | "
                         f"{v['calls']:,.0f} | {avg/1e3:,.0f}k | {v['maxctx']/1e3:,.0f}k | {v['w_big']:,.0f} | "
                         f"{v['w_cold']:,.0f} | {v['w_fetch']:,.0f} |")
            else:
                L.append(f"| {keyfmt(k)} | {v['usd']:,.0f} | {v['usd']/T:.0%} | {v['calls']:,.0f} | {avg/1e3:,.0f}k | "
                         f"{v['maxctx']/1e3:,.0f}k | {v['usd_read']:,.0f} | {v['usd_write']:,.0f} | {v['usd_out']:,.0f} |")

    table("seat", "By seat", 25)
    table("kind", "Main vs sub-agents", 2)
    table("model", "By model", 8)
    table("login", "By login", 3)
    table("session", f"Top {top} sessions", top, lambda k: f"{k[1]} `{k[0][:8]}` ({k[2]})")
    table("ctx", "By context size per call", 6)
    table("hour", "By hour (local)", 24)
    w = r["waste"]
    L.append("\n## Waste signals ($, overlapping)\n")
    for k, label in (("big", "cache reads above 100k context"), ("cold", "cache re-writes after an idle gap"),
                     ("fetch", "Opus/Fable read-only calls in runs of 3+"), ("opsub", "sub-agents on Opus/Fable")):
        L.append(f"- {label}: ${w.get(k, 0):,.0f} ({w.get(k, 0)/T:.0%})")
    if cdx:
        L.append(f"\nCodex: {cdx.get('total_tokens', 0):,} tokens ({cdx.get('cached_input_tokens', 0):,} cached input, "
                 f"{cdx.get('output_tokens', 0):,} output).")
    return "\n".join(L)


def daily(seats, day=None):
    """One day (default yesterday, local) into LEDGER.md + data/daily.jsonl; flag a seat at 2x its 7-day mean, >$50."""
    y = dt.date.fromisoformat(day) if day else dt.date.today() - dt.timedelta(days=1)
    t0 = time.mktime(y.timetuple())
    r = analyse(scan(t0, t0 + 86400), seats)
    seat_usd = {k: round(v["usd"], 2) for k, v in r["by"]["seat"].items()}
    os.makedirs(HERE + "/data", exist_ok=True)
    hist_f = HERE + "/data/daily.jsonl"
    hist = [json.loads(l) for l in open(hist_f)] if os.path.exists(hist_f) else []
    if any(h["day"] == str(y) for h in hist):
        print(f"{y} already in the ledger")
        return
    hist = [h for h in hist if h["day"] < str(y)][-7:]
    flags = []
    for s, v in seat_usd.items():
        prior = [h["seats"].get(s, 0) for h in hist]
        mean = sum(prior) / len(prior) if prior else 0
        if v > 50 and prior and v > 2 * mean:
            flags.append(f"{s} ${v:,.0f} vs ${mean:,.0f}/day")
    row = {"day": str(y), "total": round(r["total"], 2), "calls": r["calls"], "seats": seat_usd,
           "kind": {k: round(v["usd"], 2) for k, v in r["by"]["kind"].items()},
           "waste": {k: round(v, 2) for k, v in r["waste"].items()}, "flags": flags}
    with open(hist_f, "a") as fh:
        fh.write(json.dumps(row) + "\n")
    top = ", ".join(f"{s} {v:,.0f}" for s, v in sorted(seat_usd.items(), key=lambda kv: -kv[1])[:5])
    sub = row["kind"].get("sub", 0)
    line = (f"| {y} | {r['total']:,.0f} | {sub/max(r['total'],1):.0%} | {top} | "
            f"{row['waste'].get('big',0):,.0f} / {row['waste'].get('cold',0):,.0f} / {row['waste'].get('fetch',0):,.0f} | "
            f"{'; '.join(flags) or '-'} |\n")
    with open(HERE + "/LEDGER.md", "a") as fh:
        fh.write(line)
    print(line, end="")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--day")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--no-codex", action="store_true")
    a = ap.parse_args()
    seats = seat_map()
    if a.daily:
        return daily(seats, a.day)
    if a.day:
        t0 = time.mktime(dt.date.fromisoformat(a.day).timetuple())
        t1 = t0 + 86400
    else:
        t1 = time.time()
        t0 = t1 - a.hours * 3600
    r = analyse(scan(t0, t1), seats)
    cdx = {} if a.no_codex else codex(t0, t1)
    print(fmt(r, a.top, cdx))
    if a.json:
        by = {d: {(" ".join(k) if isinstance(k, tuple) else k): dict(v) for k, v in rows.items()} for d, rows in r["by"].items()}
        json.dump({"window": [t0, t1], "total": r["total"], "calls": r["calls"], "waste": r["waste"], "by": by,
                   "codex": cdx}, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    sys.exit(main())
