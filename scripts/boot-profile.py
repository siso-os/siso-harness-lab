#!/usr/bin/env python3
"""boot-profile.py [--days 14] [--write] — the lean boot profile for herdr agents, from what agents actually use.

STACK-OPT item 4 (2 Oct 2026). Shaan, 14:35: boot context by task, loaded on demand ("rollable"). Every skill's
description rides in every request of every agent; over 14 days (1,657 sessions) 39 of 58 skills were never invoked.
Skills used in the window stay "on" (description listed); the rest go "name-only" (listed by name, invocable, no
description), so an agent can still roll one in when its task needs it. Artifact skills are user-invocable-only
because the Artifact tool is off for agents (Shaan: never a claude.ai artifact).

Writes config/agent-boot.json, which bin/agent-boot.sh passes to claude via --settings. Prints the on/name-only split.
"""
import argparse, glob, json, os, re, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "config", "agent-boot.json")
ROOTS = ["~/.claude/projects", "~/.config/claude-siso-3/projects"]
SKILLS = "~/.claude/skills"
ALWAYS_ON = {"self-compact", "shaan-report", "adhd-agent-output"}  # named by the brain for every agent
ARTIFACT = ["artifact-design", "artifact-diagramming", "artifact-capabilities"]
# Model-listed skills that ship with Claude Code or its plugins (2.1.287); same rule: unused in the window -> name-only.
SHIPPED = ["codex-companion", "dataviz", "update-config", "keybindings-help", "code-review", "simplify",
           "fewer-permission-prompts", "loop", "schedule", "claude-api", "workflow-authoring", "claude-in-chrome", "run",
           "plugin-authoring", "init", "security-review", "anthropic-skills:docs", "anthropic-skills:docx",
           "anthropic-skills:google-workspace", "anthropic-skills:import-memory", "anthropic-skills:morning",
           "anthropic-skills:pdf", "anthropic-skills:pptx", "anthropic-skills:skill-creator", "anthropic-skills:xlsx"]


def used(days):
    cut, n = time.time() - days * 86400, {}
    for root in ROOTS:
        for f in glob.glob(os.path.expanduser(root) + "/*/*.jsonl"):
            if os.path.getmtime(f) < cut:
                continue
            with open(f, errors="replace") as fh:
                for line in fh:
                    if '"Skill"' in line:
                        for m in re.finditer(r'"name":"Skill","input":\{"skill":"([^"]+)"', line):
                            n[m[1].split(":")[-1]] = n.get(m[1].split(":")[-1], 0) + 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    n = used(a.days)
    d = os.path.expanduser(SKILLS)
    names = sorted(s for s in os.listdir(d) if os.path.isfile(os.path.join(d, s, "SKILL.md")))
    over = {s: "name-only" for s in names + SHIPPED if not n.get(s.split(":")[-1]) and s not in ALWAYS_ON}
    over.update({s: "user-invocable-only" for s in ARTIFACT})
    profile = {
        "_source": f"scripts/boot-profile.py --days {a.days} --write ({time.strftime('%Y-%m-%d')}); regenerate, don't hand-edit",
        "enableArtifact": False,
        "skillOverrides": dict(sorted(over.items())),
    }
    on = [s for s in names if s not in over]
    print(f"on ({len(on)}): {', '.join(on)}")
    print(f"name-only ({sum(v == 'name-only' for v in over.values())}): {', '.join(k for k, v in over.items() if v == 'name-only')}")
    if a.write:
        with open(OUT, "w") as f:
            json.dump(profile, f, indent=2)
            f.write("\n")
        print("wrote", OUT)


if __name__ == "__main__":
    main()
