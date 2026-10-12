#!/usr/bin/env python3
"""stack-page.py — rebuild "the agent stack" page from live data.

The page is the project front door for the agent stack (this repo): plain HTML composed from the siso-shell
template bank, family U4 (project one pager), per Shaan's 2026-09-23 brief — "i'd rather just have html's …
templates", so the page is a URL he can click, never a Lavish review session.

Every number on it is collected at run time by the collectors below. Each collector runs under a wall-clock
timeout; one that raises or overruns records "unavailable: <reason>" and the page still composes. Nothing is
fabricated: a check that did not run appears in "What is left", not in "What landed".

    python3 scripts/stack-page.py              # collect, write reports/agent-stack/{page-data.json,index.html}
    python3 scripts/stack-page.py --refresh    # also re-run scripts/corrections.py and cache its JSON
    python3 scripts/stack-page.py --post       # also post the composed page to the local console (:8891)
"""
from __future__ import annotations

import argparse
import collections
import datetime
import json
import pathlib
import re
import shlex
import statistics
import subprocess
import sys
import threading
import urllib.error
import urllib.request

HOME = pathlib.Path.home()
WORKSPACE = HOME / "SISO_Workspace"
REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "reports" / "agent-stack"
SHELL = WORKSPACE / "Great_Library_of_SISO" / "banks" / "siso-shell"
BRAIN = REPO / "brain" / "compose-brain.mjs"

# the stack's own repos: every folder whose origin, head and dirtiness this page reports
STACK_REPOS = [
    "SISO_Agents/siso-harness-lab",
    "SISO_Agents/siso-skills-hub",
    "SISO_Agents/siso-agent-hooks",
    "SISO_Agents/siso-agent-stack",
]

OWNER_SEAT = "agent-stack"
CONSOLE_URL = "http://127.0.0.1:8891/"
CONSOLE_CARD = "http://127.0.0.1:8891/card/agent-stack/html"
SHELL_BASE = "https://siso-shell.pages.dev"
CODEX_LISTING_RE = re.compile(r"\\n- ([a-z0-9_:-]+): ")
NODE_TEST_PASS_RE = re.compile(r"^# pass (\d+)", re.M)
NODE_TEST_FAIL_RE = re.compile(r"^# fail (\d+)", re.M)

NODE_TEST_FILES = [
    "tests/project-memory.test.mjs",
    "tests/closeout-check.test.mjs",
    "tests/ui-bank-nudge.test.mjs",
]
NODE_TEST_CMD = ["node", "--test", *NODE_TEST_FILES]
CORRECTIONS_CMD = "python3 scripts/corrections.py --days 14 --json"

# the checks this page reports, as (key, label, section note)
CHECKS = [
    ("brain", "brain current in every harness", "estate router + composed outputs"),
    ("tests", "node --test", "project memory, closeout check, ui-bank nudge"),
    ("requests", "siso-request tests", "the capability-request CLI"),
    ("routes", "route doctor", "installed skills and jobs still point somewhere live"),
]

WORDS = [
    "you should actually be the owner of a project and have all your memory and something like that there",
    "they know where to request frameworks to the system and then building it and then log it that it's built",
    "all agents that run … should be aware of the system the infrastructure and each other … as few tokens as possible",
]

QUICKSTART_COMMANDS = [
    'herdr-send agent-stack "<msg>"',
    'siso-request add "<what>" --why "<use>"',
    "python3 scripts/stack-page.py --post",
]

BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
TABLE_ROW_RE = re.compile(r"^\|\s*\d+\s*\|")


# ------------------------------------------------------------------------------------------------------------
# result convention: {"status": "ok", ...payload} | {"status": "unavailable", "reason": "<short reason>"}


def ok(**payload):
    return {"status": "ok", **payload}


def short_reason(reason, limit: int = 110) -> str:
    """One line, bounded: the reason a collector is on the page as unavailable."""
    text = reason if isinstance(reason, str) else f"{type(reason).__name__}: {reason}"
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def unavailable(reason):
    return {"status": "unavailable", "reason": short_reason(reason)}


def is_unavailable(res) -> bool:
    return not isinstance(res, dict) or res.get("status") != "ok"


def unavailable_line(label, res) -> str:
    return f"{label}: unavailable: {res.get('reason', '?')}"


def collect(label, fn, timeout, results=None):
    """Run one collector under a wall-clock budget. Never raises: a failure becomes an unavailable record."""
    box: dict = {}

    def work():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — a collector must never take the page down
            box["error"] = exc

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        res = unavailable(f"timed out after {timeout}s")
    elif "error" in box:
        res = unavailable(box["error"])
    else:
        res = box["value"]
    if results is not None:
        results[label] = res
    print(f"{label}: ok" if not is_unavailable(res) else unavailable_line(label, res))
    return res


# ------------------------------------------------------------------------------------------------------------
# process helpers


def cmdstr(args) -> str:
    """The command as run, with the home prefix folded back to ~ so the receipt is readable and exact."""
    return shlex.join(str(a) for a in args).replace(shlex.quote(str(HOME)), "~")


def run(args, cwd=None, timeout=30):
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def stamp(dt) -> str:
    if dt is None:
        return ""
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def iso_local(iso: str) -> str:
    try:
        return stamp(datetime.datetime.fromisoformat(iso))
    except ValueError:
        return iso


def mtime(path: pathlib.Path):
    try:
        return datetime.datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


# ------------------------------------------------------------------------------------------------------------
# pure parsers (unit-tested with fixture strings; no process, network or clock)


def parse_repo_slug(remote_url: str) -> str:
    """'git@github.com:owner/repo.git' and 'https://github.com/owner/repo(.git)' both give 'owner/repo'."""
    url = remote_url.strip()
    m = re.search(r"github\.com[:/]+([^/]+/[^/\s]+?)(?:\.git)?/?$", url)
    return m.group(1) if m else ""


def parse_backlog_open(text: str):
    """Open rows of BACKLOG.md: lines under '## Open' starting '| <number> |', as {n, title}."""
    rows = []
    in_open = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_open = stripped.lower().startswith("## open")
            continue
        if not in_open or not TABLE_ROW_RE.match(stripped):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        body = cells[1] if len(cells) > 1 else ""
        bold = BOLD_RE.search(body)
        rows.append({"n": int(cells[0]), "title": (bold.group(1) if bold else body).strip()})
    return rows


def parse_herdr_agents(text: str, owner_name: str = OWNER_SEAT):
    """herdr agent list JSON -> the owner seat plus counts by harness and by status."""
    agents = json.loads(text)["result"]["agents"]
    owner = next((a for a in agents if a.get("name") == owner_name), None)
    named = [a for a in agents if a.get("name")]
    return {
        "total": len(agents),
        "owner": {
            "name": owner_name,
            "found": owner is not None,
            "harness": (owner or {}).get("agent"),
            "state": (owner or {}).get("agent_status"),
            "cwd": (owner or {}).get("cwd"),
        },
        "by_harness": dict(collections.Counter(a.get("agent") or "unknown" for a in agents).most_common()),
        "by_status": dict(collections.Counter(a.get("agent_status") or "unknown" for a in agents).most_common()),
        "named": sorted(a["name"] for a in named),
    }


def agents_payload(agents_res):
    """The parsed herdr payload, or None when the collector could not answer."""
    if isinstance(agents_res, dict) and "owner" in agents_res:
        return agents_res
    return None


def agent_counts_line(agents_res) -> str:
    """One line: how many agents, split by harness and by status."""
    payload = agents_payload(agents_res)
    if payload is None:
        return unavailable_line("herdr agent list", agents_res)
    harness = " · ".join(f"{k} {v}" for k, v in payload["by_harness"].items())
    status = " · ".join(f"{k} {v}" for k, v in payload["by_status"].items())
    return f"{payload['total']} agents ({harness}); {status}"


def owner_seat(agents_res, observed_at: str):
    """The U4 seat row for the owner seat — 'not running' when herdr has no agent under that name."""
    payload = agents_payload(agents_res)
    if payload is None:
        return {
            "name": OWNER_SEAT,
            "state": "not running",
            "last": {"at": observed_at, "what": unavailable_line("herdr agent list", agents_res)},
        }
    owner = payload["owner"]
    counts = agent_counts_line(payload)
    if not owner["found"]:
        return {
            "name": OWNER_SEAT,
            "state": "not running",
            "last": {"at": observed_at, "what": f"no seat named <code>{OWNER_SEAT}</code> in herdr. {counts}."},
        }
    return {
        "name": OWNER_SEAT,
        "state": f"{owner['state']} · {owner['harness']}",
        "last": {
            "at": observed_at,
            "what": f"herdr cwd <code>{owner['cwd']}</code>. {counts}.",
        },
    }


def parse_node_test_summary(text: str):
    """node --test TAP tail -> {'pass': N, 'fail': N}; missing counters come back None."""
    p = NODE_TEST_PASS_RE.search(text)
    f = NODE_TEST_FAIL_RE.search(text)
    return {
        "pass": int(p.group(1)) if p else None,
        "fail": int(f.group(1)) if f else None,
    }


def count_codex_listed(text: str) -> int:
    """Unique skills Codex lists at turn 1, from `codex debug prompt-input`."""
    return len(set(CODEX_LISTING_RE.findall(text)))


def corrections_stats(payload):
    """total, mean per day, median of the full days (every per_day key but the newest), and the last full day."""
    per_day = {str(k): int(v) for k, v in (payload.get("per_day") or {}).items()}
    ordered = sorted(per_day.items())
    full = dict(ordered[:-1]) if len(ordered) > 1 else {}
    last_day = max(full) if full else None
    return {
        "total": payload.get("total"),
        "per_day_rate": payload.get("per_day_rate"),
        "per_harness": payload.get("per_harness") or {},
        "per_class": payload.get("per_class") or {},
        "days": len(per_day),
        "days_full": len(full),
        "mean_per_day": round(statistics.fmean(per_day.values()), 1) if per_day else None,
        "median_full_days": statistics.median(full.values()) if full else None,
        "last_full_day": {"day": last_day, "count": full[last_day]} if last_day else None,
        "window": payload.get("window"),
    }


# ------------------------------------------------------------------------------------------------------------
# collectors


def collect_repos():
    items, missing = [], []
    for rel in STACK_REPOS:
        path = WORKSPACE / rel
        try:
            remote = run(["git", "-C", path, "config", "--get", "remote.origin.url"], timeout=15).stdout.strip()
            slug = parse_repo_slug(remote)
            branch = run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], timeout=15).stdout.strip()
            head = run(["git", "-C", path, "log", "-1", "--format=%h"], timeout=15).stdout.strip()
            head_iso = run(["git", "-C", path, "log", "-1", "--format=%cI"], timeout=15).stdout.strip()
            status = run(["git", "-C", path, "status", "--porcelain"], timeout=30).stdout
            if not slug or not head:
                raise RuntimeError(f"git gave no origin/head for {rel}")
        except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
            missing.append(f"{rel} ({short_reason(exc, 60)})")
            continue
        dirty = len([ln for ln in status.splitlines() if ln.strip()])
        private = None
        try:
            r = run(["gh", "api", f"repos/{slug}", "--jq", ".private"], timeout=8)
            if r.returncode == 0:
                private = {"true": True, "false": False}.get(r.stdout.strip().lower())
        except (subprocess.SubprocessError, OSError):
            private = None
        entry = {
            "repo": slug,
            "url": f"https://github.com/{slug}",
            "branch": branch,
            "head": head,
            "head_at": iso_local(head_iso),
            "access": f"{dirty} dirty paths",
            "what": f"<code>{rel}</code>",
        }
        if private is None:
            entry["access"] += " · visibility unknown"
        else:
            entry["private"] = private
        items.append(entry)
    if not items:
        return unavailable(f"no repository answered to git: {', '.join(missing) or 'none found'}")
    return ok(items=items, missing=missing)


def collect_agents():
    r = run(["herdr", "agent", "list"], timeout=25)
    if r.returncode != 0:
        return unavailable(f"herdr agent list exited {r.returncode}: {r.stderr.strip()[:80]}")
    return ok(**parse_herdr_agents(r.stdout))


def collect_check_brain():
    r = run(["node", BRAIN, "--check"], timeout=60)
    tail = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return ok(
        pass_=r.returncode == 0,
        exit=r.returncode,
        cmd=cmdstr(["node", BRAIN, "--check"]),
        detail=tail[-1] if tail else "",
    )


def collect_check_tests():
    r = run(NODE_TEST_CMD, cwd=REPO, timeout=300)
    summary = parse_node_test_summary(r.stdout + r.stderr)
    return ok(
        pass_=r.returncode == 0 and summary["fail"] == 0 and summary["pass"] is not None,
        exit=r.returncode,
        cmd=cmdstr(NODE_TEST_CMD),
        detail=f"{summary['pass']} pass · {summary['fail']} fail",
        summary=summary,
    )


def collect_check_request_tests():
    cmd = ["python3", "tests/test_siso_request.py"]
    r = run(cmd, cwd=REPO, timeout=150)
    ran = re.search(r"^Ran (\d+) tests", r.stdout + r.stderr, re.M)
    return ok(
        pass_=r.returncode == 0,
        exit=r.returncode,
        cmd=cmdstr(cmd),
        detail=f"{ran.group(1)} tests, exit {r.returncode}" if ran else f"exit {r.returncode}",
    )


def collect_check_routes():
    cmd = ["python3", "scripts/route_doctor.py", "--json"]
    r = run(cmd, cwd=REPO, timeout=180)
    try:
        payload = json.loads(r.stdout)
    except ValueError as exc:
        return unavailable(f"route doctor gave no JSON ({short_reason(exc, 60)})")
    dead, down = payload.get("dead_count"), payload.get("down_count")
    return ok(
        pass_=dead == 0 and down == 0,
        exit=r.returncode,
        cmd=cmdstr(cmd),
        detail=f"{dead} dead · {down} down · {payload.get('total_count')} routes",
        dead_count=dead,
        down_count=down,
        total_count=payload.get("total_count"),
    )


def collect_skills():
    root = HOME / ".claude" / "skills"
    installed = sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").exists())
    r = run(["codex", "debug", "prompt-input"], cwd=HOME, timeout=90)
    if r.returncode != 0:
        return ok(installed=len(installed), names=installed, codex=None,
                  codex_error=short_reason(f"codex debug prompt-input exited {r.returncode}", 70))
    return ok(
        installed=len(installed),
        names=installed,
        codex=count_codex_listed(r.stdout),
        codex_cmd=cmdstr(["codex", "debug", "prompt-input"]),
    )


def collect_brain_size():
    files = {
        "claude": HOME / ".claude" / "CLAUDE.md",
        "codex": HOME / ".codex" / "AGENTS.md",
        "omp": HOME / ".omp" / "agent" / "AGENTS.md",
    }
    sizes, tokens, missing = {}, {}, []
    for key, path in files.items():
        try:
            sizes[key] = path.stat().st_size
            tokens[key] = round(path.stat().st_size / 4)
        except OSError:
            missing.append(f"{key} ({path})")
    if not sizes:
        return unavailable(f"no brain output readable: {', '.join(missing)}")
    return ok(files=sizes, tokens=tokens, missing=missing)


def collect_requests():
    cmd = ["bin/siso-request", "list", "--all", "--json"]
    r = run([REPO / "bin" / "siso-request", "list", "--all", "--json"], cwd=REPO, timeout=60)
    if r.returncode != 0:
        return unavailable(f"siso-request exited {r.returncode}: {r.stderr.strip()[:80]}")
    try:
        rows = json.loads(r.stdout)
    except ValueError as exc:
        return unavailable(f"siso-request gave no JSON ({short_reason(exc, 60)})")
    by_state = collections.Counter(x.get("state") or "unknown" for x in rows)
    return ok(
        open=[x for x in rows if x.get("state") == "open"],
        built=[x for x in rows if x.get("state") == "built"],
        by_state=dict(by_state),
        total=len(rows),
        cmd=cmdstr(cmd),
    )


def collect_backlog():
    path = REPO / "BACKLOG.md"
    rows = parse_backlog_open(path.read_text(encoding="utf-8"))
    return ok(items=rows, count=len(rows), href="https://github.com/sisodias/siso-harness-lab/blob/main/BACKLOG.md")


def collect_corrections(refresh: bool):
    path = OUT / "corrections-latest.json"
    notes = []
    if refresh:
        cmd = ["python3", "scripts/corrections.py", "--days", "14", "--json"]
        r = run(cmd, cwd=REPO, timeout=180)
        if r.returncode == 0 and r.stdout.strip():
            path.write_text(r.stdout, encoding="utf-8")
            notes.append(f"refreshed with <code>{CORRECTIONS_CMD}</code>")
        else:
            notes.append(f"refresh failed (exit {r.returncode}), kept the cached file")
    if not path.exists():
        return unavailable(f"{path.name} is not written yet; run with --refresh")
    payload = json.loads(path.read_text(encoding="utf-8"))
    stats = corrections_stats(payload)
    stats.update(
        ok(
            source=f"{path.relative_to(REPO)}",
            at=stamp(mtime(path)),
            cmd=CORRECTIONS_CMD,
            notes=notes,
        )
    )
    return stats


def collect_timeline():
    fmt = "%h%x09%cI%x09%s"
    r = run(["git", "-C", REPO, "log", "-15", "--format=" + fmt], timeout=25)
    remote = run(["git", "-C", REPO, "config", "--get", "remote.origin.url"], timeout=10).stdout.strip()
    slug = parse_repo_slug(remote)
    events = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        sha, iso, subject = parts
        event = {"at": iso_local(iso), "lane": "commits", "label": f"{sha} · {subject}", "iso": iso}
        if slug:
            event["href"] = f"https://github.com/{slug}/commit/{sha}"
        events.append(event)
    if not events:
        return unavailable("git log gave nothing")
    return ok(events=events, slug=slug)


def collect_console():
    try:
        with urllib.request.urlopen(CONSOLE_URL, timeout=5) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return unavailable(f"console did not answer: {short_reason(exc, 80)}")
    return ok(url=CONSOLE_URL, code=code)


def collect_docs():
    estate = REPO / "brain" / "estate.md"
    branch = "main"
    try:
        branch = run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                     timeout=15).stdout.strip() or "main"
    except (subprocess.SubprocessError, OSError):
        pass
    specs = [
        ("AGENTS.md", "Repo rules every agent loads on entry: owner contract, invariants, close-out",
         "https://github.com/sisodias/siso-harness-lab/blob/main/AGENTS.md"),
        ("STATE.md", "Dated session state, newest entry first",
         "https://github.com/sisodias/siso-harness-lab/blob/main/STATE.md"),
        ("docs/HISTORY-RETENTION.md", "Which harness history exists, who reads it, what is deleted",
         "https://github.com/sisodias/siso-harness-lab/blob/main/docs/HISTORY-RETENTION.md"),
        ("~/SISO_Workspace/SISO_Agents/siso-harness-lab/brain/estate.md",
         "The estate router: where every bank, skill and prior run lives",
         f"https://github.com/sisodias/siso-harness-lab/blob/{branch}/brain/estate.md"),
    ]
    items, missing = [], []
    for label, what, href in specs:
        path = estate if label.startswith("~/") else REPO / label
        when = mtime(path)
        if when is None:
            missing.append(label)
            continue
        items.append({"path": label, "href": href, "what": what, "at": stamp(when)})
    if not items:
        return unavailable(f"none of the docs are on disk: {', '.join(missing)}")
    return ok(items=items, missing=missing)


# ------------------------------------------------------------------------------------------------------------
# the page


def repo_metric(repos_res):
    if is_unavailable(repos_res):
        return unavailable_line("repos", repos_res)
    private = sum(1 for r in repos_res["items"] if r.get("private"))
    public = sum(1 for r in repos_res["items"] if r.get("private") is False)
    unknown = len(repos_res["items"]) - private - public
    text = f"{len(repos_res['items'])} repos · {private} private · {public} public"
    if unknown:
        text += f" · {unknown} visibility unknown"
    if repos_res.get("missing"):
        text += f" · {len(repos_res['missing'])} unreadable"
    return text


def checks_rows(res):
    """The four checks as list rows; a check that failed or never ran is honest about which."""
    rows = []
    for key, label, note in CHECKS:
        res_key = {"brain": "check:brain", "tests": "check:tests",
                   "requests": "check:requests", "routes": "check:routes"}[key]
        got = res[res_key]
        if is_unavailable(got):
            rows.append({"key": key, "label": label, "note": note, "cmd": "", "detail": unavailable_line(res_key, got),
                         "pass": None, "exit": None})
        else:
            rows.append({"key": key, "label": label, "note": note, "cmd": got.get("cmd", ""),
                         "detail": got.get("detail", ""), "pass": bool(got.get("pass_")), "exit": got.get("exit")})
    return rows


def build_page(res, now):
    agents_res = res["agents"]
    repos_res = res["repos"]
    skills_res = res["skills"]
    brain_res = res["brain"]
    requests_res = res["requests"]
    backlog_res = res["backlog"]
    corrections_res = res["corrections"]
    timeline_res = res["timeline"]
    console_res = res["console"]
    docs_res = res["docs"]

    rows = checks_rows(res)
    passing = sum(1 for r in rows if r["pass"])
    limits = [unavailable_line(label, r) for label, r in res.items() if is_unavailable(r)]

    # --- metrics (the four the brief names)
    metrics = [
        {"value": f"{passing}/{len(rows)}", "label": "checks passing", "tone": "now" if passing == len(rows) else "warn",
         "href": "#landed", "note": now},
        {"value": skills_res.get("installed", "unavailable") if not is_unavailable(skills_res) else "unavailable",
         "unit": (f"/ {skills_res['codex']} listed by Codex" if not is_unavailable(skills_res) and skills_res.get("codex") is not None
                  else "/ Codex listing unavailable"),
         "label": "skills · Claude installed / Codex-visible", "tone": "projects"},
        {"value": len(requests_res.get("open", [])) if not is_unavailable(requests_res) else "unavailable",
         "label": "open capability requests", "tone": "warn", "href": "#left"},
    ]
    if is_unavailable(corrections_res):
        metrics.append({"value": "unavailable", "label": "corrections per day, median of full days",
                        "tone": "blocked", "note": corrections_res["reason"]})
    else:
        last = corrections_res.get("last_full_day") or {}
        metrics.append({
            "value": corrections_res.get("median_full_days"), "unit": "per day",
            "label": f"corrections · median of {corrections_res.get('days_full')} full days", "tone": "research",
            "note": f"last full day {last.get('day')} · {last.get('count')}",
            "href": None,
        })

    badges = [
        {"label": f"owner {OWNER_SEAT} · {owner_seat(agents_res, now)['state']}", "tone": "agents", "dot": True},
        {"label": f"{passing}/{len(rows)} checks pass", "tone": "now" if passing == len(rows) else "warn",
         "href": "#landed"},
        {"label": repo_metric(repos_res), "tone": "muted", "href": "#repos"},
        {"label": f"{len(backlog_res.get('items', [])) if not is_unavailable(backlog_res) else '?'} backlog rows · "
                  f"{len(requests_res.get('open', [])) if not is_unavailable(requests_res) else '?'} requests open",
         "tone": "warn", "href": "#left"},
    ]

    status_facts = []
    if not is_unavailable(timeline_res) and timeline_res["events"]:
        head = timeline_res["events"][0]
        status_facts.append({"k": "head", "v": f"<code>{head['label'].split(' · ')[0]}</code> · {head['at']}"})
    if not is_unavailable(brain_res):
        sizes = brain_res["files"]
        status_facts.append({"k": "brain",
                             "v": " · ".join(f"{k} {v / 1024:.1f} KB" for k, v in sizes.items())
                                  + f" · ~{sum(brain_res['tokens'].values())} tokens at 4 B/token"})
    if not is_unavailable(skills_res):
        codex = skills_res.get("codex")
        status_facts.append({"k": "skills",
                             "v": f"<code>{skills_res['installed']}</code> installed · "
                                  + (f"<code>{codex}</code> listed by Codex" if codex is not None
                                     else f"Codex listing unavailable: {skills_res.get('codex_error', 'unknown')}")})
    if not is_unavailable(agents_res):
        status_facts.append({"k": "seats", "v": agent_counts_line(agents_res)})
    if not is_unavailable(console_res):
        status_facts.append({"k": "console", "v": f"HTTP <code>{console_res['code']}</code> · {CONSOLE_URL}"})

    # --- sections
    checks_sub = "; ".join(f"{r['label']} {'pass' if r['pass'] else 'FAIL' if r['pass'] is False else 'unavailable'}"
                           for r in rows)
    sections = {
        "what": {"n": "01", "title": "What it is, in his words", "sub": "verbatim, 23 Sep"},
        "map": {"n": "02", "title": "Mind map",
                "sub": "repos · seats · checks · requests · docs this stack touches"},
        "repos": {"n": "03", "title": "Repos, incl. private",
                  "sub": ("branch, head and dirty count from <code>git</code>; visibility from <code>gh api</code>, "
                          + now) if not is_unavailable(repos_res)
                  else unavailable_line("repos", repos_res)},
        "live": {"n": "04", "title": "Live URLs, with codes", "sub": f"checked {now}" if not is_unavailable(console_res)
                 else unavailable_line("console", console_res)},
        "seats": {"n": "05", "title": "Owner seats and latest writeback",
                  "sub": f"herdr agent list, {now}" if not is_unavailable(agents_res)
                  else unavailable_line("herdr agent list", agents_res)},
        "landed": {"n": "06", "title": "What landed",
                   "sub": "each check with the exact command that ran it — " + checks_sub},
        "left": {"n": "07", "title": "What is left", "sub": "open BACKLOG.md rows and open capability requests"},
        "research": {"n": "08", "title": "Research it rests on", "sub": "and what each means for this project"},
        "docs": {"n": "09", "title": "Docs, dated", "sub": f"mtimes on disk, {now}" if not is_unavailable(docs_res)
                 else unavailable_line("docs", docs_res)},
        "timeline": {"n": "10", "title": "Timeline", "sub": "the last 15 commits in this repo"
                     if not is_unavailable(timeline_res) else unavailable_line("timeline", timeline_res)},
        "links": {"n": "11", "title": "Links out",
                  "sub": "the console, the bank this page is composed from, and the records behind it"},
        "agent": {"n": "12", "title": "Agent entry"},
    }

    # --- map (only what was collected)
    types = []
    if not is_unavailable(repos_res):
        types.append({"type": "repo", "label": "Repos", "tone": "projects", "items": [
            {"label": r["repo"].split("/")[-1], "href": r["url"],
             "rel": f"{r['branch']} {r['head']} · " + ("private" if r.get("private") else
                                                       "public" if r.get("private") is False else "visibility unknown"),
             "private": bool(r.get("private"))}
            for r in repos_res["items"]]})
    if not is_unavailable(agents_res):
        seat_items = [{"label": name, "rel": "named seat"} for name in agents_res["named"]]
        if not seat_items:
            seat_items = [{"label": f"{k} × {v}", "rel": "harness"} for k, v in agents_res["by_harness"].items()]
        types.append({"type": "seat", "label": "Seats · herdr", "tone": "agents", "items": seat_items})
    types.append({"type": "check", "label": "Checks", "tone": "research", "items": [
        {"label": r["label"], "href": "#landed", "rel": "pass" if r["pass"] else
         ("FAIL" if r["pass"] is False else "unavailable")} for r in rows]})
    if not is_unavailable(requests_res) and requests_res["open"]:
        types.append({"type": "request", "label": "Capability requests", "tone": "clients", "items": [
            {"label": q["id"], "href": "https://github.com/sisodias/siso-harness-lab/blob/main/requests/requests.jsonl",
             "rel": q["what"][:70]} for q in requests_res["open"]]})
    if not is_unavailable(docs_res) and docs_res["items"]:
        types.append({"type": "doc", "label": "Docs", "tone": "muted", "items": [
            {"label": d["path"].split("/")[-1], "href": d["href"], "rel": d["at"]} for d in docs_res["items"]]})
    types.append({"type": "node", "label": "Nodes", "tone": "now", "items": [
        {"label": "console", "href": CONSOLE_URL, "rel": "the page's own surface"},
        {"label": "siso-shell", "href": SHELL_BASE, "rel": "the template bank (U4)"},
        {"label": "siso-harness-lab", "href": "https://github.com/sisodias/siso-harness-lab", "rel": "this repo"},
    ]})

    # --- landed: the checks that passed, as facts with receipts
    facts = []
    for r in rows:
        if not r["pass"]:
            continue
        line = f"<b>{r['label']}</b> — {r['detail']}."
        if r["key"] == "brain":
            line = ("<b>Brain current in every harness</b> — the estate router resolves for Claude and Codex and all "
                    "three composed outputs are up to date.")
        elif r["key"] == "tests":
            line = f"<b>{r['detail']} in <code>node --test</code></b> — project memory, closeout check, ui-bank nudge."
        elif r["key"] == "requests":
            line = f"<b>siso-request CLI: {r['detail']}</b> — file, list and mark-built all pass."
        elif r["key"] == "routes":
            line = (f"<b>Route doctor: {r['detail']}</b> — every skill command, endpoint and LaunchAgent recorded "
                    "by a skill or job still resolves.")
        facts.append({"claim": line, "receipt": r["cmd"], "at": now})
    if not is_unavailable(agents_res) and agents_res["owner"]["found"]:
        o = agents_res["owner"]
        facts.append({"claim": f"<b>Owner seat running</b> — <code>{OWNER_SEAT}</code> is {o['state']} in herdr, "
                               f"cwd <code>{o['cwd']}</code>.",
                      "receipt": "herdr agent list", "at": now})
    if not is_unavailable(repos_res):
        facts.append({"claim": f"<b>Repos read</b> — " + repo_metric(repos_res) + ", each with its branch, "
                               "head commit and dirty-path count.", "receipt": "git -C <repo> log/status · gh api repos/<slug>",
                      "at": now})
    if not is_unavailable(skills_res):
        codex = skills_res.get("codex")
        facts.append({"claim": f"<b>{skills_res['installed']} skills installed</b> in <code>~/.claude/skills</code>"
                               + (f", <code>{codex}</code> of them listed by Codex at turn 1." if codex is not None
                                  else "; the Codex listing was not observed."),
                      "receipt": skills_res.get("codex_cmd", "ls ~/.claude/skills") + " · ls ~/.claude/skills",
                      "at": now})
    if not is_unavailable(corrections_res):
        last = corrections_res.get("last_full_day") or {}
        facts.append({"claim": f"<b>Corrections measured</b> — {corrections_res['total']} in "
                               f"{corrections_res['days']} days ({corrections_res['per_day_rate']}/day); median of the "
                               f"{corrections_res['days_full']} full days {corrections_res['median_full_days']}; "
                               f"last full day {last.get('day')} at {last.get('count')}.",
                      "receipt": corrections_res["cmd"], "href": None, "at": corrections_res.get("at", now)})

    # --- left: open backlog rows + open requests (+ the failures, stated as what is left)
    left_items = [{"label": f"#{r['n']}", "what": r["title"], "state": "open", "tone": "warn",
                   "href": backlog_res.get("href")} for r in (backlog_res.get("items") or [])
                  ] if not is_unavailable(backlog_res) else []
    if not is_unavailable(requests_res):
        left_items += [{"label": q["id"], "what": q["what"], "state": "open request", "tone": "clients",
                        "href": "https://github.com/sisodias/siso-harness-lab/blob/main/requests/requests.jsonl"}
                       for q in requests_res["open"]]
    for r in rows:
        if r["pass"]:
            continue
        left_items.append({"label": f"check · {r['label']}", "what": r["detail"], "state":
                           "failed" if r["pass"] is False else "unavailable",
                           "tone": "blocked" if r["pass"] is False else "warn", "href": "#landed"})
    for line in limits:
        left_items.append({"label": "collector", "what": line, "state": "unavailable", "tone": "blocked"})

    left = {"items": left_items, "steps": [
        {"label": "Fix a route", "what": "Open a backlog row's instrument, close the route it names, then re-run "
                                         "<code>python3 scripts/stack-page.py</code> and watch the checks row flip."},
        {"label": "Rebuild this page", "what": "<code>python3 scripts/stack-page.py --refresh</code> re-collects "
                                               "everything, including the corrections window."},
        {"label": "Post it to the console", "what": "<code>python3 scripts/stack-page.py --post</code> lands the "
                                                    f"composed HTML at <a href=\"{CONSOLE_CARD}\">{CONSOLE_CARD}</a>."},
    ]}

    # --- docs
    docs = docs_res.get("items", []) if not is_unavailable(docs_res) else []

    # --- timeline
    events = timeline_res.get("events", []) if not is_unavailable(timeline_res) else []
    timeline = {
        "from": events[-1]["iso"] if events else "",
        "to": events[0]["iso"] if events else "",
        "lanes": [{"id": "commits", "label": "commits", "tone": "projects"}],
        "events": [{"at": e["at"], "lane": e["lane"], "label": e["label"], "href": e.get("href")} for e in events],
    }

    links = [
        {"title": "SISO console", "href": CONSOLE_URL, "type": "local surface", "tone": "now",
         "why": "where this page is posted; --post lands the card"},
        {"title": "sisodias/siso-harness-lab", "href": "https://github.com/sisodias/siso-harness-lab",
         "type": "repo", "tone": "projects", "why": "the agent stack repo this page describes"},
        {"title": "BACKLOG.md", "href": "https://github.com/sisodias/siso-harness-lab/blob/main/BACKLOG.md",
         "type": "record", "tone": "agents", "why": "ranked by leverage per hour; #left lists its open rows"},
        {"title": "requests.jsonl", "href": "https://github.com/sisodias/siso-harness-lab/blob/main/requests/requests.jsonl",
         "type": "record", "tone": "agents", "why": "capability requests agents filed instead of building one-offs"},
        {"title": "siso-shell · U4 template", "href": f"{SHELL_BASE}/t/U4/", "type": "Cloudflare page",
         "tone": "projects", "why": "the project one-pager family this page is composed from"},
        {"title": "siso-shell · the bank", "href": f"{SHELL_BASE}/", "type": "Cloudflare page", "tone": "projects",
         "why": "shell, parts and templates"},
        {"title": "agent-context review, 23 Sep", "href": "https://github.com/sisodias/siso-harness-lab/blob/main/reports/2026-09-23-agent-context/index.html",
         "type": "report", "tone": "research", "why": "the phase-2 measurements this page's checks came out of"},
    ]

    return {
        "meta": {
            "title": "Agent stack · project",
            "description": "Project one pager for the agent stack: repos with heads, the owner seat, the checks with "
                           "their receipts, what is left, docs and the timeline.",
            "stream": "agents",
            "crumb": [{"label": "SISO Agents"}, {"label": "siso-harness-lab"}, {"label": "Agent stack"}],
            "actions": [
                {"label": "Repo", "href": "https://github.com/sisodias/siso-harness-lab", "icon": "git-branch",
                 "external": True},
                {"label": "Console", "href": CONSOLE_URL, "icon": "activity", "external": True},
            ],
            "source": ("git · gh api · herdr agent list · codex debug prompt-input · node --test · "
                       "scripts/route_doctor.py · bin/siso-request · " + now),
        },
        "heading": {
            "breadcrumb": [{"label": "Projects"}, {"label": "agency"}, {"label": "agent-stack"}],
            "kicker": 'project <span class="sep">·</span> agency <span class="sep">·</span> '
                      '<span class="dim">siso-harness-lab</span>',
            "title": "Agent stack",
            "subtitle": "How every agent on Shaan's machines works: brain and estate router, hooks, skills, project "
                        "memory, DeepSeek workers, capability requests. Owner: herdr agent agent-stack.",
            "badges": badges,
            "status": {
                "kicker": "Collected",
                "value": now,
                "note": ("Every number on this page was read on this machine at this time. A collector that could not "
                         "answer says so in <a href=\"#left\">What is left</a>."),
                "facts": status_facts,
            },
            "metrics": metrics,
        },
        "sections": sections,
        "words": [{"text": w, "who": "Shaan", "at": "23 Sep"} for w in WORDS],
        "map": {"centre": {"label": "agent stack", "href": "#top"}, "types": types},
        "repos": repos_res.get("items", []) if not is_unavailable(repos_res) else [],
        "urls": (
            [{"url": CONSOLE_URL, "what": "the local SISO console", "code": console_res["code"], "tone": "now",
              "checked": now}]
            if not is_unavailable(console_res) else
            [{"url": CONSOLE_URL, "what": "the local SISO console", "code": "unavailable", "tone": "blocked",
              "checked": now}]
        ),
        "seats": [owner_seat(agents_res, now)],
        "landed": {"facts": facts, "proposals": [], "limits": limits or [
            "Every collector answered on this run; the fail-closed path was not exercised.",
        ], "version": {"label": f"stack-page.py @ {stamp(datetime.datetime.now())}", "at": now}},
        "left": left,
        "research": [],
        "docs": docs,
        "timeline": timeline,
        "links": links,
        "quickstart": {
            "entry": {"path": "reports/agent-stack/"},
            "commands": QUICKSTART_COMMANDS,
            "owner": {"name": OWNER_SEAT, "href": "https://github.com/sisodias/siso-harness-lab",
                      "last": now},
            "verification": "Run <code>python3 scripts/stack-page.py</code> and see the same checks row pass; open "
                            f"<a href=\"{CONSOLE_CARD}\">{CONSOLE_CARD}</a> and read this page from the console.",
            "context_url": CONSOLE_URL,
        },
        "nav": {
            "title": "Agent stack",
            "mark": "AS",
            "home": "#top",
            "groups": [
                {"id": "stack", "label": "The stack", "destinations": [
                    {"id": "what", "label": "What it is", "href": "#what", "icon": "layout-dashboard"},
                    {"id": "map", "label": "Mind map", "href": "#map", "icon": "map"},
                    {"id": "repos", "label": "Repos", "href": "#repos", "icon": "git-branch"},
                    {"id": "live", "label": "Live URLs", "href": "#live", "icon": "activity"},
                    {"id": "seats", "label": "Owner seats", "href": "#seats", "icon": "users"},
                ]},
                {"id": "state", "label": "State", "destinations": [
                    {"id": "landed", "label": "What landed", "href": "#landed", "icon": "shield-check"},
                    {"id": "left", "label": "What is left", "href": "#left", "icon": "boxes"},
                    {"id": "docs", "label": "Docs", "href": "#docs", "icon": "file-text"},
                    {"id": "timeline", "label": "Timeline", "href": "#timeline", "icon": "clock"},
                    {"id": "links", "label": "Links out", "href": "#links", "icon": "search"},
                    {"id": "agent", "label": "Agent entry", "href": "#agent", "icon": "bot"},
                ]},
            ],
        },
    }


# ------------------------------------------------------------------------------------------------------------
# run


def gather(refresh: bool):
    res = {}
    res["repos"] = collect("repos", collect_repos, 150, res)
    res["agents"] = collect("agents", collect_agents, 40, res)
    res["check:brain"] = collect("check:brain", collect_check_brain, 90, res)
    res["check:tests"] = collect("check:tests", collect_check_tests, 300, res)
    res["check:requests"] = collect("check:requests", collect_check_request_tests, 150, res)
    res["check:routes"] = collect("check:routes", collect_check_routes, 200, res)
    res["skills"] = collect("skills", collect_skills, 150, res)
    res["brain"] = collect("brain", collect_brain_size, 20, res)
    res["requests"] = collect("requests", collect_requests, 60, res)
    res["backlog"] = collect("backlog", collect_backlog, 20, res)
    res["corrections"] = collect("corrections", lambda: collect_corrections(refresh), 240, res)
    res["timeline"] = collect("timeline", collect_timeline, 40, res)
    res["console"] = collect("console", collect_console, 20, res)
    res["docs"] = collect("docs", collect_docs, 30, res)
    return res


def compose_page(data_path, html_path):
    cmd = [SHELL / "bin" / "compose", "U4", data_path, "--base", SHELL_BASE, "--out", html_path]
    r = subprocess.run([str(c) for c in cmd], cwd=str(REPO), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"compose failed (exit {r.returncode}): {r.stderr.strip()[:400]}", file=sys.stderr)
        return False
    print(r.stderr.strip())
    return True


def post(html_path):
    exe = subprocess.run(["sh", "-c", "command -v console-post"], capture_output=True, text=True).stdout.strip()
    exe = exe or str(HOME / ".claude" / "console" / "bin" / "console-post")
    with open(html_path, "rb") as fh:
        r = subprocess.run(
            [exe, "-k", "html", "-i", "agent-stack", "-t", "Agent stack", "-"],
            stdin=fh, cwd=str(REPO), capture_output=True, text=True, timeout=60,
        )
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        print(f"console-post failed (exit {r.returncode}): {(r.stderr or '').strip()[:300]}", file=sys.stderr)
        return False
    print(out or "posted")
    print(CONSOLE_CARD)
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild the agent stack page from live data.")
    parser.add_argument("--refresh", action="store_true", help="re-run scripts/corrections.py first")
    parser.add_argument("--post", action="store_true", help="post the composed page to the console")
    args = parser.parse_args(argv)

    OUT.mkdir(parents=True, exist_ok=True)
    now = stamp(datetime.datetime.now())
    res = gather(args.refresh)
    data = build_page(res, now)
    data_path = OUT / "page-data.json"
    html_path = OUT / "index.html"
    data_path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {data_path.relative_to(REPO)} ({data_path.stat().st_size} bytes)")
    if not compose_page(str(data_path), str(html_path)):
        return 1
    if args.post and not post(html_path):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
