#!/usr/bin/env python3
"""Read-only scanner for dead routes agents get pointed at: bad subagent_type
values in skills, unreachable localhost endpoints, missing commands, missing
paths, and broken LaunchAgents.

Usage:
    python3 route_doctor.py            # human table, exit 1 if any route dead
    python3 route_doctor.py --json     # machine output on stdout

Scans (see BUILD-BRIEF.md W1 for the exact contract):
  - Skill roots: ~/.claude/skills, ~/.agents/skills, ~/.codex/skills
      (follow symlinks, dedupe by realpath). Per SKILL.md:
        * subagent_type values -> built-in name or ~/.claude/agents/<x>.md
        * http(s)://127.0.0.1:PORT / localhost:PORT / 0.0.0.0:PORT -> HTTP GET, 2s timeout
        * first token of command lines in fenced code blocks -> `command -v` via zsh -lc
        * absolute or ~ paths mentioned anywhere -> must exist
  - LaunchAgents: ~/Library/LaunchAgents/com.siso.*.plist
        * ProgramArguments[0] must exist
        * loaded with non-zero last exit status -> flag
        * any http://127.0.0.1|localhost URL in the plist -> probe
"""
import json
import os
import plistlib
import re
import subprocess
import sys
import urllib.request
from urllib.error import URLError, HTTPError

HOME = os.path.expanduser("~")
TIMEOUT_S = 2.0

SKILL_ROOTS = [
    os.path.join(HOME, ".claude", "skills"),
    os.path.join(HOME, ".agents", "skills"),
    os.path.join(HOME, ".codex", "skills"),
]
LAUNCH_AGENTS_DIR = os.path.join(HOME, "Library", "LaunchAgents")
BUILTIN_SUBAGENTS = {
    "general-purpose", "Explore", "Plan", "claude", "claude-code-guide",
    "statusline-setup",
}

# Shell builtins and generic tools: never flagged as a dead command.
SKIP_TOKENS = {
    "cd", "echo", "export", "git", "node", "python3", "python", "npx", "npm",
    "jq", "grep", "rg", "sed", "awk", "cat", "ls", "curl", "mkdir", "rm",
    "cp", "mv", "for", "if", "then", "do", "done", "open", "set", "source",
    "test", "while", "case", "esac", "fi", "else", "elif",
    "function", "return", "local", "readonly", "unset", "shift", "wait",
    "trap", "exec", "eval", "true", "false", "pwd", "which", "type", "printf",
    "read", "declare", "let", "until", "break", "continue", "exit",
    # Fix-round-2 rule 2: Linux-only commands that skills legitimately
    # document for a VPS/remote-host context — never installed on macOS,
    # so never a laptop documentation bug.
    "systemctl", "journalctl", "apt", "apt-get", "useradd", "ufw", "service",
}
# Prose words repeatedly seen as false command hits in labelled fences that
# are actually narrative/pseudo-code (numbered steps, "then do X" prose).
PROSE_STOPLIST = {
    "after", "before", "then", "else", "done", "trigger", "media", "use",
    "execute", "import", "export", "prop", "plane", "and", "or", "the",
    "a", "an", "when", "where", "what", "this", "that", "these", "those",
    "run", "call", "invoke", "note", "example", "see", "via", "with",
    "for", "from", "into", "if",
}
# A real command token: lowercase, starts with a letter, only
# letters/digits/underscore/hyphen. This alone rejects tree-drawing
# glyphs, table pipes, numbered-list markers, capitalized prose words,
# and punctuation — no path separators or extensions allowed here since
# those are handled (and mostly skipped) separately per fix-round-1 rule 1.
COMMAND_SHAPE_RE = re.compile(r'^[a-z][a-z0-9_-]*$')
# A token containing "/" or a recognizable file extension is a path or a
# source file mentioned in a snippet (server.mjs, public/index.html,
# scripts/init_skill.py) — never a command to `command -v` check.
PATH_LIKE_TOKEN_RE = re.compile(r'/|\.[A-Za-z][A-Za-z0-9]{1,4}$')

# Conventional placeholder segments used in docs/examples everywhere:
# never real routes on this machine, so never worth flagging as dead.
PLACEHOLDER_PATH_RE = re.compile(
    r'/(path/to|absolute|<[^>]*>|\[[^\]]*\]|YYYY|project|repo-root)\b',
    re.I,
)
# /tmp/... in docs is almost always an example output path (a screenshot,
# a log, a scratch file a command *will* create), not a route the doctor
# should verify pre-exists.
TMP_PATH_RE = re.compile(r'^/tmp/')
# Fix-round-1 rule 2: only these leading segments are real, checkable
# machine paths. Anything else with a leading "/" (/mod/ui/, /api/health,
# /demo/) is a URL path documented in prose, not a filesystem route.
#
# Fix-round-2 rule 1: bare "/opt/" is dropped — /opt/siso-* paths in
# siso-compute-pool, siso-credentials and siso-plane-ops are VPS paths
# documented for a remote host, not this laptop. Only /opt/homebrew/ (the
# real local Homebrew prefix on Apple Silicon) stays checkable.
REAL_PATH_PREFIXES = (
    "/Users/", "/opt/homebrew/", "/Applications/", "/Library/",
    "/usr/local/", "/private/",
)

SUBAGENT_RE = re.compile(r'subagent_type\s*[:=]\s*["\']?([A-Za-z0-9_-]+)["\']?')
URL_RE = re.compile(
    r'https?://(127\.0\.0\.1|localhost|0\.0\.0\.0)(:\d+)?[A-Za-z0-9._~/?#\[\]@!$&\'()*+,;=%-]*'
)
FENCE_OPEN_RE = re.compile(r'^```([A-Za-z0-9_-]*)\s*$')
# Fix-round-1 rule 1: only these labelled fences are scanned for commands.
# Unlabelled (bare ```) fences are never scanned — skills use them for
# directory trees, YAML-ish specs, and templated prose, not shell.
COMMAND_FENCE_LANGS = {"bash", "sh", "zsh", "shell", "console"}
# Require a boundary before the leading slash/~ so "SVG/vector/code-native"
# inside a prose sentence doesn't match starting mid-word at "/vector".
ABS_PATH_RE = re.compile(
    r'(?:(?<=^)|(?<=[\s`\'"(\[]))(?:~|/[A-Za-z0-9._-]+/[A-Za-z0-9._~/-]*)'
)
# Fix-round-1 rule 3: an endpoint mentioned as illustration, not a route
# to actually verify.
EXAMPLE_LINE_RE = re.compile(r'e\.g\.|example|<', re.I)

# Fix-round-2 rule 4: bundled/vendored skill locations. The anthropic
# pdf/pptx/morning skills document optional tools (qpdf, pdftk,
# markitdown) that are install-if-you-need-them, not a laptop
# documentation bug — skip command checks (not other checks) for any
# SKILL.md under one of these. ".claude/plugins/cache/" is the real
# plugin-cache path (per `installed_plugins.json`); ".claude/skills/synced/"
# and ".codex/skills/.system/" are where the bundled skills that actually
# reference qpdf/pdftk/markitdown live on this machine today.
PLUGIN_CACHE_MARKERS = (
    os.path.join(".claude", "plugins", "cache") + os.sep,
    os.path.join(".claude", "plugins") + os.sep,
    os.path.join(".claude", "skills", "synced") + os.sep,
    os.path.join(".codex", "skills", ".system") + os.sep,
)


def is_bundled_skill_path(skill_md_path):
    return any(marker in skill_md_path for marker in PLUGIN_CACHE_MARKERS)


def realpath_dedupe(paths):
    """Follow symlinks, dedupe roots by realpath, preserve first-seen order."""
    seen = set()
    out = []
    for p in paths:
        if not os.path.isdir(p):
            continue
        rp = os.path.realpath(p)
        if rp in seen:
            continue
        seen.add(rp)
        out.append(p)
    return out


def find_skill_md_files():
    """Walk each skill root (following symlinks) and collect SKILL.md files,
    deduped by realpath so a symlinked skill isn't scanned twice."""
    roots = realpath_dedupe(SKILL_ROOTS)
    seen_files = set()
    files = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
            if "SKILL.md" in filenames:
                fp = os.path.join(dirpath, "SKILL.md")
                rp = os.path.realpath(fp)
                if rp in seen_files:
                    continue
                seen_files.add(rp)
                files.append(fp)
    return files


def check_http(url):
    """Any HTTP response (even 4xx/5xx) means alive. Refused/timeout = dead."""
    try:
        req = urllib.request.Request(url, method="GET")
        urllib.request.urlopen(req, timeout=TIMEOUT_S)
        return True, None
    except HTTPError:
        return True, None  # server responded, just not with 2xx
    except (URLError, TimeoutError, ConnectionError, OSError) as e:
        return False, str(e)
    except Exception as e:
        # Malformed URL text pulled from prose (stray unicode, etc.) is a
        # dead/unreachable route, not a scanner crash.
        return False, f"malformed url: {e}"


def check_command(tok):
    try:
        r = subprocess.run(
            ["zsh", "-lc", f"command -v {tok!r}"],
            capture_output=True, timeout=5, text=True,
        )
        return r.returncode == 0
    except Exception:
        return False


def line_of(text, idx):
    return text.count("\n", 0, idx) + 1


_APPLICATIONS_DIR = "/Applications"
_applications_listing_cache = None


def applications_listing():
    global _applications_listing_cache
    if _applications_listing_cache is None:
        try:
            _applications_listing_cache = os.listdir(_APPLICATIONS_DIR)
        except OSError:
            _applications_listing_cache = []
    return _applications_listing_cache


def path_exists_with_applications_fallback(expanded_path, original_route):
    """Fix-round-2 rule 3: ABS_PATH_RE stops at the first space (paths in
    prose/shell aren't space-delimited), so "/Applications/Cloudflare
    WARP.app/..." is truncated to "/Applications/Cloudflare" — a name that
    never exists verbatim even though the real app does. For any
    "/Applications/<Name>" route, also count it alive when some entry in
    /Applications starts with <Name> (the untruncated real name)."""
    if os.path.exists(expanded_path):
        return True
    prefix = _APPLICATIONS_DIR + "/"
    if not original_route.startswith(prefix):
        return False
    name = original_route[len(prefix):]
    if not name:
        return False
    return any(entry.startswith(name) for entry in applications_listing())


def scan_skill_file(path, findings):
    try:
        with open(path, "r", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return

    bundled = is_bundled_skill_path(path)

    # 1. subagent_type values
    for m in SUBAGENT_RE.finditer(text):
        val = m.group(1)
        ln = line_of(text, m.start())
        if val in BUILTIN_SUBAGENTS:
            findings.append({
                "kind": "subagent_type", "route": val, "status": "alive",
                "file": path, "line": ln, "reason": None,
            })
            continue
        agent_file = os.path.join(HOME, ".claude", "agents", f"{val}.md")
        if os.path.isfile(agent_file):
            findings.append({
                "kind": "subagent_type", "route": val, "status": "alive",
                "file": path, "line": ln, "reason": None,
            })
            continue
        findings.append({
            "kind": "subagent_type", "route": val, "status": "dead",
            "file": path, "line": ln,
            "reason": f"not built-in and {agent_file} does not exist",
        })

    # 2. localhost endpoints. Fix-round-1 rule 3: a refused local endpoint
    # is informational ("down"), not a hard "dead" route — the service may
    # simply not be running right now, unlike a missing command/path/agent
    # type which is a documentation bug regardless of what's running. An
    # endpoint on an illustrative line ("e.g.", "example", or a "<...>"
    # placeholder nearby) is skipped entirely: it was never claimed live.
    seen_urls = set()
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(").,;")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        ln = line_of(text, m.start())
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line_text = text[line_start:(line_end if line_end != -1 else len(text))]
        if EXAMPLE_LINE_RE.search(line_text):
            continue
        alive, err = check_http(url)
        findings.append({
            "kind": "endpoint", "route": url,
            "status": "alive" if alive else "down",
            "file": path, "line": ln,
            "reason": None if alive else (err or "unreachable"),
        })

    # 3. first tokens of command lines inside fenced code blocks.
    # Fences are paired sequentially (open -> next close), not with a
    # DOTALL regex: an unanchored "```lang\n...```" match desyncs the
    # moment two fences of different kinds are adjacent, silently
    # swallowing real prose as "command lines".
    #
    # Fix-round-1 rule 1: only bash/sh/zsh/shell/console fences are
    # scanned — never unlabelled ones, which skills use for directory
    # trees, YAML-ish specs, and templated prose. A token is checked as a
    # command only when it contains no "/" and no file extension (those
    # are source files or paths mentioned in a snippet, e.g. server.mjs,
    # public/index.html, scripts/init_skill.py — not commands to
    # `command -v`), matches ^[a-z][a-z0-9_-]*$, and isn't a known prose
    # word.
    #
    # Fix-round-2 rule 4: bundled/vendored skills (plugin cache, synced
    # anthropic skills, Codex .system skills) document optional tools
    # (qpdf, pdftk, markitdown) that are install-if-you-need-them, not a
    # laptop documentation bug — skip command checks entirely for them.
    seen_cmds = set()
    lines = text.split("\n") if not bundled else []
    i = 0
    n = len(lines)
    while i < n:
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        lang = m.group(1).lower()
        start_line_no = i + 2  # 1-indexed line number of first body line
        body_lines = []
        j = i + 1
        while j < n and lines[j].strip() != "```":
            body_lines.append(lines[j])
            j += 1
        # j is the closing fence (or EOF if unterminated); resume after it
        i = j + 1
        if lang not in COMMAND_FENCE_LANGS:
            continue
        for k, raw_line in enumerate(body_lines):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # strip a leading shell prompt marker if present
            stripped = stripped.lstrip("$ ").strip()
            if not stripped:
                continue
            tok = stripped.split()[0]
            # strip common wrapper punctuation
            tok = tok.strip("`\"'()")
            if not tok or tok in SKIP_TOKENS:
                continue
            if tok.startswith(("<", "*", "$", "{", "#", "-")):
                continue
            if PATH_LIKE_TOKEN_RE.search(tok):
                continue  # a path or a source file, not a command
            tok_lower = tok.lower()
            if tok_lower in PROSE_STOPLIST:
                continue
            if not COMMAND_SHAPE_RE.match(tok):
                continue  # not ^[a-z][a-z0-9_-]*$: glyph, pipe, Capitalized, etc.
            if tok in seen_cmds:
                continue
            seen_cmds.add(tok)
            ln = start_line_no + k
            if check_command(tok):
                continue
            findings.append({
                "kind": "command", "route": tok, "status": "dead",
                "file": path, "line": ln, "reason": "command not found",
            })

    # 4. absolute or ~ paths mentioned anywhere. Fix-round-1 rule 2: only
    # a leading segment from REAL_PATH_PREFIXES (or a bare "~/...") is a
    # real, checkable machine path. Any other leading-"/" string
    # (/mod/ui/, /api/health, /demo/) is a URL path documented in prose,
    # not a filesystem route, so it's skipped rather than flagged dead.
    seen_paths = set()
    for m in ABS_PATH_RE.finditer(text):
        p = m.group(0)
        if any(c in p for c in "<*${"):
            continue
        if PLACEHOLDER_PATH_RE.search(p) or TMP_PATH_RE.match(p):
            continue
        if not (p.startswith("~/") or p == "~" or p.startswith(REAL_PATH_PREFIXES)):
            continue
        if p in seen_paths:
            continue
        # trim trailing punctuation that isn't part of the path
        p = p.rstrip(".,;:)\"'`")
        if not p or p in seen_paths:
            continue
        seen_paths.add(p)
        expanded = os.path.expanduser(p)
        if path_exists_with_applications_fallback(expanded, p):
            continue
        # Skip pure directory-looking fragments too short to be meaningful
        if len(p) < 3:
            continue
        ln = line_of(text, m.start())
        findings.append({
            "kind": "path", "route": p, "status": "dead",
            "file": path, "line": ln, "reason": "path does not exist",
        })


def launchctl_status(label):
    """Return last exit status for a loaded label, or None if not loaded."""
    try:
        r = subprocess.run(["launchctl", "list", label],
                            capture_output=True, timeout=5, text=True)
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith('"LastExitStatus"'):
                m = re.search(r'=\s*(-?\d+)', line)
                if m:
                    return int(m.group(1))
        return None
    except Exception:
        return None


def scan_launch_agents(findings):
    if not os.path.isdir(LAUNCH_AGENTS_DIR):
        return
    for name in sorted(os.listdir(LAUNCH_AGENTS_DIR)):
        if not (name.startswith("com.siso.") and name.endswith(".plist")):
            continue
        path = os.path.join(LAUNCH_AGENTS_DIR, name)
        try:
            with open(path, "rb") as fh:
                plist = plistlib.load(fh)
        except Exception as e:
            findings.append({
                "kind": "launchagent", "route": name, "status": "dead",
                "file": path, "line": 1, "reason": f"unparsable plist: {e}",
            })
            continue

        label = plist.get("Label", name)
        args = plist.get("ProgramArguments") or []
        prog = plist.get("Program")

        exe = args[0] if args else prog
        if exe:
            expanded = os.path.expanduser(exe)
            exists = os.path.exists(expanded) or (
                subprocess.run(["zsh", "-lc", f"command -v {exe!r}"],
                                capture_output=True, timeout=5).returncode == 0
            )
            if not exists:
                findings.append({
                    "kind": "launchagent", "route": f"{label}:{exe}",
                    "status": "dead", "file": path, "line": 1,
                    "reason": "ProgramArguments[0] does not exist",
                })

        exit_status = launchctl_status(label)
        if exit_status is not None and exit_status != 0:
            findings.append({
                "kind": "launchagent", "route": f"{label}:exit={exit_status}",
                "status": "dead", "file": path, "line": 1,
                "reason": f"loaded with non-zero last exit status ({exit_status})",
            })

        # probe any localhost URL in the plist (args + raw plist text)
        raw_blobs = args + ([prog] if prog else [])
        try:
            with open(path, "r", errors="replace") as fh:
                raw_blobs.append(fh.read())
        except OSError:
            pass
        seen = set()
        for blob in raw_blobs:
            if not isinstance(blob, str):
                continue
            for m in URL_RE.finditer(blob):
                url = m.group(0).rstrip(").,;<")
                if url in seen:
                    continue
                seen.add(url)
                alive, err = check_http(url)
                findings.append({
                    "kind": "launchagent_endpoint", "route": url,
                    "status": "alive" if alive else "down",
                    "file": path, "line": 1,
                    "reason": None if alive else (err or "unreachable"),
                })


def run():
    findings = []
    for skill_md in find_skill_md_files():
        scan_skill_file(skill_md, findings)
    scan_launch_agents(findings)
    return findings


def render_human(findings):
    dead = [f for f in findings if f["status"] == "dead"]
    down = [f for f in findings if f["status"] == "down"]
    rows = []
    header = ("KIND", "ROUTE", "STATUS", "FILE:LINE")
    rows.append(header)
    for f in findings:
        loc = f"{f['file']}:{f['line']}"
        rows.append((f["kind"], f["route"][:60], f["status"], loc))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    lines = []
    for i, r in enumerate(rows):
        line = "  ".join(r[c].ljust(widths[c]) for c in range(4))
        lines.append(line)
        if i == 0:
            lines.append("  ".join("-" * widths[c] for c in range(4)))
    lines.append("")
    lines.append(
        f"{len(dead)} dead route(s), {len(down)} down (informational) "
        f"of {len(findings)} checked."
    )
    return "\n".join(lines)


def main():
    as_json = "--json" in sys.argv[1:]
    findings = run()
    dead = [f for f in findings if f["status"] == "dead"]
    down = [f for f in findings if f["status"] == "down"]
    if as_json:
        print(json.dumps({
            "findings": findings,
            "dead_count": len(dead),
            "down_count": len(down),
            "total_count": len(findings),
        }, indent=2))
    else:
        print(render_human(findings))
    # Fix-round-1 rule 3: exit 1 only for "dead" findings (missing
    # subagent type, missing absolute path, missing command, failing
    # LaunchAgent); "down" alone (a refused local endpoint) exits 0.
    sys.exit(1 if dead else 0)


if __name__ == "__main__":
    main()
