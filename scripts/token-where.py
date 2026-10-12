#!/usr/bin/env python3
"""token-where: where Claude plan tokens go, per seat and per kind of turn, weighted by what they cost.

Raw token counts are dominated by cache reads, which cost a tenth of fresh input. So every number here is also given
as list-price dollars (the best public proxy for how fast a call drains the plan): Opus/Fable $5 in, $25 out; Sonnet
$3/$15; Haiku 4.5 $1/$5; Haiku 5.5 $0.10/$0.50; cache read 0.1x input, 5-minute cache write 1.25x, 1-hour cache write 2x.

  token-where [--hours 24] [--json OUT] [--root DIR ...]

Splits: who started the turn (Shaan, another agent, compaction, hook, finished sub-agent, system), seat (cwd), model,
sub-agents, and what fills context: tool output by tool, the cost of carrying it on every later call, and files read
twice. Headline: dollars per Shaan request (the number to push down).
"""
import argparse, glob, json, os, re, time
from collections import defaultdict

HOME = os.path.expanduser("~")
ROOTS = [HOME + "/.claude-siso", HOME + "/.config/claude-siso-3", HOME + "/.claude"]
# $/M tokens: input, 5m cache write, 1h cache write, cache read, output. Anthropic pricing page, 12 Oct 2026
# (_reference/anthropic/docs-platform/pages/about-claude-pricing.md). Haiku 5.5 doubles tier above a 100k prompt.
RATES = {"fable": (10, 12.5, 20, 0.25, 50), "opus-5": (4, 5, 8, 0.20, 20), "opus": (5, 6.25, 10, 0.5, 25),
         "sonnet-5": (2, 2.5, 4, 0.10, 10), "sonnet": (3, 3.75, 6, 0.3, 15), "haiku-5": (0.10, 0.125, 0.20, 0.01, 0.50),
         "haiku-5-long": (0.50, 0.625, 1, 0.05, 2.50), "haiku": (1, 1.25, 2, 0.10, 5)}


def price(model, ctx=0):
    m = (model or "").lower()
    for k in ("fable", "opus-5", "opus", "sonnet-5", "sonnet", "haiku-5", "haiku"):
        if k in m:
            return RATES["haiku-5-long"] if k == "haiku-5" and ctx > 100_000 else RATES[k]
    return RATES["opus-5"]


# harness-bench's own runs (scripts/harness-bench.py prompts) are measurement, not work: leave them out
BENCH = ("Do not edit anything.", "add a --top N option", "say hi")
FETCH = {"Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch", "LSP", "ToolSearch", "TaskOutput"}


def trigger(t):
    """Same classes as Agent Zero's stack-doctor."""
    t = t.lstrip()
    if "task-notification>" in t[:200]: return "sub-agent finished"
    if "Stop hook" in t[:300] or "hook blocking error" in t[:400]: return "hook"
    if "<cross-session-message" in t[:200] or t.startswith("Another Claude session") or re.match(r"^[A-Z0-9-]{3,}\s*(:|→|->)", t): return "another agent"
    if t.startswith("This session is being continued") or "Compacted" in t[:80]: return "compaction"
    if t.startswith(("<system-reminder>", "[SYSTEM", "Caveat:", "<local-command", "<command-")) or "heard from you" in t[:300]: return "system"
    return "Shaan"


def size(c):
    """Rough tokens in a tool_result content (chars/4; an image ~1.5k)."""
    if isinstance(c, str):
        return len(c) // 4
    n = 0
    for b in c or []:
        if isinstance(b, dict):
            n += len(b.get("text", "")) // 4 if b.get("type") == "text" else 1500 if b.get("type") == "image" else 0
    return n


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
    ap.add_argument("--hours", type=float, default=24)
    ap.add_argument("--json")
    ap.add_argument("--root", action="append")
    a = ap.parse_args()
    since = time.time() - a.hours * 3600
    files = set()
    for r in a.root or ROOTS:
        for x in glob.glob(r + "/projects/**/*.jsonl", recursive=True):
            try:
                if os.path.getmtime(x) >= since:
                    files.add(os.path.realpath(x))
            except OSError:
                pass

    agg = defaultdict(lambda: defaultdict(float))  # dim -> key -> dollars
    raw = defaultdict(float)
    tool_tok, tool_carry, tool_calls = defaultdict(float), defaultdict(float), defaultdict(int)
    reread_tok, reread_n, shaan_req, calls = 0.0, 0, 0, 0
    fetch_loop = {"usd": 0.0, "runs": 0}
    asked = set()
    big = defaultdict(float)
    seen = set()
    skipped = set()  # bench session ids; their sub-agents (in <session>/subagents/) go too
    for f in sorted(files, key=lambda f: "/subagents/" in f):
        sub = "/subagents/" in f
        if sub and f.split("/subagents/")[0].rsplit("/", 1)[-1] in skipped:
            continue
        cur = "sub-agent" if sub else "Shaan"
        names, reads, toolsof, seq = {}, {}, defaultdict(set), []
        shaan_seen = False
        pending = []  # tool results awaiting later calls: [tokens, tool, cost-per-token-of-read]
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
            c = msg.get("content")
            try:
                ts = time.mktime(time.strptime(o.get("timestamp", "")[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            except ValueError:
                ts = 0
            if o["type"] == "user":
                first = c if isinstance(c, str) else (c[0].get("text", "") if isinstance(c, list) and c and c[0].get("type") == "text" else None)
                if first is not None and not sub and not o.get("isSidechain"):
                    if not seq and not shaan_seen and any(b in first for b in BENCH):
                        skipped.add(os.path.basename(f)[:-6])
                        break
                    cur = trigger(first)
                    shaan_seen = True
                    if cur == "compaction":
                        pending, reads = [], {}
                    if cur == "Shaan" and ts >= since and (o.get("timestamp"), first[:200]) not in asked:  # a forked copy repeats them
                        asked.add((o.get("timestamp"), first[:200]))
                        shaan_req += 1
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            n = size(b.get("content"))
                            tool, path = names.get(b.get("tool_use_id"), ("?", None))
                            if ts >= since:
                                tool_tok[tool] += n
                                tool_calls[tool] += 1
                            pending.append([n, tool])
                            if tool == "Read" and path:
                                if path in reads and ts >= since:
                                    reread_tok += n
                                    reread_n += 1
                                reads[path] = 1
                continue
            mid = msg.get("id") or o.get("requestId")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        names[b.get("id")] = (b.get("name", "?"), inp.get("file_path") if isinstance(inp, dict) else None)
                        toolsof[mid].add(b.get("name", "?"))
            if not mid or mid in seen:
                continue
            seen.add(mid)
            u = msg.get("usage") or {}
            model = msg.get("model", "?")
            if model == "<synthetic>" or not u:
                continue
            rd, inp, out = u.get("cache_read_input_tokens", 0), u.get("input_tokens", 0), u.get("output_tokens", 0)
            r_in, r_w5, r_w1, r_rd, r_out = price(model, inp + rd + u.get("cache_creation_input_tokens", 0))
            cc = u.get("cache_creation") or {}
            w1h = cc.get("ephemeral_1h_input_tokens", 0)
            w5m = u.get("cache_creation_input_tokens", 0) - w1h
            # every earlier tool result rides along on this call as cached input
            for p in pending:
                if ts >= since:
                    tool_carry[p[1]] += p[0] * r_rd / 1e6
            if ts < since:
                continue
            calls += 1
            usd = (inp * r_in + w5m * r_w5 + w1h * r_w1 + rd * r_rd + out * r_out) / 1e6
            ctx = inp + w5m + w1h + rd
            kind = "sub-agent" if sub or o.get("isSidechain") else cur
            for dim, key in (("turn", kind), ("seat", seat(o.get("cwd"))), ("model", model), ("entry", o.get("entrypoint", "?"))):
                agg[dim][key] += usd
            agg["part"]["output"] += out * r_out / 1e6
            agg["part"]["cache read"] += rd * r_rd / 1e6
            agg["part"]["cache write 1h"] += w1h * r_w1 / 1e6
            agg["part"]["cache write 5m"] += w5m * r_w5 / 1e6
            agg["part"]["fresh input"] += inp * r_in / 1e6
            seq.append((mid, usd, model))
            big[">300k" if ctx > 300_000 else ">150k" if ctx > 150_000 else "<=150k"] += usd
            raw["tokens"] += ctx + out
            raw["usd"] += usd
        # Opus/Fable calls that only fetch (read, search, run a command), in runs of 3+: the bulk work Haiku 5.5 should do
        run = []
        for mid, usd, model in seq + [(None, 0, "")]:
            if mid and toolsof[mid] and toolsof[mid] <= FETCH and ("opus" in model or "fable" in model):
                run.append(usd)
                continue
            if len(run) >= 3:
                fetch_loop["usd"] += sum(run)
                fetch_loop["runs"] += 1
            run = []

    total = raw["usd"] or 1
    res = {"hours": a.hours, "files": len(files), "calls": calls, "raw_tokens": raw["tokens"], "usd": round(raw["usd"], 2),
           "shaan_requests": shaan_req, "usd_per_shaan_request": round(raw["usd"] / max(shaan_req, 1), 3),
           "tokens_per_shaan_request": int(raw["tokens"] / max(shaan_req, 1)),
           "split": {d: {k: round(v / total, 4) for k, v in sorted(m.items(), key=lambda kv: -kv[1])[:15]} for d, m in agg.items()},
           "context_band": {k: round(v / total, 4) for k, v in big.items()},
           "tool_output_tokens": {k: int(v) for k, v in sorted(tool_tok.items(), key=lambda kv: -kv[1])[:12]},
           "tool_calls": dict(sorted(tool_calls.items(), key=lambda kv: -kv[1])[:12]),
           "tool_carry_share": {k: round(v / total, 4) for k, v in sorted(tool_carry.items(), key=lambda kv: -kv[1])[:12]},
           "reread": {"reads": reread_n, "tokens": int(reread_tok)},
           "opus_fetch_loops": {"runs": fetch_loop["runs"], "share": round(fetch_loop["usd"] / total, 4)}}
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)
    print(f"{a.hours:g}h: {calls} calls in {len(files)} transcripts, {raw['tokens'] / 1e6:.0f}M tokens, ${raw['usd']:.0f} at list price")
    print(f"Shaan requests {shaan_req}: ${res['usd_per_shaan_request']} and {res['tokens_per_shaan_request'] / 1e6:.2f}M tokens each")
    for d in ("turn", "part", "model", "entry", "seat"):
        print(f"  {d:6}", ", ".join(f"{k} {v:.0%}" for k, v in list(res["split"].get(d, {}).items())[:8]))
    print("  context", ", ".join(f"{k} {v:.0%}" for k, v in res["context_band"].items()))
    print("  carrying tool output", ", ".join(f"{k} {v:.0%}" for k, v in list(res["tool_carry_share"].items())[:6]))
    print(f"  files read again {reread_n}x ({reread_tok / 1e3:.0f}k tokens)")
    print(f"  Opus fetch loops (3+ fetch-only calls in a row): {fetch_loop['runs']} runs, {res['opus_fetch_loops']['share']:.0%} of cost (Haiku 5.5's job)")


if __name__ == "__main__":
    main()
