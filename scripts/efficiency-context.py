#!/usr/bin/env python3
"""On-demand, metadata-only context measurement and fresh-chat replay.

No hooks, scheduling, agent contact, transcript text exports, or process changes.
Default scope is the separate SISO login; mixed-login stores are refused.
Replay is a planning estimate, never a live saving or task-quality proof.
"""
import argparse
import datetime as dt
import json
from pathlib import Path

CAP = 300_000
PRIVATE = ("fahmy", "whatsapp", "personal", "bykonz")
HOME = Path.home()


def allowed(path):
    real = path.resolve()
    forbidden = (HOME / ".claude", HOME / ".claude-siso")
    return not any(word in str(real).lower() for word in PRIVATE) and not any(
        real == root or root in real.parents for root in forbidden)


def calls(root, day):
    if not allowed(root):
        raise ValueError("private or mixed-login transcript store refused")
    seen, rows, first_calls = set(), [], {}
    for path in sorted(root.glob("*/*.jsonl")):
        if not allowed(path):
            continue
        with path.open(errors="replace") as stream:
            for line in stream:
                if '"assistant"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                    stamp = dt.datetime.fromisoformat(obj.get("timestamp", "").replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
                if obj.get("type") != "assistant" or stamp.tzinfo is None:
                    continue
                cwd = obj.get("cwd") or "?"
                if any(word in cwd.lower() for word in PRIVATE):
                    continue
                first_calls[path.stem] = min(stamp, first_calls.get(path.stem, stamp))
                if stamp.astimezone().date().isoformat() != day:
                    continue
                msg = obj.get("message") or {}
                mid = msg.get("id")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                usage = msg.get("usage") or {}
                context = sum(usage.get(key, 0) for key in (
                    "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                rows.append({"session": path.stem, "at": stamp.astimezone(dt.timezone.utc).isoformat(), "cwd": cwd,
                             "model": msg.get("model"), "context": context,
                             "output": usage.get("output_tokens", 0)})
    for row in rows:
        row["session_first_call_at"] = first_calls[row["session"]].astimezone(dt.timezone.utc).isoformat()
    return sorted(rows, key=lambda row: row["at"])


def number(rows):
    total = sum(row["context"] + row["output"] for row in rows)
    above = sum(row["context"] + row["output"] for row in rows if row["context"] > CAP)
    return {"total_tokens": total, "above_tokens": above,
            "share_pct": round(100 * above / total, 4) if total else None}


def report(rows, threshold=260_000, boot=60_000):
    if not 0 < boot < threshold < CAP:
        raise ValueError("require 0 < fresh boot < handover threshold < 300000")
    by = {}
    for row in rows:
        by.setdefault(row["cwd"], []).append(row)
    ranked = sorted(by, key=lambda cwd: -number(by[cwd])["above_tokens"])
    owner = ranked[0] if ranked and number(by[ranked[0]])["above_tokens"] else None
    simulated, state, resets = [], {}, 0
    for row in rows:
        projected = dict(row)
        if row["cwd"] == owner:
            old = state.get(row["session"])
            candidate = row["context"] if old is None or row["context"] < old[0] else old[1] + row["context"] - old[0]
            if candidate >= threshold:
                candidate = boot
                resets += 1
            projected["context"] = candidate
            state[row["session"]] = (row["context"], candidate)
        simulated.append(projected)
    observed = number(rows)
    replay = number(simulated)
    return {"observed": observed, "largest_contributor": owner,
            "contributors": [{"cwd": cwd, **number(by[cwd]), "calls": len(by[cwd]),
                              "max_context": max(r["context"] for r in by[cwd]),
                              "latest_context": by[cwd][-1]["context"],
                              "latest_at": by[cwd][-1]["at"],
                              "latest_session": by[cwd][-1]["session"]} for cwd in ranked],
            "handover": {"threshold": threshold, "fresh_boot_budget": boot,
                         "protocol": ".agents/efficiency/CONTEXT-HANDOVER.md",
                         "target_cwd": owner, "action": "owner_checkpoint_then_fresh_chat" if owner else "none",
                         "timing": "next safe task boundary; defer during user conversation or critical work",
                         "resume_old_session": False, "automatic_action": False},
            "replay": {**replay, "fresh_chats": resets, "kind": "optimistic planning estimate",
                       "expected_share_gain_pp": round(observed["share_pct"] - replay["share_pct"], 4) if rows else None,
                       "assumptions": "Retain observed positive context growth and outputs; natural context drops reset the trace. Replace a call reaching threshold with a fresh boot. Boundary timing, summary quality and cold-cache writes are unmeasured; boot includes all checkpoint/cache tokens."}}


def adoption(rows, baseline, boot=60_000):
    """Observe rollover metadata without equating a new session with accepted work."""
    try:
        cutoff = dt.datetime.fromisoformat(baseline["measured_at"])
        owner = baseline["largest_contributor"]
        old_session = next(r["latest_session"] for r in baseline["contributors"] if r["cwd"] == owner)
        if cutoff.tzinfo is None or not owner or not old_session:
            raise ValueError
    except (KeyError, TypeError, ValueError, StopIteration):
        raise ValueError("baseline must contain a timezone-aware measurement and owner session") from None
    recent = [r for r in rows if dt.datetime.fromisoformat(r["at"]) > cutoff]
    owner_recent = [r for r in recent if r["cwd"] == owner]
    result = {"since": cutoff.isoformat(), "target_cwd": owner, "old_session": old_session,
              "all_calls_since": number(recent), "owner_calls_since": number(owner_recent),
              "owner_call_count": len(owner_recent), "status": "no_new_owner_calls",
              "fresh_boot_budget": boot, "useful_work_verified": False,
              "limit": "Session metadata cannot prove checkpoint quality, accepted work or process ownership."}
    if not owner_recent:
        return result
    latest = max(owner_recent, key=lambda r: r["at"])
    session_rows = [r for r in rows if r["session"] == latest["session"]]
    first = min(session_rows, key=lambda r: r["at"])
    session_first = min(r.get("session_first_call_at", r["at"]) for r in session_rows)
    result.update(latest_session=latest["session"], latest_context=latest["context"],
                  session_first_call_at=session_first,
                  first_recorded_at=first["at"], first_recorded_context=first["context"])
    if latest["session"] == old_session or dt.datetime.fromisoformat(session_first) <= cutoff:
        result["status"] = "no_fresh_owner_session"
    elif first["context"] > boot:
        result["status"] = "fresh_boot_over_budget"
    else:
        result["status"] = "fresh_session_observed_acceptance_unverified"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=HOME / ".config/claude-siso-3/projects")
    parser.add_argument("--day", default=dt.datetime.now().astimezone().date().isoformat())
    parser.add_argument("--threshold", type=int, default=260_000)
    parser.add_argument("--boot", type=int, default=60_000)
    parser.add_argument("--baseline", type=Path, help="prior measurement JSON; verify silent owner adoption")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error("transcript root missing; cannot measure")
    try:
        rows = calls(args.root, args.day)
        result = report(rows, args.threshold, args.boot)
        if args.baseline:
            if not allowed(args.baseline):
                raise ValueError("private baseline refused")
            baseline = json.loads(args.baseline.read_text())
            if not isinstance(baseline, dict):
                raise ValueError("baseline must be a measurement object")
            if baseline.get("scope") != str(args.root.resolve()):
                raise ValueError("baseline and current transcript scopes must match")
            result["adoption"] = adoption(rows, baseline, args.boot)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    result.update(day=args.day, measured_at=dt.datetime.now().astimezone().isoformat(),
                  scope=str(args.root.resolve()),
                  scope_limit="SISO separate login only; mixed-login roots/private paths excluded. Not fleet-wide.")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
