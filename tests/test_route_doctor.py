import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/route_doctor.py"


def load_module():
    """Import route_doctor.py as a plain module (not __main__), so its
    functions can be unit-tested directly without running main()."""
    spec = importlib.util.spec_from_file_location("route_doctor_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# A fixture SKILL.md with exactly one live route, one "down" route, and
# three dead ones:
#   - live: a real built-in subagent_type ("general-purpose")
#   - down: a localhost port nothing listens on (fake port) — fix-round-1
#     rule 3 demotes a refused local endpoint to informational "down", not
#     hard "dead", so this is no longer one of the three dead routes.
#   - dead: a command that does not exist on any machine (missing command)
#   - dead: a subagent_type that is neither built-in nor a real agent file
#           (missing agent type)
#   - dead: an absolute path under a REAL_PATH_PREFIXES prefix that does
#           not exist (missing path) — the third dead route, replacing the
#           fake-port case now that endpoints can't be "dead" at all.
#
# Plus fix-round-1 and fix-round-2 precision cases that must NOT be
# flagged dead:
#   - a URL-path string (/mod/ui/) — not a leading-REAL_PATH_PREFIXES path
#   - a relative file token inside an UNLABELLED fence — unlabelled fences
#     are never scanned for commands
#   - an endpoint on a line containing "e.g." — illustrative, not a claim
#   - fix-round-2 rule 1: an /opt/siso-* VPS path — /opt/ is no longer a
#     real, checkable prefix (only /opt/homebrew/ is)
FIXTURE_SKILL_MD = """---
name: fixture-skill
description: fixture for route_doctor tests
---

# Fixture skill

Delegates real work with `subagent_type:"general-purpose"` (live) and a
fake one with `subagent_type:"totally-fake-agent-9000"` (dead, no
~/.claude/agents/totally-fake-agent-9000.md).

Talks to a local service at http://127.0.0.1:59991/health (down, nothing
bound to that port right now — informational, not a documentation bug).

Reads its config from /Users/nobody-on-this-machine/config-9000.json
(dead, that absolute path does not exist).

The UI route is mounted at /mod/ui/ (a URL path, not a filesystem route —
must not be flagged dead even though nothing exists on disk at that name).

E.g. a dev server might run at http://127.0.0.1:59992 — illustrative only,
never actually claimed live, must not be flagged dead.

The pool VPS keeps its venv at /opt/siso-compute-pool/.venv/bin/python
(a remote-host path, not a laptop path — /opt/ is dropped from the real
path prefixes, must not be flagged dead even though nothing exists on
disk at that name locally).

```bash
this-command-does-not-exist-anywhere-9000 --flag
```

Directory layout for reference:

```
project/
  scripts/init_skill.py
  server.mjs
```
"""


class RouteDoctorFixtureTest(unittest.TestCase):
    def run_doctor(self, root, extra_args=None):
        argv = [str(SCRIPT)] + (extra_args or [])
        buf_out = io.StringIO()
        with patch("os.path.expanduser",
                    side_effect=lambda p: p.replace("~", str(root), 1) if p.startswith("~") else p), \
             patch.object(sys, "argv", argv), \
             contextlib.redirect_stdout(buf_out):
            try:
                runpy.run_path(str(SCRIPT), run_name="__main__")
                code = 0
            except SystemExit as e:
                code = e.code or 0
        return code, buf_out.getvalue()

    def make_fixture_root(self, directory):
        root = Path(directory)
        skills = root / ".claude" / "skills" / "fixture-skill"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(FIXTURE_SKILL_MD)
        # Empty agent roots / LaunchAgents dir so those scans are no-ops
        # and don't pick up anything from the real machine.
        (root / ".claude" / "agents").mkdir(parents=True)
        (root / ".agents" / "skills").mkdir(parents=True)
        (root / ".codex" / "skills").mkdir(parents=True)
        (root / "Library" / "LaunchAgents").mkdir(parents=True)
        return root

    def test_flags_exactly_the_three_dead_routes(self):
        with tempfile.TemporaryDirectory(prefix="route-doctor-fixture-") as directory:
            self.make_fixture_root(directory)
            code, out = self.run_doctor(Path(directory), ["--json"])

        self.assertEqual(code, 1, "exit code must be 1 when routes are dead")
        report = json.loads(out)
        findings = report["findings"]

        dead = {f["route"]: f for f in findings if f["status"] == "dead"}
        alive = {f["route"]: f for f in findings if f["status"] == "alive"}
        down = {f["route"]: f for f in findings if f["status"] == "down"}

        self.assertEqual(
            report["dead_count"], 3,
            f"expected exactly 3 dead routes, got {report['dead_count']}: {sorted(dead)}",
        )

        # The three dead ones, by exact route text.
        self.assertIn("this-command-does-not-exist-anywhere-9000", dead)
        self.assertEqual(
            dead["this-command-does-not-exist-anywhere-9000"]["kind"], "command"
        )

        self.assertIn("totally-fake-agent-9000", dead)
        self.assertEqual(
            dead["totally-fake-agent-9000"]["kind"], "subagent_type"
        )

        self.assertIn("/Users/nobody-on-this-machine/config-9000.json", dead)
        self.assertEqual(
            dead["/Users/nobody-on-this-machine/config-9000.json"]["kind"], "path"
        )

        # The live one must be recorded as alive, not silently dropped.
        self.assertIn("general-purpose", alive)
        self.assertEqual(alive["general-purpose"]["kind"], "subagent_type")

        # Fix-round-1 rule 3: the fake-port endpoint is refused right now,
        # which is informational ("down"), not a hard "dead" documentation
        # bug — it must NOT count toward dead_count or the exit code.
        self.assertIn("http://127.0.0.1:59991/health", down)
        self.assertEqual(down["http://127.0.0.1:59991/health"]["kind"], "endpoint")
        self.assertNotIn("http://127.0.0.1:59991/health", dead)

        # --- Fix-round-1 precision cases: must NOT be flagged dead. ---

        # Rule 2: /mod/ui/ has no REAL_PATH_PREFIXES leading segment, so
        # it's treated as a URL path, not a filesystem route, and never
        # appears as a dead "path" finding at all.
        self.assertNotIn("/mod/ui/", dead)
        path_kind_dead_routes = {r for r, f in dead.items() if f["kind"] == "path"}
        self.assertNotIn("/mod/ui/", path_kind_dead_routes)

        # Rule 1: scripts/init_skill.py and server.mjs sit inside an
        # UNLABELLED fence (the directory-layout block) and are never
        # scanned as commands at all — neither dead nor alive.
        self.assertNotIn("scripts/init_skill.py", dead)
        self.assertNotIn("scripts/init_skill.py", alive)
        self.assertNotIn("scripts/init_skill.py", down)
        self.assertNotIn("server.mjs", dead)
        self.assertNotIn("server.mjs", alive)
        self.assertNotIn("server.mjs", down)

        # Rule 3: the "e.g." endpoint is skipped outright (never probed,
        # never recorded at all) since it was never claimed live.
        self.assertNotIn("http://127.0.0.1:59992", dead)
        self.assertNotIn("http://127.0.0.1:59992", down)
        self.assertNotIn("http://127.0.0.1:59992", alive)

        # --- Fix-round-2 precision cases: must NOT be flagged dead. ---

        # Rule 1: /opt/ is dropped from REAL_PATH_PREFIXES (only
        # /opt/homebrew/ remains) — an /opt/siso-* VPS path is a
        # remote-host route, never checked/flagged on this laptop at all.
        vps_path = "/opt/siso-compute-pool/.venv/bin/python"
        self.assertNotIn(vps_path, dead)
        opt_dead_routes = {r for r, f in dead.items() if r.startswith("/opt/")}
        self.assertEqual(
            opt_dead_routes, set(),
            f"no /opt/ route should be flagged dead, got: {opt_dead_routes}",
        )

    def test_negative_control_a_fully_healthy_fixture_exits_zero(self):
        """No dead routes at all -> exit 0. This is the negative control:
        if the doctor is broken in the direction of over-flagging (e.g. it
        starts treating a live built-in subagent_type or a running server
        as dead), this test fails loudly instead of silently passing."""
        healthy_md = """---
name: healthy-fixture
description: every route here is real
---

Uses `subagent_type:"general-purpose"` only, and shells out to `python3 --version`.
"""
        with tempfile.TemporaryDirectory(prefix="route-doctor-healthy-") as directory:
            root = Path(directory)
            skills = root / ".claude" / "skills" / "healthy-fixture"
            skills.mkdir(parents=True)
            (skills / "SKILL.md").write_text(healthy_md)
            (root / ".claude" / "agents").mkdir(parents=True)
            (root / ".agents" / "skills").mkdir(parents=True)
            (root / ".codex" / "skills").mkdir(parents=True)
            (root / "Library" / "LaunchAgents").mkdir(parents=True)

            code, out = self.run_doctor(root, ["--json"])

        self.assertEqual(code, 0, f"expected exit 0 for an all-healthy fixture, got {code}: {out[:500]}")
        report = json.loads(out)
        self.assertEqual(report["dead_count"], 0)


class ApplicationsFallbackTest(unittest.TestCase):
    """Fix-round-2 rule 3, in isolation: ABS_PATH_RE truncates
    "/Applications/Cloudflare WARP.app/..." at the space, so the route
    text ends up as "/Applications/Cloudflare" — a name that never
    exists verbatim. Any real /Applications entry starting with the
    truncated name must count as alive. Uses a fake /Applications
    listing (patched) instead of depending on what's installed on this
    particular Mac."""

    def test_truncated_multiword_app_name_counts_alive_via_prefix_match(self):
        module = load_module()
        with patch.object(module, "_applications_listing_cache", None), \
             patch.object(module, "applications_listing",
                           return_value=["Cloudflare WARP.app", "Safari.app"]):
            self.assertTrue(
                module.path_exists_with_applications_fallback(
                    "/Applications/Cloudflare",  # truncated, does not exist verbatim
                    "/Applications/Cloudflare",
                )
            )

    def test_no_matching_prefix_is_not_alive(self):
        module = load_module()
        with patch.object(module, "_applications_listing_cache", None), \
             patch.object(module, "applications_listing",
                           return_value=["Safari.app"]):
            self.assertFalse(
                module.path_exists_with_applications_fallback(
                    "/Applications/TotallyMadeUpApp9000",
                    "/Applications/TotallyMadeUpApp9000",
                )
            )

    def test_non_applications_path_is_unaffected(self):
        module = load_module()
        with patch.object(module, "_applications_listing_cache", None), \
             patch.object(module, "applications_listing", return_value=[]):
            self.assertFalse(
                module.path_exists_with_applications_fallback(
                    "/opt/homebrew/definitely-not-here-9000",
                    "/opt/homebrew/definitely-not-here-9000",
                )
            )


class BundledSkillCommandSkipTest(unittest.TestCase):
    """Fix-round-2 rule 4, in isolation: command checks are skipped for
    skills under plugin-cache/synced/.system locations, but other checks
    (subagent_type, endpoint, path) still run for the same file."""

    def test_is_bundled_skill_path_matches_known_locations(self):
        module = load_module()
        home = "/Users/fixture"
        bundled_paths = [
            f"{home}/.claude/plugins/cache/some-marketplace/pdf/1.0.0/SKILL.md",
            f"{home}/.claude/skills/synced/uuid-a_uuid-b/pdf/SKILL.md",
            f"{home}/.codex/skills/.system/imagegen/SKILL.md",
        ]
        for p in bundled_paths:
            self.assertTrue(module.is_bundled_skill_path(p), p)

    def test_ordinary_user_skill_path_is_not_bundled(self):
        module = load_module()
        p = "/Users/fixture/.claude/skills/my-own-skill/SKILL.md"
        self.assertFalse(module.is_bundled_skill_path(p))

    def test_bundled_skill_command_is_never_flagged_dead_but_subagent_type_still_is(self):
        bundled_md = """---
name: bundled-fixture
description: a vendored skill documenting an optional tool
---

Optional: install `this-optional-tool-does-not-exist-9000` if you need PDF support.

Uses `subagent_type:"totally-fake-agent-in-bundled-skill-9000"` (still must be
flagged dead — only command checks are skipped for bundled skills).

```bash
this-optional-tool-does-not-exist-9000 --version
```
"""
        with tempfile.TemporaryDirectory(prefix="route-doctor-bundled-") as directory:
            root = Path(directory)
            # SKILL_ROOTS only walks .claude/skills, .agents/skills,
            # .codex/skills — the real bundled skills on this machine
            # today live under .claude/skills/synced/<uuid>/, which this
            # reproduces so find_skill_md_files() actually discovers it.
            skill_dir = root / ".claude" / "skills" / "synced" / "uuid-a_uuid-b" / "pdf"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(bundled_md)
            (root / ".claude" / "agents").mkdir(parents=True)
            (root / ".agents" / "skills").mkdir(parents=True)
            (root / ".codex" / "skills").mkdir(parents=True)
            (root / "Library" / "LaunchAgents").mkdir(parents=True)

            argv = [str(SCRIPT), "--json"]
            buf_out = io.StringIO()
            with patch("os.path.expanduser",
                        side_effect=lambda p: p.replace("~", str(root), 1) if p.startswith("~") else p), \
                 patch.object(sys, "argv", argv), \
                 contextlib.redirect_stdout(buf_out):
                try:
                    runpy.run_path(str(SCRIPT), run_name="__main__")
                    code = 0
                except SystemExit as e:
                    code = e.code or 0

        report = json.loads(buf_out.getvalue())
        dead = {f["route"]: f for f in report["findings"] if f["status"] == "dead"}

        self.assertNotIn("this-optional-tool-does-not-exist-9000", dead)
        self.assertIn("totally-fake-agent-in-bundled-skill-9000", dead)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
