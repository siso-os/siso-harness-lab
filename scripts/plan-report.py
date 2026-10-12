#!/usr/bin/env python3
"""plan-report.py [--day YYYY-MM-DD] [--write] [--json] — one day of Claude plan usage, the STACK-OPT scoreboard.

STACK-OPT item 7 (2 Oct 2026). Grown from A0's .agents/efficiency/plan-usage.py. For one local day it reads every
Claude transcript (both logins, subagent transcripts included) and reports:
  - weighted usage (API list prices per model as a proxy for plan usage) and its parts (cache reads/writes, output);
  - steps (unique assistant messages) and average context per step (fresh + cache write + cache read);
  - finished items = A0-inbox lines that day with an upper-case DONE or opening with "done", and weighted usage and steps per finished item;
  - rework steps = Stop-hook feedback turns; wakes = task/Monitor notifications;
  - share by agent (name from the transcript; subagents fold into their parent).
Targets (A0 brief): average context per step < 150k by 4 Oct; weighted usage per finished item down 50% in a week
from the 1-2 Oct baseline. --write saves .agents/efficiency/daily/<day>.md and appends a row to daily.jsonl.
Run on demand (no scheduling, DECISIONS.md); A0 runs it each morning for the day before.
"""
import argparse, collections, datetime as dt, glob, json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EFF = os.path.join(HERE, ".agents", "efficiency")
ROOTS = [os.environ.get("PLAN_REPORT_ROOTS")] if os.environ.get("PLAN_REPORT_ROOTS") else [
    "~/.config/claude-siso-3/projects", "~/.claude/projects"]
INBOX = os.environ.get("PLAN_REPORT_INBOX") or os.path.expanduser(
    "~/SISO_Workspace/SISO_Agents/agent-zero/siso-firstmate/.agents/a0/inbox.log")
# $ per 1M tokens: fresh input, cache write (1h), cache read, output, from the one price table config/prices.json
# (Anthropic API list price, cited there). Until 2 Oct this weighted every Opus at 15/18.75/1.5/75 (Opus 4 rates),
# ~3.7x Opus 5.5's real 4/8/0.2/20; weighted figures in daily.jsonl before so-020 used those old weights.
_PRICES = json.load(open(os.environ.get("SISO_PRICES") or os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "config", "prices.json")))


class _Price(dict):
    """PRICE[model] -> (in, cw1h, cr, out) by the table's first matching pattern; unknown models price as Opus 5.5."""
    def __missing__(self, model):
        row = next((r for r in _PRICES["claude"] if re.search(r["match"], model)), None) or \
            next(r for r in _PRICES["claude"] if r["match"] == "opus-5-5")
        self[model] = (row["in"], row["cw1h"], row["cr"], row["out"])
        return self[model]


PRICE = _Price()
TARGET_CTX = 150_000
TZ = dt.datetime.now().astimezone().tzinfo
NAMES = {}  # transcript -> agent name (first agentName/customTitle seen)


def family(model):
    """The model id PRICE is looked up by (bare aliases like 'sonnet' mapped to their current model)."""
    m = (model or "").lower()
    return _PRICES["aliases"].get(m, m) or "claude-opus-5-5"


def day_of(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(TZ).date().isoformat()


def text_of(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    return " ".join(x.get("text", "") for x in (c or []) if isinstance(x, dict) and x.get("type") == "text")


def scan(day):
    lo = dt.datetime.fromisoformat(day).replace(tzinfo=TZ).timestamp()
    agents = collections.defaultdict(collections.Counter)
    # Each transcript once, each message once (EFFICIENCY so-020): old project folder names link to the same file (one
    # HALO-UI session was read 4 times on 2 Oct), and claude-move copies a session to the other login.
    read, seen_all = set(), set()
    for root in ROOTS:
        root = os.path.expanduser(root)
        files = glob.glob(root + "/*/*.jsonl") + glob.glob(root + "/*/*/subagents/*.jsonl")
        for f in files:
            if os.path.getmtime(f) < lo or os.path.realpath(f) in read:
                continue
            read.add(os.path.realpath(f))
            sub = "/subagents/" in f
            parent = os.path.join(os.path.dirname(os.path.dirname(f)) + ".jsonl") if sub else f
            seen = seen_all if not sub else set()
            with open(f, errors="replace") as fh:
                lines = fh.readlines()
            for line in lines:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                nm = d.get("agentName") or d.get("customTitle")
                if nm:
                    NAMES.setdefault(parent if sub else f, nm)
                ts = d.get("timestamp")
                if not ts or day_of(ts) != day:
                    continue
                a = agents[(parent if sub else f)]
                if d.get("type") == "user":
                    t = text_of(d.get("message"))
                    if "Stop hook feedback" in t or "stop hook" in t.lower() and "blocking" in t.lower():
                        a["rework"] += 1
                    elif "task-notification" in t or "Monitor event" in t or "SYSTEM NOTIFICATION" in t:
                        a["wakes"] += 1
                elif d.get("type") == "assistant":
                    m = d.get("message") or {}
                    if m.get("id") in seen:
                        continue
                    seen.add(m.get("id"))
                    u = m.get("usage") or {}
                    inp, cw, cr, out = (u.get(k, 0) for k in (
                        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
                    p = PRICE[family(m.get("model"))]
                    a["steps"] += 1
                    a["ctx"] += inp + cw + cr
                    a["cr_w"] += cr * p[2] / 1e6
                    a["cw_w"] += cw * p[1] / 1e6
                    a["out_w"] += out * p[3] / 1e6
                    a["in_w"] += inp * p[0] / 1e6
                    if sub:
                        a["sub_steps"] += 1
                    else:
                        a["main_steps"] += 1
                        a["main_ctx"] += inp + cw + cr
    return agents


def finished(day):
    """DONE lines per agent on <day>. The inbox carries HH:MM only, so days are inferred: the last line is on the
    file's modified date, and each backwards step across midnight (the clock jumping forward by over 6 h when read
    in reverse) is one day earlier."""
    n = collections.Counter()
    try:
        lines = open(INBOX, errors="replace").read().splitlines()
        cur = dt.datetime.fromtimestamp(os.path.getmtime(INBOX), TZ).date()
    except OSError:
        return n
    later = None
    for l in reversed(lines):
        m = re.match(r"(\d\d):(\d\d) ", l)
        if not m:
            continue
        mins = int(m[1]) * 60 + int(m[2])
        if later is not None and mins - later > 360:
            cur -= dt.timedelta(days=1)
        later = mins
        d = re.match(r"\d\d:\d\d ([A-Z0-9][A-Za-z0-9_-]*)[^:]*: (?:.*\bDONE\b|done\b)", l)
        if d and cur.isoformat() == day:
            n[d[1]] += 1
    return n


def report(day):
    agents = scan(day)
    names = {f: NAMES.get(f) or os.path.basename(f)[:8] for f in agents}
    tot = collections.Counter()
    by = collections.defaultdict(collections.Counter)
    for f, a in agents.items():
        for k in ("steps", "main_steps", "sub_steps", "ctx", "main_ctx", "cr_w", "cw_w", "out_w", "in_w", "rework", "wakes"):
            tot[k] += a[k]
            by[names[f]][k] += a[k]
    w = lambda c: c["cr_w"] + c["cw_w"] + c["out_w"] + c["in_w"]
    weighted = w(tot)
    done = finished(day)
    items = sum(done.values())
    avg_ctx = tot["main_ctx"] / tot["main_steps"] if tot["main_steps"] else 0
    return {
        "day": day, "weighted": round(weighted, 1),
        "parts": {k: round(tot[k + "_w"] / weighted, 3) if weighted else 0 for k in ("cr", "cw", "out", "in")},
        "steps": tot["steps"], "subagent_steps": tot["sub_steps"],
        "avg_context_per_step": round(avg_ctx), "target_avg_context": TARGET_CTX,
        "finished_items": items, "weighted_per_item": round(weighted / items, 1) if items else None,
        "steps_per_item": round(tot["steps"] / items, 1) if items else None,
        "rework_steps": tot["rework"], "wakes": tot["wakes"],
        "agents": sorted(({"agent": n, "weighted": round(w(c), 1), "share": round(w(c) / weighted, 3) if weighted else 0,
                           "steps": c["steps"], "avg_ctx": round(c["main_ctx"] / c["main_steps"]) if c["main_steps"] else 0,
                           "done": done.get(n, 0), "rework": c["rework"], "wakes": c["wakes"]}
                          for n, c in by.items() if c["steps"]), key=lambda r: -r["weighted"]),
    }


def markdown(r):
    ok = "✅" if r["avg_context_per_step"] < r["target_avg_context"] else "❌"
    out = [f"# Plan usage {r['day']}", "",
           f"- Weighted usage {r['weighted']:,.0f} (cache reads {r['parts']['cr']:.0%}, writes {r['parts']['cw']:.0%}, "
           f"output {r['parts']['out']:.0%})",
           f"- Average context per step {r['avg_context_per_step']/1000:.0f}k {ok} target < {r['target_avg_context']//1000}k; "
           f"{r['steps']:,} steps ({r['subagent_steps']:,} in subagents)",
           f"- Finished items (DONE/done lines in the A0 inbox) {r['finished_items']}: "
           f"{r['weighted_per_item'] if r['weighted_per_item'] is not None else '-'} weighted and "
           f"{r['steps_per_item'] if r['steps_per_item'] is not None else '-'} steps per item",
           f"- Rework steps (Stop-hook feedback) {r['rework_steps']}; wakes {r['wakes']}", "",
           "| Agent | Share | Weighted | Steps | Avg ctx | DONE | Rework | Wakes |", "|---|---|---|---|---|---|---|---|"]
    for a in r["agents"][:20]:
        out.append(f"| {a['agent']} | {a['share']:.0%} | {a['weighted']:,.0f} | {a['steps']} | {a['avg_ctx']/1000:.0f}k | "
                   f"{a['done']} | {a['rework']} | {a['wakes']} |")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--day", default=(dt.datetime.now(TZ).date() - dt.timedelta(days=1)).isoformat())
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = report(a.day)
    if a.json:
        print(json.dumps(r, indent=1))
    else:
        print(markdown(r), end="")
    if a.write:
        os.makedirs(os.path.join(EFF, "daily"), exist_ok=True)
        open(os.path.join(EFF, "daily", f"{a.day}.md"), "w").write(markdown(r))
        with open(os.path.join(EFF, "daily.jsonl"), "a") as f:
            f.write(json.dumps({k: v for k, v in r.items() if k != "agents"}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
