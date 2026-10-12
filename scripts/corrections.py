#!/usr/bin/env python3
"""On-demand corrections miner: how often Shaan corrects agents, by class, by harness.

Reads Claude top-level sessions (~/.claude/projects/*/*.jsonl) and Codex rollouts
(~/.codex/sessions/YYYY/MM/DD/*.jsonl) for a trailing window, extracts user-authored
messages only, flags corrections with the same detection audit.py uses (CORR_RE, copied
below with a comment naming the source so totals stay comparable), and tags each
correction with zero or more classes.

Usage:
  corrections.py [--days N] [--json] [--samples DIR]

Streaming: each file is read line by line; files are filtered by mtime before being
opened, then each event is filtered by its own timestamp against the window.
"""
import argparse, collections, glob, json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
CLAUDE_PROJ = os.path.join(HOME, ".claude", "projects")
CODEX_SESS = os.path.join(HOME, ".codex", "sessions")

# ---------- correction detection: copied from scripts/audit.py CORR_RE (same regex,
# same "head = txt[:400]; CORR_RE.search(head) and len(txt) < 1500" gate) so totals are
# comparable with audit.py's count for the same Claude window. ----------
CORR_RE = re.compile(
    r"(^|\W)(no,|no\.|nope|don'?t|do not|stop\b|why did you|why are you|why do you|i said|i told you|i asked|wrong|fuck|wtf|again\b|you didn'?t|you did not|not what i|that'?s not|isn'?t what|i never|didn'?t ask|didnt ask|bro\b|bruh|useless|wasting|waste\b|what the|seriously|ffs|stupid|are you kidding|still not|not working|read the|actually\b|ignore|listen)",
    re.I)

# ---------- classes (multi-label, case-insensitive) ----------
CLASSES = collections.OrderedDict([
    ("show-me-url", re.compile(r"\b(url|link)\b|can'?t see|don'?t see|eyes on|before and after|screenshot|one pager|paragraph|show me", re.I)),
    ("just-do-it", re.compile(r"just (do|build|go|make)|stop asking|don'?t ask|own reasoning|over ?-?engineer|what do we do|next step", re.I)),
    ("didnt-look", re.compile(r"didn'?t (look|read|check|search)|haven'?t (read|looked)|read (more|enough)|look (in|around|at) (my|our|the)|already (built|made|have|exists?)|it'?s (literally )?in (our|my|the)", re.I)),
    ("use-our-components", re.compile(r"shadcn|shatzi|shadzi|21st|\bcomps?\b|ui components|component bank|ui bank", re.I)),
    ("already-told-you", re.compile(r"\bi (already|just) (told|said|asked)|as i said|like i said|i told you|specifically what i (told|said)", re.I)),
    ("wrong-build-no-change", re.compile(r"wrong (url|app|build|page|version)|old (app|ui|version)|what url|no difference|didn'?t change|nothing changed|still (says|shows|looks|the same)", re.I)),
    ("misread-intent", re.compile(r"\bi (didn'?t|did not) mean|\bi meant\b|not what i (wanted|said|asked|meant)|that'?s not what|when i said", re.I)),
])


def ts(s):
    try:
        v = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
        return v if v.tzinfo is not None else None
    except Exception:
        return None


def classify(text):
    hits = [name for name, rx in CLASSES.items() if rx.search(text)]
    return hits or ["other"]


def blocks(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


# ---------- Claude source ----------
def claude_events(w0, w1):
    """Yield (timestamp, date_str, project, text) for user-authored Claude messages."""
    for f in glob.glob(os.path.join(CLAUDE_PROJ, "*", "*.jsonl")):
        if os.path.getmtime(f) < w0.timestamp():
            continue
        proj = os.path.basename(os.path.dirname(f))
        proj = proj.replace("-Users-shaansisodia-", "").replace("-Users-shaansisodia", "home") or "home"
        try:
            fh = open(f, "r", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if len(line) < 20:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") != "user":
                    continue
                tm = ts(o.get("timestamp") or "")
                if tm is None or not w0 <= tm < w1:
                    continue
                m = o.get("message") or {}
                bl = blocks(m)
                # tool results carry a tool_result block: exclude
                if any(b.get("type") == "tool_result" for b in bl):
                    continue
                txt = " ".join(b.get("text", "") for b in bl if b.get("type") == "text").strip()
                if not txt:
                    continue
                if o.get("isMeta") or o.get("isCompactSummary"):
                    continue
                if txt.startswith("This session is being continued"):
                    continue
                if txt.startswith(("<teammate-message", "<task-notification>", "<system-reminder>",
                                    "<command-name>", "<local-command", "<cross-session",
                                    "[from:", "Caveat:")):
                    continue
                if "idle_notification" in txt[:60]:
                    continue
                yield tm, o.get("timestamp", "")[:10], proj, txt


# ---------- Codex source ----------
def codex_events(w0, w1):
    """Yield (timestamp, date_str, project, text) for user-role message payloads."""
    pattern = os.path.join(CODEX_SESS, "*", "*", "*", "*.jsonl")
    for f in glob.glob(pattern):
        if os.path.getmtime(f) < w0.timestamp():
            continue
        cwd = None
        try:
            fh = open(f, "r", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if len(line) < 20:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") == "session_meta" and cwd is None:
                    cwd = (o.get("payload") or {}).get("cwd")
                if o.get("type") != "response_item":
                    continue
                p = o.get("payload") or {}
                if p.get("type") != "message" or p.get("role") != "user":
                    continue
                tm = ts(o.get("timestamp") or "")
                if tm is None or not w0 <= tm < w1:
                    continue
                content = p.get("content")
                parts = content if isinstance(content, list) else []
                txt = " ".join(
                    c.get("text", "") for c in parts
                    if isinstance(c, dict) and c.get("type") in ("input_text", "text")
                ).strip()
                if not txt:
                    continue
                # AGENTS.md / instructions injections
                if txt.startswith("# AGENTS.md instructions for") or "<INSTRUCTIONS>" in txt[:200]:
                    continue
                if txt.startswith("<subagent_notification>"):
                    continue
                if txt.startswith(("<environment_context>", "<user_instructions>")):
                    continue
                proj = os.path.basename((cwd or "?").rstrip("/")) or "?"
                yield tm, o.get("timestamp", "")[:10], proj, txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--samples", metavar="DIR", default=None)
    args = ap.parse_args()

    w1 = datetime.now(timezone.utc)
    w0 = w1 - timedelta(days=args.days)

    if args.samples:
        target = os.path.abspath(args.samples)
        try:
            r = subprocess.run(["git", "check-ignore", "-q", target], cwd=os.path.dirname(__file__),
                                capture_output=True)
            ignored = r.returncode == 0
        except Exception:
            ignored = False
        if not ignored:
            print(f"refused: --samples target {target!r} is not under a git-ignored path", file=sys.stderr)
            sys.exit(2)
        os.makedirs(target, exist_ok=True)

    sources = {"claude": claude_events, "codex": codex_events}

    per_class = collections.Counter()
    per_harness_class = collections.Counter()
    per_day = collections.Counter()
    per_harness = collections.Counter()
    total = 0
    samples = collections.defaultdict(list)  # class -> [(harness, date, project, text[:80])]

    for harness, fn in sources.items():
        for tm, date_str, proj, txt in fn(w0, w1):
            head = txt[:400]
            if not (CORR_RE.search(head) and len(txt) < 1500):
                continue
            total += 1
            per_harness[harness] += 1
            per_day[date_str] += 1
            classes = classify(txt)
            for cls in classes:
                per_class[cls] += 1
                per_harness_class[(harness, cls)] += 1
                if args.samples and len(samples[cls]) < 25:
                    clean = re.sub(r"\s+", " ", txt)[:80]
                    samples[cls].append((harness, date_str, proj, clean))

    if args.samples:
        for cls, rows in samples.items():
            path = os.path.join(os.path.abspath(args.samples), f"{cls}.jsonl")
            with open(path, "w") as out:
                for harness, date_str, proj, clean in rows:
                    out.write(json.dumps({"harness": harness, "date": date_str, "project": proj, "text": clean}) + "\n")

    days_span = max(1, args.days)
    result = {
        "window_days": args.days,
        "window": f"{w0.isoformat()}..{w1.isoformat()}",
        "total": total,
        "per_day_rate": round(total / days_span, 2),
        "per_harness": dict(per_harness),
        "per_class": dict(per_class),
        "per_harness_class": {f"{h}/{c}": n for (h, c), n in per_harness_class.items()},
        "per_day": dict(sorted(per_day.items())),
    }

    if args.json:
        print(json.dumps(result, indent=1))
        return

    print(f"Window: last {args.days}d  ({result['window']})")
    print(f"Total corrections: {total}  ({result['per_day_rate']}/day)")
    print()
    print(f"{'harness':<10} {'count':>6}")
    for h, n in sorted(per_harness.items(), key=lambda kv: -kv[1]):
        print(f"{h:<10} {n:>6}")
    print()
    print(f"{'class':<24} {'count':>6}")
    for cls in list(CLASSES.keys()) + ["other"]:
        print(f"{cls:<24} {per_class.get(cls, 0):>6}")


if __name__ == "__main__":
    main()
