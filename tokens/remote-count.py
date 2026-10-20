#!/usr/bin/env python3
"""remote-count.py: token counts and effort settings on one machine. Counts only, never message text.

Run on another box over ssh, no install needed:
  ssh <host> python3 - --hours 24 < tokens/remote-count.py

Claude: every */projects/**/*.jsonl under ~/.claude*, ~/.config/claude*, deduped by (message.id, requestId).
Codex: ~/.codex/sessions/**/*.jsonl, the last total_token_usage of each session file.
Settings: model, effortLevel and modelSettings from each Claude config dir's settings.json; model and
model_reasoning_effort from ~/.codex/config.toml. Prints one JSON object.
"""
import glob, json, os, re, sys, time

hours = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 24
t0 = time.time() - hours * 3600
H = os.path.expanduser("~")
dirs = sorted({d for d in glob.glob(H + "/.claude*") + glob.glob(H + "/.config/claude*") if os.path.isdir(d)})

out = {"host": os.uname().nodename, "hours": hours, "claude": {}, "codex": {}, "settings": {}}
seen = set()
for d in dirs:
    s = os.path.join(d, "settings.json")
    if os.path.exists(s):
        try:
            j = json.load(open(s))
            out["settings"][d.replace(H, "~")] = {k: j.get(k) for k in ("model", "effortLevel", "modelSettings",
                                                                        "advisorModel") if k in j}
        except Exception:
            pass
    for f in glob.glob(d + "/projects/**/*.jsonl", recursive=True):
        try:
            if os.path.getmtime(f) < t0:
                continue
            sub = "/subagents/" in f
            for line in open(f, errors="ignore"):
                if '"usage"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("message") or {}
                u = m.get("usage")
                if not u or not isinstance(m, dict):
                    continue
                ts = r.get("timestamp", "")
                try:
                    if time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone < t0:
                        continue
                except Exception:
                    pass
                key = (m.get("id"), r.get("requestId"))
                if key in seen:
                    continue
                seen.add(key)
                k = (m.get("model") or "?") + (" sub" if sub else "")
                a = out["claude"].setdefault(k, {"calls": 0, "in": 0, "write": 0, "w1h": 0, "read": 0, "out": 0,
                                                  "sessions": set(), "dirs": set()})
                cc = u.get("cache_creation") or {}
                a["calls"] += 1
                a["in"] += u.get("input_tokens", 0) or 0
                a["write"] += u.get("cache_creation_input_tokens", 0) or 0
                a["w1h"] += cc.get("ephemeral_1h_input_tokens", 0) or 0
                a["read"] += u.get("cache_read_input_tokens", 0) or 0
                a["out"] += u.get("output_tokens", 0) or 0
                a["sessions"].add(f)
                a["dirs"].add(d.replace(H, "~"))
        except Exception:
            continue
for a in out["claude"].values():
    a["sessions"] = len(a["sessions"])
    a["dirs"] = sorted(a["dirs"])

cfg = H + "/.codex/config.toml"
if os.path.exists(cfg):
    t = open(cfg, errors="ignore").read()
    out["settings"]["~/.codex/config.toml"] = dict(re.findall(r'^(model|model_reasoning_effort)\s*=\s*"([^"]*)"', t, re.M))
for f in glob.glob(H + "/.codex/sessions/**/*.jsonl", recursive=True):
    try:
        if os.path.getmtime(f) < t0:
            continue
        last, model, effort = None, "?", "?"
        for line in open(f, errors="ignore"):
            if '"turn_context"' in line or '"total_token_usage"' in line:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                p = r.get("payload") or {}
                if r.get("type") == "turn_context":
                    model, effort = p.get("model", model), p.get("effort") or p.get("reasoning_effort") or effort
                tu = (p.get("info") or {}).get("total_token_usage")
                if tu:
                    last = tu
        if last:
            a = out["codex"].setdefault(f"{model} effort={effort}", {"sessions": 0, "in": 0, "cached": 0, "out": 0,
                                                                      "reasoning": 0})
            a["sessions"] += 1
            a["in"] += last.get("input_tokens", 0)
            a["cached"] += last.get("cached_input_tokens", 0)
            a["out"] += last.get("output_tokens", 0)
            a["reasoning"] += last.get("reasoning_output_tokens", 0)
    except Exception:
        continue
print(json.dumps(out, default=str))
