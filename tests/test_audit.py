import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit.py"
END = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
START = END - timedelta(days=1)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return END.astimezone(tz) if tz else END.replace(tzinfo=None)


def response(mid, at, tokens=7, tool="Read"):
    return {"type": "assistant", "timestamp": at, "message": {
        "id": mid, "model": "fixture-model", "usage": {"input_tokens": tokens},
        "content": [{"type": "tool_use", "id": mid + "-tool", "name": tool,
                     "input": {}}]}}


class AuditWindowTest(unittest.TestCase):
    def audit(self, transcripts):
        with tempfile.TemporaryDirectory(prefix="harness-audit-test-") as directory:
            root = Path(directory)
            project = root / ".claude/projects/fixture"
            project.mkdir(parents=True)
            (root / ".claude/skills").mkdir()
            (root / ".claude/history.jsonl").write_text("")
            for name, records in transcripts.items():
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
                os.utime(path, (END.timestamp(), END.timestamp()))
            output = root / "result.json"
            # Redirect this invocation's reads, without changing HOME or live files.
            with patch("os.path.expanduser", return_value=directory), \
                 patch("datetime.datetime", Clock), \
                 patch.object(sys, "argv", [str(SCRIPT), str(output), "1"]), \
                 contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(SCRIPT), run_name="__main__")
            return json.loads(output.read_text())

    def test_old_events_do_not_contaminate_active_or_global_metrics(self):
        old = (START - timedelta(days=2)).isoformat()
        current = (START + timedelta(hours=1)).isoformat()
        report = self.audit({
            "active.jsonl": [response("old", old, 100, "Skill"),
                             {"type": "user", "timestamp": old,
                              "message": {"content": "Stop doing that"}},
                             {"type": "system", "subtype": "compact_boundary",
                              "timestamp": old},
                             response("current", current),
                             {"type": "user", "timestamp": current,
                              "message": {"content": "Inspect the fixture"}}],
            "old-only.jsonl": [response("stale", old, 200, "Bash")],
        })
        self.assertEqual(report["assistant_turns"], 1)
        self.assertEqual(report["model_usage"]["fixture-model"]["input_tokens"], 7)
        self.assertEqual(report["model_usage"]["fixture-model"]["turns"], 1)
        self.assertEqual(report["sessions"], 1)
        self.assertEqual(report["top_tools"], [["Read", 1]])
        self.assertEqual(report["user_prompts"], 1)
        self.assertEqual(report["corrections"]["total"], 0)
        self.assertEqual(report["compaction"]["boundaries"], 0)

    def test_half_open_window_rejects_future_and_unplaceable_events(self):
        report = self.audit({"bounds.jsonl": [
            response("start", START.isoformat(), 13),
            response("end", END.isoformat(), 100),
            response("future", (END + timedelta(days=1)).isoformat(), 200),
            response("bad", "not-a-time", 300),
            response("missing", None, 400),
            response("naive", "2026-09-07T12:00:00", 500),
        ]})
        self.assertEqual(report["assistant_turns"], 1)
        self.assertEqual(report["model_usage"]["fixture-model"]["input_tokens"], 13)

    def test_streamed_message_usage_is_counted_once(self):
        current = (START + timedelta(hours=2)).isoformat()
        report = self.audit({"stream.jsonl": [
            response("same-message", current),
            response("same-message", current, tool="Glob"),
        ]})
        self.assertEqual(report["assistant_turns"], 1)
        self.assertEqual(report["model_usage"]["fixture-model"]["input_tokens"], 7)
        self.assertEqual(report["tool_uses"], 2)

    def test_child_returns_use_only_windowed_text(self):
        def child(at, text):
            return {"type": "assistant", "timestamp": at,
                    "message": {"content": [{"type": "text", "text": text}]}}
        current = (START + timedelta(hours=3)).isoformat()
        old = (START - timedelta(days=1)).isoformat()
        report = self.audit({
            "parent.jsonl": [response("parent", current)],
            "parent/subagents/current.jsonl": [
                child(old, "failed old return"), child(current, "ok " * 150),
                child(END.isoformat(), "failed future return")],
            "parent/subagents/old-only.jsonl": [child(old, "failed old return")],
        })
        self.assertEqual(report["agent"]["subagent_files"], 1)
        self.assertEqual(report["agent"]["subagent_final_under_300"], 0)
        self.assertEqual(report["agent"]["subagent_final_neg"], 0)

    def test_report_names_the_requested_window(self):
        report = self.audit({"empty.jsonl": []})
        self.assertEqual(report["window"], START.isoformat() + ".." + END.isoformat())
        self.assertEqual(report["assistant_turns"], 0)

    def test_held_out_offset_boundary_and_empty_current_child(self):
        # Added after the correction: timezone equivalence and a real empty return
        # must survive filtering. This hold-out is known after its first run.
        report = self.audit({
            "parent.jsonl": [
                response("before", "2026-09-07T06:59:59+07:00", 100),
                response("start", "2026-09-07T07:00:00+07:00", 19)],
            "parent/subagents/empty.jsonl": [{
                "type": "user", "timestamp": "2026-09-07T08:00:00+07:00",
                "message": {"content": "Fixture assignment"}}],
        })
        self.assertEqual(report["model_usage"]["fixture-model"]["input_tokens"], 19)
        self.assertEqual(report["agent"]["subagent_files"], 1)
        self.assertEqual(report["agent"]["subagent_final_under_300"], 1)


if __name__ == "__main__":
    unittest.main()
