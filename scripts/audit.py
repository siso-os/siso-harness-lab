#!/usr/bin/env python3
"""On-demand streaming audit of Claude Code events in the requested time window."""
import json, os, glob, re, sys, time, collections, statistics, difflib
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
PROJ = os.path.join(HOME, ".claude", "projects")
# Window: `audit.py OUT.json [DAYS]` (default 14, ending now). Run on demand only; never scheduled.
_DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 14
W1 = datetime.now(timezone.utc)
from datetime import timedelta as _td
W0 = W1 - _td(days=_DAYS)
OUT = json.load if False else None

def ts(s):
    try:
        value = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return value if value.tzinfo is not None else None
    except Exception:
        return None

def proj_name(path):
    d = os.path.basename(os.path.dirname(path))
    return d.replace("-Users-shaansisodia-", "").replace("-Users-shaansisodia", "home") or "home"

def blocks(msg):
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []

SEARCH_RE = re.compile(r'(?:^|[|;&(]\s*|\bsudo\s+|\bxargs\s+)(rg|grep|egrep|fgrep|find|ag|ack)\b')
CORR_RE = re.compile(
    r"(^|\W)(no,|no\.|nope|don'?t|do not|stop\b|why did you|why are you|why do you|i said|i told you|i asked|wrong|fuck|wtf|again\b|you didn'?t|you did not|not what i|that'?s not|isn'?t what|i never|didn'?t ask|didnt ask|bro\b|bruh|useless|wasting|waste\b|what the|seriously|ffs|stupid|are you kidding|still not|not working|read the|actually\b|ignore|listen)",
    re.I)
NEG_HITS = re.compile(r"blocked|no payload|partial|could not|couldn't|unable to|did not complete|timed out|terminated early|failed", re.I)

# ---------- collect top-level session files ----------
files = []
for f in glob.glob(os.path.join(PROJ, "*", "*.jsonl")):
    if os.path.getmtime(f) < W0.timestamp():
        continue
    files.append(f)

sessions = {}          # sid -> dict
agent_calls = []       # dicts
agent_results = {}     # tool_use_id -> (len, text)
agent_notifs = {}      # tool_use_id -> (status, summary)
skill_uses = collections.Counter()
skill_by_session = collections.Counter()
model_usage = collections.defaultdict(lambda: collections.Counter())
tool_counter = collections.Counter()
corrections = []       # (date, project, quote, sid)
corr_per_session = collections.Counter()
compactions = []       # (sid, trigger, pre, post, ts)
search_cmds = []       # (sid, cmd[:120])
api_errors = collections.Counter()
hook_summaries = collections.Counter()
sub_dirs = []

for f in files:
    sid = os.path.basename(f)[:-6]
    S = dict(sid=sid, project=proj_name(f), lines=0, bytes=os.path.getsize(f),
             turns=set(), tool_use=0, tools=collections.Counter(), agent=0,
             user_prompts=0, compact=0, resume=0, bash_search=0, read_glob_grep=0,
             first=None, last=None, events=[], turn_tools=collections.Counter(),
             models=collections.Counter())
    in_window = False
    with open(f, "r", errors="replace") as fh:
        for line in fh:
            S["lines"] += 1
            if len(line) < 20:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            tm = ts(o.get("timestamp") or "")
            if tm is None or not W0 <= tm < W1:
                continue
            in_window = True
            S["first"] = S["first"] or tm
            S["last"] = tm
            if t == "system":
                st = o.get("subtype")
                if st == "compact_boundary":
                    md = o.get("compactMetadata") or {}
                    compactions.append((sid, md.get("trigger"), md.get("preTokens"), md.get("postTokens"), o.get("timestamp")))
                    S["compact"] += 1
                elif st == "stop_hook_summary":
                    hook_summaries["stop_hook_summary"] += 1
                    if o.get("preventedContinuation"):
                        hook_summaries["preventedContinuation"] += 1
                elif st == "local_command":
                    c = str(o.get("content", ""))
                    if "Error during compaction" in c:
                        api_errors["compaction_error"] += 1
                continue
            if t == "assistant":
                m = o.get("message") or {}
                if o.get("isApiErrorMessage"):
                    api_errors["api_error_msg"] += 1
                mid = m.get("id") or o.get("uuid")
                model = m.get("model") or "?"
                S["models"][model] += 1
                if mid not in S["turns"]:
                    S["turns"].add(mid)
                    u = m.get("usage") or {}
                    mu = model_usage[model]
                    mu["turns"] += 1
                    for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
                        mu[k] += u.get(k) or 0
                for b in blocks(m):
                    bt = b.get("type")
                    if bt == "tool_use":
                        name = b.get("name")
                        inp = b.get("input") or {}
                        S["tool_use"] += 1
                        S["tools"][name] += 1
                        S["turn_tools"][mid] += 1
                        tool_counter[name] += 1
                        S["events"].append((tm, "tool", name))
                        if name in ("Agent", "Task"):
                            S["agent"] += 1
                            p = inp.get("prompt") or ""
                            agent_calls.append(dict(sid=sid, project=S["project"], id=b.get("id"),
                                                    subagent_type=inp.get("subagent_type"), model=inp.get("model"),
                                                    plen=len(p), prompt=p, desc=inp.get("description"),
                                                    ts=o.get("timestamp"), caller_model=model))
                        elif name == "Skill":
                            sk = inp.get("skill")
                            skill_uses[sk] += 1
                            skill_by_session[(sid, sk)] += 1
                        elif name == "Bash":
                            cmd = inp.get("command") or ""
                            if SEARCH_RE.search(cmd):
                                S["bash_search"] += 1
                                search_cmds.append((sid, S["project"], cmd[:160].replace("\n", " ")))
                        elif name in ("Read", "Glob", "Grep"):
                            S["read_glob_grep"] += 1
                    elif bt == "text" and (b.get("text") or "").strip():
                        S["events"].append((tm, "text", len(b["text"])))
                continue
            if t == "user":
                m = o.get("message") or {}
                bl = blocks(m)
                is_result = any(b.get("type") == "tool_result" for b in bl)
                if is_result:
                    for b in bl:
                        if b.get("type") != "tool_result":
                            continue
                        tid = b.get("tool_use_id")
                        c = b.get("content")
                        txt = c if isinstance(c, str) else " ".join(x.get("text", "") for x in (c or []) if isinstance(x, dict))
                        agent_results[tid] = (len(txt), txt[:300])
                    continue
                txt = " ".join(b.get("text", "") for b in bl if b.get("type") == "text").strip()
                if not txt:
                    continue
                if txt.startswith("<task-notification>"):
                    tid = re.search(r"<tool-use-id>(.*?)</tool-use-id>", txt)
                    st = re.search(r"<status>(.*?)</status>", txt)
                    sm = re.search(r"<summary>(.*?)</summary>", txt, re.S)
                    if tid:
                        agent_notifs[tid.group(1)] = (st.group(1) if st else "?", (sm.group(1) if sm else "")[:300])
                    continue
                if o.get("isCompactSummary") or txt.startswith("This session is being continued"):
                    S["resume"] += 1
                    continue
                if o.get("isMeta") or txt.startswith("<command-name>") or txt.startswith("<local-command") or txt.startswith("[from:") or txt.startswith("<teammate-message") or txt.startswith("<cross-session") or "[Cross-session" in txt[:30]:
                    continue
                S["user_prompts"] += 1
                S["events"].append((tm, "user", txt[:200]))
                head = txt[:400]
                if CORR_RE.search(head) and len(txt) < 1500:
                    corrections.append((o.get("timestamp", "")[:10], S["project"], re.sub(r"\s+", " ", txt)[:200], sid))
                    corr_per_session[sid] += 1
    if in_window:
        sessions[sid] = S
        sd = os.path.join(os.path.dirname(f), sid, "subagents")
        if os.path.isdir(sd):
            sub_dirs.append((sid, sd))

# ---------- subagent transcripts: final payload length ----------
sub_payloads = []   # (sid, agentId, final_text_len, final_text[:200], lines)
for sid, sd in sub_dirs:
    for sf in glob.glob(os.path.join(sd, "*.jsonl")):
        last_text = ""
        n = 0
        sub_in_window = False
        with open(sf, errors="replace") as fh:
            for line in fh:
                n += 1
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                tm = ts(o.get("timestamp") or "")
                if tm is None or not W0 <= tm < W1:
                    continue
                sub_in_window = True
                if o.get("type") != "assistant":
                    continue
                for b in blocks(o.get("message")):
                    if b.get("type") == "text" and b.get("text", "").strip():
                        last_text = b["text"]
        if sub_in_window:
            sub_payloads.append((sid, os.path.basename(sf)[:-6], len(last_text), re.sub(r"\s+", " ", last_text)[:200], n))

# ---------- derived metrics ----------
def pct(a, b):
    return f"{(100.0*a/b):.1f}%" if b else "n/a"

n_sessions = len(sessions)
turns = sum(len(S["turns"]) for S in sessions.values())
tool_uses = sum(S["tool_use"] for S in sessions.values())
turn_tool_dist = collections.Counter()
for S in sessions.values():
    for mid in S["turns"]:
        k = S["turn_tools"].get(mid, 0)
        turn_tool_dist["0" if k == 0 else "1" if k == 1 else "2-3" if k <= 3 else "4+"] += 1
turns_with_tools = turns - turn_tool_dist["0"]

# agent metrics
agent_calls = [a for a in agent_calls if a["sid"] in sessions]
agent_per_session = collections.Counter(a["sid"] for a in agent_calls)
st_dist = collections.Counter(a["subagent_type"] or "(none)" for a in agent_calls)
model_dist = collections.Counter(a["model"] or "(unset)" for a in agent_calls)
plens = sorted(a["plen"] for a in agent_calls)
def q(xs, p):
    if not xs: return 0
    return xs[min(len(xs)-1, int(p*len(xs)))]
short_results = 0; neg_results = 0; matched = 0; failed_notif = 0; result_examples = []
for a in agent_calls:
    r = agent_results.get(a["id"]); n = agent_notifs.get(a["id"])
    txt = ""
    if n:
        matched += 1
        txt = n[1]
        if n[0] != "completed":
            failed_notif += 1
    elif r and "Async agent launched" not in r[1]:
        matched += 1
        txt = r[1]
        if r[0] < 300:
            short_results += 1
    if txt and NEG_HITS.search(txt):
        neg_results += 1
        if len(result_examples) < 8:
            result_examples.append((a["project"], a["desc"], txt[:160].replace("\n", " ")))
sub_short = sum(1 for p in sub_payloads if p[2] < 300)
sub_neg = sum(1 for p in sub_payloads if NEG_HITS.search(p[3]))

# re-dispatch detection
def norm(p): return re.sub(r"\s+", " ", p.lower())[:600]
redisp = []
by_sess = collections.defaultdict(list)
for a in agent_calls:
    by_sess[a["sid"]].append(a)
exact = collections.Counter(norm(a["prompt"]) for a in agent_calls if a["plen"] > 80)
exact_dups = sum(v-1 for v in exact.values() if v > 1)
for sid, L in by_sess.items():
    for i in range(len(L)):
        for j in range(i+1, len(L)):
            a, b = L[i], L[j]
            if a["plen"] < 80 or b["plen"] < 80: continue
            r = difflib.SequenceMatcher(None, norm(a["prompt"]), norm(b["prompt"])).quick_ratio()
            if r >= 0.85:
                r2 = difflib.SequenceMatcher(None, norm(a["prompt"]), norm(b["prompt"])).ratio()
                if r2 >= 0.85:
                    redisp.append((sessions[sid]["project"], sid, a["desc"], b["desc"], round(r2, 2), a["ts"], b["ts"]))

# compaction
compactions = [c for c in compactions if c[0] in sessions]
longest = sorted(sessions.values(), key=lambda S: -S["lines"])[:10]

# search doctrine
bash_search = sum(S["bash_search"] for S in sessions.values())
rgg = sum(S["read_glob_grep"] for S in sessions.values())
serena = sum(v for k, v in tool_counter.items() if "serena" in (k or "").lower())

# waits
waits = []
for S in sessions.values():
    ev = sorted([e for e in S["events"] if e[0]], key=lambda e: e[0])
    for i, e in enumerate(ev):
        if e[1] != "user": continue
        tools = collections.Counter(); first_any = None; first_text = None
        for e2 in ev[i+1:]:
            if e2[1] == "user": break
            if e2[1] == "tool":
                tools[e2[2]] += 1
                first_any = first_any or e2[0]
            if e2[1] == "text":
                first_any = first_any or e2[0]
                first_text = e2[0]; break
        if first_text:
            waits.append(((first_text - e[0]).total_seconds(), (first_any - e[0]).total_seconds(), S["project"], S["sid"], e[0].isoformat()[:16], e[2][:90], dict(tools.most_common(4))))
wait_text = sorted(w[0] for w in waits)
wait_any = sorted(w[1] for w in waits)
top_waits = sorted(waits, key=lambda w: -w[0])[:10]

# history + hooks
hist = collections.Counter(); hist_n = 0
with open(os.path.join(HOME, ".claude", "history.jsonl"), errors="replace") as fh:
    for line in fh:
        try: o = json.loads(line)
        except: continue
        t = datetime.fromtimestamp((o.get("timestamp") or 0)/1000, tz=timezone.utc)
        if W0 <= t < W1:
            hist_n += 1; hist[os.path.basename(o.get("project") or "?")] += 1
hooks = collections.Counter()
for hf in glob.glob(os.path.join(HOME, ".claude", "hook-feedback", "*.jsonl")):
    with open(hf, errors="replace") as fh:
        for line in fh:
            try: o = json.loads(line)
            except: continue
            t = ts(o.get("timestamp") or "")
            if t and W0 <= t < W1:
                hooks[(o.get("hook"), o.get("kind"), o.get("reason"))] += 1
installed = sorted(os.listdir(os.path.join(HOME, ".claude", "skills")))

report = dict(
    window=f"{W0.isoformat()}..{W1.isoformat()}", files_scanned=len(files), sessions=n_sessions,
    total_lines=sum(S["lines"] for S in sessions.values()), total_mb=round(sum(S["bytes"] for S in sessions.values())/1e6, 1),
    assistant_turns=turns, tool_uses=tool_uses, turns_with_tools=turns_with_tools,
    turn_tool_dist=dict(turn_tool_dist), user_prompts=sum(S["user_prompts"] for S in sessions.values()),
    top_tools=tool_counter.most_common(25), model_usage={k: dict(v) for k, v in model_usage.items()},
    agent=dict(calls=len(agent_calls), sessions_with_agents=len(agent_per_session),
               per_session_top=[(sessions[s]["project"], s[:8], n) for s, n in agent_per_session.most_common(10)],
               subagent_type=dict(st_dist), model=dict(model_dist),
               caller_model=dict(collections.Counter(a["caller_model"] for a in agent_calls)),
               prompt_len=dict(min=plens[0] if plens else 0, p25=q(plens, .25), median=q(plens, .5), p75=q(plens, .75), p95=q(plens, .95), max=plens[-1] if plens else 0),
               results_matched=matched, sync_results_under_300=short_results, notif_not_completed=failed_notif,
               results_neg_keyword=neg_results, result_examples=result_examples,
               subagent_files=len(sub_payloads), subagent_final_under_300=sub_short, subagent_final_neg=sub_neg,
               exact_dup_prompts=exact_dups, near_dup_pairs=len(redisp), near_dup_examples=redisp[:15]),
    skills=dict(uses=skill_uses.most_common(), installed=len(installed),
                installed_used=sorted(set(installed) & set(skill_uses)), installed_unused=sorted(set(installed) - set(skill_uses)),
                used_not_installed=sorted(set(k for k in skill_uses if k) - set(installed))),
    compaction=dict(boundaries=len(compactions), sessions_with=len(set(c[0] for c in compactions)),
                    triggers=dict(collections.Counter(c[1] for c in compactions)),
                    pre_tokens=[c[2] for c in compactions], post_tokens=[c[3] for c in compactions],
                    resumes=sum(S["resume"] for S in sessions.values()), compaction_errors=api_errors["compaction_error"],
                    api_error_msgs=api_errors["api_error_msg"],
                    longest=[(S["project"], S["sid"][:8], S["lines"], round(S["bytes"]/1e6, 1), len(S["turns"]), S["compact"], S["resume"]) for S in longest]),
    search=dict(bash_search_cmds=bash_search, read_glob_grep_tools=rgg, serena_tools=serena,
                grep_tool=tool_counter.get("Grep", 0), glob_tool=tool_counter.get("Glob", 0), read_tool=tool_counter.get("Read", 0),
                bash_total=tool_counter.get("Bash", 0), sessions_with_bash_search=sum(1 for S in sessions.values() if S["bash_search"]),
                examples=search_cmds[:12]),
    corrections=dict(total=len(corrections), sessions=len(corr_per_session),
                     per_session_top=[(sessions[s]["project"], s[:8], n) for s, n in corr_per_session.most_common(10)],
                     quotes=corrections),
    waits=dict(n=len(waits), median_to_text_s=round(statistics.median(wait_text), 1) if wait_text else 0,
               p90_to_text_s=round(q(wait_text, .9), 1), median_to_any_s=round(statistics.median(wait_any), 1) if wait_any else 0,
               over_5min=sum(1 for w in wait_text if w > 300), top10=top_waits),
    history=dict(prompts=hist_n, by_project=hist.most_common(12)),
    hooks=sorted(((k, v) for k, v in hooks.items()), key=lambda kv: -kv[1])[:30],
    stop_hooks=dict(hook_summaries),
    sessions_table=sorted([(S["project"], S["sid"][:8], S["lines"], len(S["turns"]), S["tool_use"], S["agent"], S["user_prompts"], S["compact"], S["resume"], corr_per_session.get(S["sid"], 0), S["models"].most_common(1)[0][0] if S["models"] else "?") for S in sessions.values()], key=lambda r: -r[2]),
)
with open(sys.argv[1], "w") as output:
    json.dump(report, output, indent=1, default=str)
print("wrote", sys.argv[1])
