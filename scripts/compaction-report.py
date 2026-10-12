#!/usr/bin/env python3
"""compaction-report: where compactions happen and what they cost.

Measures session compaction frequency, context sizes before/after, and cost burden at high context.

  compaction-report [--days 7] [--json OUT]
"""
import argparse, glob, json, os, re, time, statistics
from collections import defaultdict

HOME = os.path.expanduser("~")
ROOTS = [HOME + "/.claude-siso", HOME + "/.config/claude-siso-3"]
PRICE = {"opus": (5, 25), "fable": (5, 25), "sonnet": (3, 15), "haiku-5": (0.1, 0.5), "haiku": (1, 5)}


def price(model):
    m = (model or "").lower()
    for k, v in PRICE.items():
        if k in m:
            return v
    return PRICE["opus"]


def trigger(t):
    t = t.lstrip()
    if "task-notification>" in t[:200]: return "sub-agent finished"
    if "Stop hook" in t[:300] or "hook blocking error" in t[:400]: return "hook"
    if "<cross-session-message" in t[:200] or t.startswith("Another Claude session") or re.match(r"^[A-Z0-9-]{3,}\s*(:|→|->)", t): return "another agent"
    if t.startswith("This session is being continued") or "Compacted" in t[:80]: return "compaction"
    if t.startswith(("<system-reminder>", "[SYSTEM", "Caveat:", "<local-command", "<command-")) or "heard from you" in t[:300]: return "system"
    return "Shaan"


def seat(cwd):
    p = (cwd or "?").rstrip("/").split("/")
    if "worktrees" in p:
        i = p.index("worktrees")
        return "/".join(p[i + 1:i + 3]) + " (worktree)"
    if any(x.startswith(("siso-ephemeral", "claude-501")) or x.startswith("tmp") for x in p) or (len(p) > 1 and p[1] in ("private", "tmp", "var")):
        return "(temp dir)"
    return p[-1] or "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json")
    a = ap.parse_args()
    since = time.time() - a.days * 86400

    files = set()
    for r in ROOTS:
        for x in glob.glob(r + "/projects/**/*.jsonl", recursive=True):
            if "/subagents/" not in x:
                try:
                    if os.path.getmtime(x) >= since:
                        files.add(os.path.realpath(x))
                except OSError:
                    pass

    # per-seat: list of (compaction_time, ctx_before, ctx_after, cost_before, cost_at, cost_after, model)
    seat_compactions = defaultdict(list)
    seat_high_cost = defaultdict(lambda: defaultdict(float))  # seat -> ">150k"|">300k"|">500k" -> usd
    seat_total_cost = defaultdict(float)

    seen_ids = set()

    for f in sorted(files):
        s = seat(f)
        calls = []  # all assistant calls in order: (ts, model, ctx, usd, msg_id)
        compaction_indices = []  # indices into calls where compactions occur

        try:
            fh = open(f, errors="ignore")
        except OSError:
            continue

        for line in fh:
            if '"type":"user"' not in line and '"type":"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue

            msg = o.get("message") or {}
            # Compaction messages use uuid instead of message.id or requestId
            msg_id = msg.get("id") or o.get("requestId") or o.get("uuid")

            if msg_id and msg_id in seen_ids:
                continue
            if not msg_id:
                continue
            seen_ids.add(msg_id)

            try:
                ts = time.mktime(time.strptime(o.get("timestamp", "")[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            except ValueError:
                ts = 0

            if ts < since:
                continue

            if o["type"] == "user":
                c = msg.get("content")
                first = c if isinstance(c, str) else (c[0].get("text", "") if isinstance(c, list) and c and c[0].get("type") == "text" else None)
                is_compaction = first is not None and (trigger(first) == "compaction" or o.get("isCompactSummary"))
                if is_compaction:
                    compaction_indices.append(len(calls))

            elif o["type"] == "assistant":
                model = msg.get("model", "?")
                u = msg.get("usage") or {}

                if not u or model == "<synthetic>":
                    continue

                pin, pout = price(model)
                cc = u.get("cache_creation") or {}
                w1h = cc.get("ephemeral_1h_input_tokens", 0)
                w5m = u.get("cache_creation_input_tokens", 0) - w1h
                rd = u.get("cache_read_input_tokens", 0)
                inp = u.get("input_tokens", 0)
                out = u.get("output_tokens", 0)

                ctx = inp + w5m + w1h + rd
                usd = (inp * pin + w5m * pin * 1.25 + w1h * pin * 2 + rd * pin * 0.1 + out * pout) / 1e6

                seat_total_cost[s] += usd

                # Track cost in high-context bands
                if ctx > 500_000:
                    seat_high_cost[s][">500k"] += usd
                if ctx > 300_000:
                    seat_high_cost[s][">300k"] += usd
                if ctx > 150_000:
                    seat_high_cost[s][">150k"] += usd

                calls.append((ts, model, ctx, usd, msg_id))

        # Find compactions and their surrounding context
        # Compaction at index i means: call at i-1 is before, call at i is after
        for comp_idx in compaction_indices:
            if comp_idx > 0 and comp_idx < len(calls):
                # Call before compaction
                _, model_before, ctx_before, cost_before, _ = calls[comp_idx - 1]
                # Call after compaction (first call after the compaction user message)
                _, model_after, ctx_after, cost_at, _ = calls[comp_idx]
                cost_after = calls[comp_idx + 1][3] if comp_idx + 1 < len(calls) else None

                ts = calls[comp_idx - 1][0]
                seat_compactions[s].append((ts, ctx_before, ctx_after, cost_before, cost_at, cost_after, model_before))

    # Compute statistics per seat
    results = {}
    for s in sorted(seat_compactions.keys()):
        comps = seat_compactions[s]
        if not comps:
            continue

        ctx_befores = [c[1] for c in comps]
        ctx_afters = [c[2] for c in comps]
        costs_before = [c[3] for c in comps if c[3] is not None]
        costs_at = [c[4] for c in comps if c[4] is not None]
        costs_after = [c[5] for c in comps if c[5] is not None]
        times = [c[0] for c in comps]

        # Time between compactions
        intervals = []
        for i in range(1, len(times)):
            intervals.append((times[i] - times[i-1]) / 60)  # minutes
        median_interval = statistics.median(intervals) if intervals else 0

        # High-context cost shares
        total = seat_total_cost[s]
        high_150 = seat_high_cost[s].get(">150k", 0)
        high_300 = seat_high_cost[s].get(">300k", 0)
        high_500 = seat_high_cost[s].get(">500k", 0)

        results[s] = {
            "compactions": len(comps),
            "median_ctx_before": int(statistics.median(ctx_befores)) if ctx_befores else 0,
            "max_ctx_before": int(max(ctx_befores)) if ctx_befores else 0,
            "median_ctx_after": int(statistics.median(ctx_afters)) if ctx_afters else 0,
            "median_cost_before": round(statistics.median(costs_before), 4) if costs_before else 0,
            "median_cost_at": round(statistics.median(costs_at), 4) if costs_at else 0,
            "median_cost_after": round(statistics.median(costs_after), 4) if costs_after else 0,
            "median_minutes_between": round(median_interval, 1),
            "share_150k": round(high_150 / total, 4) if total else 0,
            "share_300k": round(high_300 / total, 4) if total else 0,
            "share_500k": round(high_500 / total, 4) if total else 0,
            "total_cost": round(total, 2),
        }

    # Totals
    total_comps = sum(r["compactions"] for r in results.values())
    total_cost = sum(r["total_cost"] for r in results.values())
    total_high_150 = sum(seat_high_cost[s].get(">150k", 0) for s in seat_high_cost)
    total_high_300 = sum(seat_high_cost[s].get(">300k", 0) for s in seat_high_cost)
    total_high_500 = sum(seat_high_cost[s].get(">500k", 0) for s in seat_high_cost)

    totals = {
        "days": a.days,
        "seats": len(results),
        "total_compactions": total_comps,
        "total_cost": round(total_cost, 2),
        "share_150k": round(total_high_150 / total_cost, 4) if total_cost else 0,
        "share_300k": round(total_high_300 / total_cost, 4) if total_cost else 0,
        "share_500k": round(total_high_500 / total_cost, 4) if total_cost else 0,
    }

    if a.json:
        json.dump({"totals": totals, "seats": results}, open(a.json, "w"), indent=1)

    # Print results
    print(f"=== Compaction Report ({a.days} days) ===\n")
    print(f"Totals: {total_comps} compactions across {len(results)} seats, ${total_cost:.2f}")
    print(f"  High-context cost: >{150_000:,} tokens {totals['share_150k']:.0%}, >{300_000:,} {totals['share_300k']:.0%}, >{500_000:,} {totals['share_500k']:.0%}\n")

    # Top 8 by cost
    top = sorted(results.items(), key=lambda kv: -kv[1]["total_cost"])[:8]
    for s, r in top:
        print(f"{s:40} | comps {r['compactions']:2d} | med ctx before {r['median_ctx_before']:7,} / after {r['median_ctx_after']:7,} | cost ${r['total_cost']:7.2f}")
        print(f"{'':40} | costs: before ${r['median_cost_before']:.4f} / at ${r['median_cost_at']:.4f} / after ${r['median_cost_after']:.4f} | >{150_000:,} {r['share_150k']:.0%}")


if __name__ == "__main__":
    main()
