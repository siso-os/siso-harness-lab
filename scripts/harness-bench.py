#!/usr/bin/env python3
"""harness-bench: the same real tasks through Claude Code and omp, compared on tokens, list-price dollars, time and result.

  harness-bench [--configs cc-haiku,omp-haiku,...] [--tasks t1,t2,t3] [--out FILE.jsonl]

Claude Code runs on the plan login (the supported route). omp never touches the plan: it runs on an Anthropic API key
(isolated profile, so no stored OAuth can be picked up) or on DeepSeek. Each edit task gets its own scratch copy.
"""
import argparse, json, os, re, shutil, subprocess, tempfile, time

HOME = os.path.expanduser("~")
LAB = HOME + "/SISO_Workspace/SISO_Agents/siso-harness-lab"
KEYFILE = HOME + "/SISO_Workspace/.credentials/projects/siso-labs/anthropic-console.env"


def api_key():
    for line in open(KEYFILE):
        m = re.match(r"\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*['\"]?([^'\"\s]+)", line)
        if m:
            return m.group(1)
    raise SystemExit("no ANTHROPIC_API_KEY in key file")


START = time.time()


def scripts_truth():
    # harness-bench.py only names the field in a task prompt; it reads CLI JSON, not transcripts (12 Oct: this wrongly
    # failed every Haiku run on t4). Scripts added after a run started are not held against it either.
    return sorted(f for f in os.listdir(LAB + "/scripts") if f.endswith(".py") and f != "harness-bench.py"
                  and "cache_read_input_tokens" in open(LAB + "/scripts/" + f, errors="ignore").read()
                  and os.path.getmtime(LAB + "/scripts/" + f) < START)


def t3_check(d):
    p = subprocess.run(["python3", "token-where.py", "--hours", "1", "--top", "2"], cwd=d, capture_output=True, text=True, timeout=300)
    if p.returncode:
        return False
    lines = [l for l in p.stdout.splitlines() if l.strip().startswith("turn")]
    return bool(lines) and lines[0].count("%") <= 2


# The lean seat: Opus thinks, Haiku 5.5 does the bulk (same env and words as the Agent Base host's lean setting).
LEAN_ENV = {"ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-5-5", "CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-5-5"}
LEAN_PROMPT = ("Token rule: you are the thinker; Haiku 5.5 is the hands (about 50x cheaper per token than you). For reading, searching "
               "or running commands that will take more than two tool calls, dispatch one sub-agent with model haiku, give it a precise "
               "question, and ask for a compact answer with file:line evidence; work from its return. Several independent questions go to "
               "several sub-agents in one message. Keep judgement, the final edit and the answer to the user yourself.")

TASKS = {
    "t1": {"prompt": "Read ~/SISO_Workspace/SISO_Agents/agent-zero/siso-agent-zero/bin/stack-doctor. Which function computes the share of Claude tokens spent on turns Shaan did not start, and which trigger classes does it sort turns into? Answer in at most 4 lines. Do not edit anything.",
           "check": lambda out, d: "turns_today" in out and "compaction" in out.lower()},
    "t2": {"prompt": "Which Python files directly under scripts/ in this repo contain the string cache_read_input_tokens? Reply with the file names only, comma-separated, sorted. Do not edit anything.",
           "check": lambda out, d: all(f in out for f in scripts_truth())},
    "t4": {"prompt": "Which scripts directly under scripts/ in this repo read Claude Code transcript files (the projects/*.jsonl under a Claude config dir), and which usage fields does each read? Reply as a compact table: script | usage fields. Do not edit anything.",
           "check": lambda out, d: all(f in out for f in scripts_truth())},
    "t5": {"prompt": "In ~/SISO_Workspace/SISO_Agency/apps/siso-internal-labs/siso-internal-labs-agent-base, how does the Agent Base host (services/host) decide when a seat's Claude session auto-compacts, and where is the threshold set? Cite file:line. Do not edit anything.",
           "check": lambda out, d: "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" in out and "30" in out},
    "t6": {"prompt": "New task, unrelated to the conversation so far. In ~/SISO_Workspace/SISO_Agency/apps/siso-internal-labs/siso-internal-labs-agent-base/services/host/src, list every option or environment variable the host sets when it starts a seat's Claude session (the query() call and the env it passes), each with file:line and one line on what it controls. Do not edit anything.",
           "check": lambda out, d: all(k in out for k in ("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "settingSources", "systemPrompt"))},
    "t7": {"prompt": "New task, unrelated to the conversation so far. In ~/SISO_Workspace/SISO_Agents/siso-estate, find how `estate where <words>` ranks its results: which function does the ranking, which signals add or subtract score, and what data it searches over. Cite file:line. Do not edit anything.",
           "check": lambda out, d: "bin/estate" in out and any(n in out for n in (":191", ":192", ":221", "191-", "191–"))},
    "t8": {"prompt": "New task, unrelated to the conversation so far. For every Python file in ~/SISO_Workspace/SISO_Agents/siso-estate/tools/, give one line: file name, what it does, and its command-line flags if it has any (read each file to be sure; do not guess from names). Do not edit anything.",
           "check": lambda out, d: sum(f[:-3] in out for f in os.listdir(HOME + "/SISO_Workspace/SISO_Agents/siso-estate/tools") if f.endswith(".py")) >= 0.9 * len([f for f in os.listdir(HOME + "/SISO_Workspace/SISO_Agents/siso-estate/tools") if f.endswith(".py")])},
    "t3": {"prompt": "In this directory, add a --top N option (default 8) to token-where.py that limits how many items each printed split line shows. Then run `python3 token-where.py --hours 1 --top 2` to confirm it works. Keep the change minimal.",
           "check": lambda out, d: t3_check(d), "scratch": True},
}


# Shaan, 12 Oct: "Haiku 5.5 and then Opus as a brain ... hire a subagent which can be called in for reasoning".
# Two ways: Claude Code's server-side advisor (Opus sees the whole chat when asked), or an Opus sub-agent Haiku briefs.
# Anthropic: executors under-call the advisor unless the system prompt says when (docs-code en-advisor.md).
BRAIN_ADVISOR = ("You are Haiku 5.5, the hands; Opus 5.5 is your advisor (the advisor tool). Consult the advisor: before you settle "
                 "on an approach for anything non-trivial, when two attempts have failed or results conflict, and always once "
                 "before your final answer to check it. Do the reading, searching and running yourself.")
BRAIN_HIRE = ("You are Haiku 5.5, the hands. Do the reading, searching and running yourself. For judgement (choosing an approach, "
              "reconciling conflicting evidence, checking a non-trivial answer before you give it), dispatch one sub-agent with "
              "model opus: give it the question and the evidence you gathered (file:line and short excerpts), and ask for a short "
              "verdict. Use it at most twice per task and never to read files for you.")


def run(cfg, task, key, fork=None):
    t = TASKS[task]
    d = LAB
    if t.get("scratch"):
        d = tempfile.mkdtemp(prefix=f"hb-{cfg}-{task}-")
        shutil.copy(LAB + "/scripts/token-where.py", d)
    env = dict(os.environ)
    t0 = time.time()
    if cfg.startswith("cc-"):
        model = {"cc-fable": "claude-fable-5-1", "cc-fable-lean": "claude-fable-5-1", "cc-fable-medium": "claude-fable-5-1",
                 "cc-opus-xhigh": "claude-opus-5-5", "cc-opus-high": "claude-opus-5-5", "cc-opus-medium": "claude-opus-5-5", "cc-opus-low": "claude-opus-5-5",
                 "cc-opus-lean": "claude-opus-5-5", "cc-haiku": "claude-haiku-4-5", "cc-haiku55": "claude-haiku-5-5", "cc-h55-advisor": "claude-haiku-5-5", "cc-h55-brain": "claude-haiku-5-5", "cc-h55-hire": "claude-haiku-5-5", "cc-opus": "claude-opus-5-5", "cc-sonnet55": "claude-sonnet-5-5", "cc-s55-advisor": "claude-sonnet-5-5"}[cfg]
        cmd = ["claude", "-p", t["prompt"], "--model", model, "--output-format", "json", "--permission-mode", "bypassPermissions"]
        for lvl in ("xhigh", "high", "medium", "low"):
            if cfg in (f"cc-opus-{lvl}", f"cc-fable-{lvl}"):
                cmd += ["--effort", lvl]
        if fork:  # continue a copy of a real long session, so each call carries a real seat's context
            cmd += ["--resume", fork, "--fork-session"]
        if cfg.endswith("-lean"):
            env.update(LEAN_ENV)
            if fork:  # same cached prefix for both arms: the rule rides in the message, not the system prompt
                cmd[2] = LEAN_PROMPT + "\n\n" + t["prompt"]
            else:
                cmd += ["--append-system-prompt", LEAN_PROMPT]
        if cfg.endswith("-advisor") or cfg == "cc-h55-brain":
            cmd += ["--advisor", "claude-opus-5-5"]
        if cfg == "cc-h55-brain":
            cmd += ["--append-system-prompt", BRAIN_ADVISOR]
        if cfg == "cc-h55-hire":
            cmd += ["--append-system-prompt", BRAIN_HIRE]
        p = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
        try:
            j = json.loads(p.stdout[p.stdout.index("{"):])
        except ValueError:
            return {"cfg": cfg, "task": task, "error": p.stderr[-300:]}
        mu = j.get("modelUsage") or {}
        tok = sum(v.get("inputTokens", 0) + v.get("outputTokens", 0) + v.get("cacheReadInputTokens", 0) + v.get("cacheCreationInputTokens", 0) for v in mu.values())
        out, usd, turns = j.get("result", ""), j.get("total_cost_usd", 0), j.get("num_turns")
        models = list(mu)
        if j.get("usage", {}).get("server_tool_use"):
            models.append("server_tools=" + json.dumps(j["usage"]["server_tool_use"]))
        open(f"/tmp/hb/raw-{cfg}-{task}.json", "w").write(p.stdout)
    else:
        model, extra = {"omp-haiku": ("anthropic/claude-haiku-4-5", ["--profile", "harness-bench"]),
                        "omp-haiku55": ("anthropic/claude-haiku-5-5", ["--profile", "harness-bench"]),
                        "omp-deepseek": ("opencode-go/deepseek-v4.1-flash", [])}[cfg]
        if cfg.startswith("omp-haiku"):
            env["ANTHROPIC_API_KEY"] = key
        cmd = ["omp", "-p", t["prompt"], "--model", model, "--mode", "json", "--no-session", "--auto-approve", "--no-title"] + extra
        p = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
        tok, usd, turns, out, models = 0, 0.0, 0, "", set()
        for line in p.stdout.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "turn_end":
                m = e.get("message") or {}
                u = m.get("usage") or {}
                tok += u.get("totalTokens", 0)
                usd += (u.get("cost") or {}).get("total", 0)
                turns += 1
                models.add(f"{m.get('provider')}/{m.get('model')}")
                out = "".join(b.get("text", "") for b in m.get("content", []) if b.get("type") == "text") or out
        models = sorted(models)
    secs = round(time.time() - t0, 1)
    ok = bool(t["check"](out, d))
    return {"cfg": cfg, "task": task, "ok": ok, "tokens": tok, "usd": round(usd, 4), "turns": turns, "secs": secs, "models": models, "answer": out[-300:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="cc-haiku,omp-haiku,omp-deepseek,cc-opus")
    ap.add_argument("--tasks", default="t1,t2,t3")
    ap.add_argument("--fork", help="session id to fork for each Claude Code run")
    ap.add_argument("--out", default=LAB + "/.agents/runs/2026-10-12-harness/bench.jsonl")
    a = ap.parse_args()
    key = api_key() if "omp-haiku" in a.configs else None
    # the bench profile's models.json carries the anthropic-workspace-id header this console key needs
    for task in a.tasks.split(","):
        for cfg in a.configs.split(","):
            r = run(cfg, task, key, a.fork)
            r["fork"] = a.fork
            open(a.out, "a").write(json.dumps(r) + "\n")
            print(f"{task} {cfg:13} ok={r.get('ok')} tokens={r.get('tokens')} ${r.get('usd')} turns={r.get('turns')} {r.get('secs')}s {r.get('models') or r.get('error')}", flush=True)


if __name__ == "__main__":
    main()
