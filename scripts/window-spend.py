#!/usr/bin/env python3
"""window-spend — Claude spend per chat inside one time window (FLEET-COST, 7 Oct 2026).

Shaan, 7 Oct ~00:15: "see why we ran through our usage so quickly the last 5 hour window". spend-ledger counts by day;
this reuses its parser (counts only, never message text) and keeps the steps inside [FROM, TO).

  window-spend FROM TO [--json]      times as ISO with offset, e.g. 2026-10-06T19:09+07:00

Per chat: steps (model calls), tokens in / cache write / cache read / out, average context per call, the dollar
equivalent at list prices (config/prices.json), and its sub-agents apart. Names: the session's agentName, then the
Agent Base host record (~/.local/state/agent-base/hosts/*.json), then herdr.
"""
import collections, datetime as dt, glob, importlib.machinery, importlib.util, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def ledger():
    loader = importlib.machinery.SourceFileLoader("spend_ledger", os.path.join(HERE, "bin", "spend-ledger"))
    spec = importlib.util.spec_from_loader("spend_ledger", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def host_names():
    names = {}
    for f in glob.glob(os.path.expanduser("~/.local/state/agent-base/hosts/**/*.json"), recursive=True):
        try:
            d = json.load(open(f))
        except (OSError, ValueError):
            continue
        if d.get("session") and d.get("name"):
            names[d["session"]] = {"name": d["name"], "effort": d.get("effort"), "model": d.get("model")}
    return names


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    lo, hi = (dt.datetime.fromisoformat(a).timestamp() for a in argv[:2])
    sl = ledger()
    days = sorted({dt.datetime.fromtimestamp(t, sl.TZ).date().isoformat() for t in (lo, hi)})
    ev = [{**e, "t": e["t"].timestamp()} for e in sl.claude_events(days)]
    ev = [e for e in ev if lo <= e["t"] < hi]
    hosts = host_names()
    by = collections.OrderedDict()
    for e in sorted(ev, key=lambda e: e["t"]):
        h = hosts.get(e["session"], {})
        name = h.get("name") or e["actor"] or e["session"][:8]
        r = by.setdefault(e["session"], {"chat": name, "session": e["session"], "effort": h.get("effort"),
                                          "models": collections.Counter(), "steps": 0, "in": 0, "cw": 0, "cr": 0,
                                          "out": 0, "usd": 0.0, "first": e["t"], "last": e["t"],
                                          "sub": {"steps": 0, "tokens": 0, "usd": 0.0, "agents": set()}})
        tk = e["tokens"]
        r["last"] = e["t"]
        if e["kind"] == "subagent":
            r["sub"]["steps"] += 1
            r["sub"]["tokens"] += tk["in"] + tk["cw"] + tk["cr"] + tk["out"]
            r["sub"]["usd"] += e["usd"] or 0
            r["sub"]["agents"].add(e["sub"]["id"])
            r["models"]["sub:" + e["model"]] += 1
            continue
        r["steps"] += 1
        for k in ("in", "cw", "cr", "out"):
            r[k] += tk[k]
        r["usd"] += e["usd"] or 0
        r["models"][e["model"]] += 1
    rows = []
    for r in by.values():
        ctx_tokens = r["in"] + r["cw"] + r["cr"]
        rows.append({**r, "models": dict(r["models"]), "avg_ctx": round(ctx_tokens / r["steps"]) if r["steps"] else 0,
                     "total": ctx_tokens + r["out"], "sub": {**r["sub"], "agents": len(r["sub"]["agents"])},
                     "first": dt.datetime.fromtimestamp(r["first"], sl.TZ).strftime("%H:%M"),
                     "last": dt.datetime.fromtimestamp(r["last"], sl.TZ).strftime("%H:%M")})
    rows.sort(key=lambda r: -(r["usd"] + r["sub"]["usd"]))
    tot_usd = sum(r["usd"] + r["sub"]["usd"] for r in rows) or 1
    if "--json" in argv:
        print(json.dumps({"from": argv[0], "to": argv[1], "rows": rows, "usd": tot_usd}, indent=1))
        return 0
    print(f"{'chat':<22}{'eff':>5}{'steps':>7}{'avg ctx':>9}{'cache rd':>10}{'cache wr':>10}{'out':>8}{'$':>9}{'share':>7}  sub(n/steps/$)  span")
    for r in rows:
        u = r["usd"] + r["sub"]["usd"]
        s = r["sub"]
        print(f"{r['chat'][:21]:<22}{(r['effort'] or '-')[:4]:>5}{r['steps']:>7}{r['avg_ctx'] // 1000:>8}k{r['cr'] / 1e6:>9.1f}M"
              f"{r['cw'] / 1e6:>9.1f}M{r['out'] / 1e3:>7.0f}k{u:>9.2f}{100 * u / tot_usd:>6.1f}%  "
              f"{s['agents']}/{s['steps']}/{s['usd']:.2f}  {r['first']}-{r['last']}")
    print(f"total ${tot_usd:.2f} over {sum(r['steps'] + r['sub']['steps'] for r in rows)} calls, {len(rows)} chats")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
