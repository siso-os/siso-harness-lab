import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("efficiency_context", Path(__file__).resolve().parents[1] / "scripts/efficiency-context.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ContextTest(unittest.TestCase):
    def test_observed_denominator_and_strict_threshold(self):
        rows = [{"context": 300000, "output": 10}, {"context": 300001, "output": 20}]
        self.assertEqual(module.number(rows), {"total_tokens": 600031, "above_tokens": 300021, "share_pct": 50.0009})

    def test_replay_changes_only_largest_contributor(self):
        rows = [{"cwd": cwd, "session": cwd, "at": str(i), "context": ctx, "output": 5}
                for i, (cwd, ctx) in enumerate((("owner", 470000), ("other", 310000), ("owner", 480000)))]
        result = module.report(rows)
        self.assertEqual(result["observed"]["above_tokens"], 1260015)
        self.assertEqual(result["largest_contributor"], "owner")
        self.assertEqual(result["replay"]["above_tokens"], 310005)
        self.assertEqual(result["replay"]["fresh_chats"], 1)
        self.assertFalse(result["handover"]["automatic_action"])

    def test_empty_and_invalid_policy(self):
        self.assertIsNone(module.report([])["observed"]["share_pct"])
        with self.assertRaises(ValueError):
            module.report([], threshold=300001)

    def test_private_and_mixed_stores_refused(self):
        for path in (module.HOME / ".claude/projects", module.HOME / ".claude-siso/projects", Path("/tmp/fahmy/projects")):
            with self.assertRaises(ValueError):
                module.calls(path, "2026-10-04")

    def test_parser_dedup_day_boundary_and_no_content_export(self):
        today = dt.datetime.now().astimezone()
        row = {"type": "assistant", "timestamp": today.isoformat(), "cwd": "/public/owner",
               "message": {"id": "m1", "model": "fixture-model", "content": "DO NOT EXPORT",
                           "usage": {"input_tokens": 1, "cache_read_input_tokens": 300000, "output_tokens": 3}}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "owner").mkdir()
            (root / "fahmy").mkdir()
            (root / "owner/one.jsonl").write_text("invalid\n" + json.dumps(row) + "\n" + json.dumps(row) + "\n")
            (root / "fahmy/private.jsonl").write_text("not read")
            rows = module.calls(root, today.date().isoformat())
            self.assertEqual(len(rows), 1)
            self.assertEqual(module.number(rows)["above_tokens"], 300004)
            self.assertNotIn("DO NOT EXPORT", json.dumps(rows))
            self.assertEqual(module.calls(root, (today - dt.timedelta(days=1)).date().isoformat()), [])

    def adoption_rows(self, session="old", context=470000):
        baseline = {"measured_at": "2026-10-04T05:25:00+07:00", "largest_contributor": "owner",
                    "contributors": [{"cwd": "owner", "latest_session": "old"}]}
        rows = [{"cwd": "owner", "session": session, "at": "2026-10-03T22:26:00+00:00",
                 "context": context, "output": 5}]
        return rows, baseline

    def test_adoption_uses_live_window_without_rewriting_daily_number(self):
        rows, baseline = self.adoption_rows()
        rows.insert(0, {**rows[0], "at": "2026-10-03T22:24:00+00:00", "context": 460000})
        original = module.number(rows)
        result = module.adoption(rows, baseline)
        self.assertEqual(result["status"], "no_fresh_owner_session")
        self.assertEqual(result["owner_calls_since"]["total_tokens"], 470005)
        self.assertEqual(module.number(rows), original)

    def test_fresh_session_observation_keeps_acceptance_unverified(self):
        rows, baseline = self.adoption_rows(session="fresh", context=60000)
        result = module.adoption(rows, baseline)
        self.assertEqual(result["status"], "fresh_session_observed_acceptance_unverified")
        self.assertEqual(result["all_calls_since"]["share_pct"], 0)
        self.assertFalse(result["useful_work_verified"])
        rows[0]["context"] = 60001
        self.assertEqual(module.adoption(rows, baseline)["status"], "fresh_boot_over_budget")

    def test_preexisting_different_session_and_nested_first_call_are_not_fresh_boot(self):
        rows, baseline = self.adoption_rows(session="different", context=35000)
        rows.insert(0, {**rows[0], "cwd": "nested", "at": "2026-10-03T22:24:00+00:00"})
        self.assertEqual(module.adoption(rows, baseline)["status"], "no_fresh_owner_session")

    def test_empty_window_and_invalid_baseline(self):
        rows, baseline = self.adoption_rows()
        self.assertEqual(module.adoption([], baseline)["status"], "no_new_owner_calls")
        self.assertIsNone(module.adoption([], baseline)["all_calls_since"]["share_pct"])
        for bad in ({}, {**baseline, "measured_at": "2026-10-04T05:25:00"}):
            with self.assertRaises(ValueError):
                module.adoption(rows, bad)

    def test_previous_day_resume_is_not_fresh(self):
        rows, baseline = self.adoption_rows(session="resumed", context=35000)
        rows[0]["session_first_call_at"] = "2026-10-02T22:00:00+00:00"
        self.assertEqual(module.adoption(rows, baseline)["status"], "no_fresh_owner_session")

    def test_parser_retains_session_origin_without_counting_yesterdays_tokens(self):
        today = dt.datetime.now().astimezone()
        row = {"type": "assistant", "timestamp": today.isoformat(), "cwd": "owner",
               "message": {"id": "today", "usage": {"input_tokens": 35}}}
        previous = {**row, "timestamp": (today - dt.timedelta(days=1)).isoformat(),
                    "message": {"id": "yesterday", "usage": {"input_tokens": 470000}}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "owner").mkdir()
            (root / "owner/resumed.jsonl").write_text(json.dumps(previous) + "\n" + json.dumps(row) + "\n")
            rows = module.calls(root, today.date().isoformat())
            self.assertEqual(module.number(rows)["total_tokens"], 35)
            self.assertEqual(dt.datetime.fromisoformat(rows[0]["session_first_call_at"]), today - dt.timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
