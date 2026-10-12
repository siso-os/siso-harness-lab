#!/usr/bin/env python3
"""Tests for scripts/stack-page.py — pure parsing and the collector wrapper.

No network, no herdr, no codex, no gh: every case here is a fixture string fed to a pure function, plus the
collector timeout/failure path. Run: python3 tests/test_stack_page.py
"""
import importlib.util
import json
import pathlib
import sys
import unittest

_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "stack-page.py"
_spec = importlib.util.spec_from_file_location("stack_page", _PATH)
stack_page = importlib.util.module_from_spec(_spec)
sys.modules["stack_page"] = stack_page
_spec.loader.exec_module(stack_page)


BACKLOG_FIXTURE = """# Backlog

## Open

| # | Item | Evidence | Instrument / proof | Effort | Blocked on |
|---|---|---|---|---|---|
| 26 | **Economical operating reset.** Diagnose September 6-8 evidence. | `.agents/EFFICIENCY.md` | offline checks | M | None |
| 1 | **safety-guard.mjs latency.** Fires on 81% of tool calls. | `14-hooks.md` #1-3 | `time` x3 | S | - |

- [ ] **SessionStart = routing** — a bullet, not a table row.

## Done

| Date | Item | Before -> after | Evidence |
|---|---|---|---|
| 2026-09-23 | #40 **project memory in every repo** | wrong -> correct | `quiz/` |
"""

HEDR_FIXTURE = json.dumps({
    "id": "cli:agent:list",
    "result": {"agents": [
        {"agent": "claude", "agent_status": "done", "cwd": "/Users/person"},
        {"agent": "claude", "agent_status": "working", "cwd": "/Users/person/SISO_Workspace",
         "name": "agent-stack"},
        {"agent": "codex", "agent_status": "idle", "cwd": "/tmp/wt", "name": "luna7-full-a1"},
        {"agent": "codex", "agent_status": "idle", "cwd": "/tmp/wt", "name": "luna7-full-a2"},
        {"agent": "omp", "agent_status": "working", "cwd": "/Users/person"},
    ]},
})

HEDR_NO_OWNER_FIXTURE = json.dumps({
    "id": "cli:agent:list",
    "result": {"agents": [
        {"agent": "codex", "agent_status": "idle", "cwd": "/tmp/wt", "name": "luna7-full-a1"},
    ]},
})

NODE_TEST_FIXTURE = """ok 36 - non-UI files never nudge
1..37
# tests 37
# suites 0
# pass 37
# fail 0
# cancelled 0
"""

CODEX_LISTING_FIXTURE = "instructions...\\n- a: x\\n- b: y\\n- a: z\\nvisible skills:\\n- c: w\\n"


class BacklogParsing(unittest.TestCase):
    def test_open_rows_take_number_and_bold_title(self):
        rows = stack_page.parse_backlog_open(BACKLOG_FIXTURE)
        self.assertEqual([r["n"] for r in rows], [26, 1])
        self.assertEqual(rows[0]["title"], "Economical operating reset.")
        self.assertEqual(rows[1]["title"], "safety-guard.mjs latency.")

    def test_bullets_and_done_rows_are_not_open_rows(self):
        rows = stack_page.parse_backlog_open(BACKLOG_FIXTURE)
        self.assertNotIn(40, [r["n"] for r in rows])
        self.assertEqual(len(rows), 2)

    def test_missing_open_section_gives_nothing(self):
        self.assertEqual(stack_page.parse_backlog_open("# Backlog\n\n## Done\n\n| 1 | **x** |\n"), [])


class HerdrParsing(unittest.TestCase):
    def test_owner_seat_found_with_state_and_cwd(self):
        parsed = stack_page.parse_herdr_agents(HEDR_FIXTURE)
        self.assertTrue(parsed["owner"]["found"])
        self.assertEqual(parsed["owner"]["state"], "working")
        self.assertEqual(parsed["owner"]["cwd"], "/Users/person/SISO_Workspace")
        self.assertEqual(parsed["total"], 5)
        self.assertEqual(parsed["by_harness"], {"claude": 2, "codex": 2, "omp": 1})
        self.assertEqual(parsed["by_status"], {"idle": 2, "done": 1, "working": 2})
        self.assertEqual(parsed["named"], ["agent-stack", "luna7-full-a1", "luna7-full-a2"])

    def test_owner_absent_is_not_running(self):
        parsed = stack_page.parse_herdr_agents(HEDR_NO_OWNER_FIXTURE)
        self.assertFalse(parsed["owner"]["found"])
        seat = stack_page.owner_seat(parsed, "2026-09-23 12:00")
        self.assertEqual(seat["name"], "agent-stack")
        self.assertEqual(seat["state"], "not running")

    def test_unavailable_agents_collector_still_yields_a_seat(self):
        seat = stack_page.owner_seat(stack_page.unavailable("herdr not on PATH"), "2026-09-23 12:00")
        self.assertEqual(seat["state"], "not running")
        self.assertIn("unavailable: herdr not on PATH", seat["last"]["what"])

    def test_counts_line_names_harness_and_status(self):
        line = stack_page.agent_counts_line(stack_page.parse_herdr_agents(HEDR_FIXTURE))
        self.assertIn("5 agents", line)
        self.assertIn("claude 2", line)
        self.assertIn("idle 2", line)


class NodeTestSummary(unittest.TestCase):
    def test_parses_pass_and_fail(self):
        self.assertEqual(stack_page.parse_node_test_summary(NODE_TEST_FIXTURE), {"pass": 37, "fail": 0})

    def test_reports_failures(self):
        text = "# pass 35\n# fail 2\n"
        self.assertEqual(stack_page.parse_node_test_summary(text), {"pass": 35, "fail": 2})

    def test_missing_counters_are_none_not_zero(self):
        self.assertEqual(stack_page.parse_node_test_summary("boom\n"), {"pass": None, "fail": None})


class CodexListing(unittest.TestCase):
    def test_counts_unique_names(self):
        self.assertEqual(stack_page.count_codex_listed(CODEX_LISTING_FIXTURE), 3)

    def test_empty_output_counts_zero(self):
        self.assertEqual(stack_page.count_codex_listed(""), 0)


class CorrectionsStats(unittest.TestCase):
    def test_median_uses_full_days_only(self):
        payload = {"total": 60, "per_day_rate": 20.0, "per_harness": {"claude": 60},
                   "per_day": {"2026-09-19": 10, "2026-09-20": 20, "2026-09-21": 30, "2026-09-22": 6}}
        stats = stack_page.corrections_stats(payload)
        self.assertEqual(stats["median_full_days"], 20)
        self.assertEqual(stats["days_full"], 3)
        self.assertEqual(stats["last_full_day"], {"day": "2026-09-21", "count": 30})
        self.assertEqual(stats["total"], 60)

    def test_single_day_has_no_full_day(self):
        stats = stack_page.corrections_stats({"total": 4, "per_day": {"2026-09-23": 4}})
        self.assertIsNone(stats["median_full_days"])
        self.assertIsNone(stats["last_full_day"])
        self.assertEqual(stats["mean_per_day"], 4.0)

    def test_odd_number_of_full_days_is_the_middle_value(self):
        payload = {"per_day": {"a": 1, "b": 9, "c": 5, "d": 100}}
        self.assertEqual(stack_page.corrections_stats(payload)["median_full_days"], 5)


class RepoSlug(unittest.TestCase):
    def test_scp_and_https_forms(self):
        self.assertEqual(stack_page.parse_repo_slug("git@github.com:sisodias/siso-agent-base.git"),
                         "sisodias/siso-agent-base")
        self.assertEqual(stack_page.parse_repo_slug("https://github.com/sisodias/siso-harness-lab.git"),
                         "sisodias/siso-harness-lab")
        self.assertEqual(stack_page.parse_repo_slug("https://github.com/sisodias/siso-harness-lab"),
                         "sisodias/siso-harness-lab")

    def test_non_github_remote_is_empty(self):
        self.assertEqual(stack_page.parse_repo_slug("/Users/person/local/only"), "")


class CollectorWrapper(unittest.TestCase):
    def test_raising_collector_is_unavailable_not_a_crash(self):
        results = {}
        res = stack_page.collect("boom", lambda: 1 / 0, 5, results)
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("division by zero", res["reason"])
        self.assertEqual(results["boom"], res)

    def test_overrunning_collector_times_out(self):
        import time
        res = stack_page.collect("slow", lambda: time.sleep(3), 0.2)
        self.assertEqual(res["status"], "unavailable")
        self.assertIn("timed out after 0.2s", res["reason"])

    def test_unavailable_reason_is_one_bounded_line(self):
        res = stack_page.unavailable("line one\nline two " + "x" * 400)
        self.assertEqual(res["reason"], stack_page.short_reason(res["reason"]))
        self.assertNotIn("\n", res["reason"])
        self.assertLessEqual(len(res["reason"]), 110)


class PageDataIntegrity(unittest.TestCase):
    """The composed page must carry the U4 sections, an owner seat and a nav of this page's own anchors."""

    def _data(self):
        res = {
            "repos": stack_page.ok(items=[{"repo": "sisodias/x", "url": "https://github.com/sisodias/x",
                                           "branch": "main", "head": "abc1234", "head_at": "2026-09-23 10:00",
                                           "private": True, "access": "0 dirty paths", "what": "<code>x</code>"}],
                                   missing=[]),
            "agents": stack_page.ok(**stack_page.parse_herdr_agents(HEDR_FIXTURE)),
            "check:brain": stack_page.ok(pass_=True, exit=0,
                                         cmd="node ~/SISO_Workspace/SISO_Agents/siso-harness-lab/brain/compose-brain.mjs --check",
                                         detail="up-to-date"),
            "check:tests": stack_page.ok(pass_=True, exit=0, cmd="node --test", detail="37 pass · 0 fail"),
            "check:requests": stack_page.ok(pass_=True, exit=0, cmd="python3 tests/test_siso_request.py",
                                            detail="13 tests, exit 0"),
            "check:routes": stack_page.ok(pass_=True, exit=0, cmd="python3 scripts/route_doctor.py --json",
                                          detail="0 dead · 0 down · 12 routes"),
            "skills": stack_page.ok(installed=48, names=[], codex=82, codex_cmd="codex debug prompt-input"),
            "brain": stack_page.ok(files={"claude": 5541, "codex": 4096, "omp": 4096},
                                   tokens={"claude": 1385, "codex": 1024, "omp": 1024}, missing=[]),
            "requests": stack_page.ok(open=[{"id": "R-0001", "what": "Skill packages"}], built=[], by_state={}, total=1,
                                      cmd="bin/siso-request list --all --json"),
            "backlog": stack_page.ok(items=[{"n": 26, "title": "Economical operating reset."}], count=1,
                                     href="https://github.com/sisodias/siso-harness-lab/blob/main/BACKLOG.md"),
            "corrections": stack_page.ok(**stack_page.corrections_stats(
                {"total": 60, "per_day_rate": 20.0, "per_day": {"a": 10, "b": 20}}, ), cmd=stack_page.CORRECTIONS_CMD,
                at="2026-09-23 10:19"),
            "timeline": stack_page.ok(events=[{"at": "2026-09-23 10:18", "lane": "commits", "label": "4415d04 · x",
                                               "iso": "2026-09-23T10:18:12+07:00"}], slug="sisodias/x"),
            "console": stack_page.ok(url="http://127.0.0.1:8891/", code=200),
            "docs": stack_page.ok(items=[{"path": "AGENTS.md", "href": "https://x", "what": "rules",
                                          "at": "2026-09-23 10:13"}], missing=[]),
        }
        return stack_page.build_page(res, "2026-09-23 12:00")

    def test_sections_cover_the_u4_template(self):
        data = self._data()
        for key in ("what", "map", "repos", "live", "seats", "landed", "left", "research", "docs", "timeline",
                    "links", "agent"):
            self.assertIn(key, data["sections"])
            self.assertTrue(data["sections"][key]["n"] and data["sections"][key]["title"])

    def test_landed_carries_the_four_check_receipts(self):
        facts = self._data()["landed"]["facts"]
        receipts = " ".join(f["receipt"] for f in facts)
        self.assertIn("compose-brain.mjs --check", receipts)
        self.assertIn("node --test", receipts)
        self.assertIn("route_doctor.py --json", receipts)

    def test_nav_destinations_are_this_page_anchors(self):
        data = self._data()
        anchors = {f"#{k}" for k in data["sections"]}
        for group in data["nav"]["groups"]:
            for dest in group["destinations"]:
                self.assertTrue(dest["href"].startswith("#"), dest)
                self.assertIn(dest["href"], anchors, dest)

    def test_failed_check_lands_in_left_not_landed(self):
        res = {"repos": stack_page.unavailable("git missing"), "agents": stack_page.unavailable("herdr missing"),
               "check:brain": stack_page.ok(pass_=False, exit=1, cmd="node brain --check", detail="stale"),
               "check:tests": stack_page.ok(pass_=True, exit=0, cmd="node --test", detail="37 pass · 0 fail"),
               "check:requests": stack_page.ok(pass_=False, exit=1, cmd="python3 tests/t.py", detail="exit 1"),
               "check:routes": stack_page.ok(pass_=True, exit=0, cmd="route_doctor.py", detail="0 dead · 0 down"),
               "skills": stack_page.unavailable("codex hung"), "brain": stack_page.unavailable("no files"),
               "requests": stack_page.unavailable("cli missing"), "backlog": stack_page.unavailable("no BACKLOG.md"),
               "corrections": stack_page.unavailable("no corrections-latest.json; run --refresh"),
               "timeline": stack_page.unavailable("git log gave nothing"), "console": stack_page.unavailable("refused"),
               "docs": stack_page.unavailable("none on disk")}
        data = stack_page.build_page(res, "2026-09-23 12:00")
        claims = " ".join(f["claim"] for f in data["landed"]["facts"])
        self.assertNotIn("stale", claims)
        left = " ".join(i["what"] for i in data["left"]["items"])
        self.assertIn("stale", left)
        self.assertIn("unavailable: git missing", " ".join(data["landed"]["limits"]))
        self.assertEqual(data["repos"], [])
        self.assertEqual(data["seats"][0]["state"], "not running")
        self.assertEqual(data["urls"][0]["code"], "unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
