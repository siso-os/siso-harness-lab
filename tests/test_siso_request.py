"""Tests for bin/siso-request — the capability request log.

Run: python3 tests/test_siso_request.py
Each test gets its own temp dir (via SISO_REQUESTS_FILE) and cleans it up.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "siso-request"


class SisoRequestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.log = self.root / "requests" / "requests.jsonl"
        self.env = dict(os.environ, SISO_REQUESTS_FILE=str(self.log), SISO_AGENT_NAME="tester")

    def cli(self, *args, **kwargs):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, env=self.env, cwd=str(self.root),
            timeout=kwargs.pop("timeout", 60),
        )

    def lines(self):
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]

    # -- add / list ------------------------------------------------------

    def test_add_then_list_shows_it(self):
        r = self.cli("add", "Telemetry rollup daemon", "--why", "stale dashboards", "--project", "harness")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.rstrip("\n").split("\n")
        self.assertEqual(len(out), 2, out)
        self.assertEqual(out[0], "R-0001 filed: Telemetry rollup daemon")
        self.assertIn("siso-request list --all", out[1])

        listed = self.cli("list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("R-0001", listed.stdout)
        self.assertIn("open", listed.stdout)
        self.assertIn("Telemetry rollup daemon", listed.stdout)
        self.assertIn("harness", listed.stdout)
        self.assertIn("tester", listed.stdout)

        event = self.lines()[0]
        self.assertEqual(event["id"], "R-0001")
        self.assertEqual(event["event"], "open")
        self.assertEqual(event["why"], "stale dashboards")
        self.assertEqual(event["by"], "tester")
        self.assertEqual(event["cwd"], str(self.root.resolve()))
        self.assertTrue(event["t"].endswith("Z"))

    def test_near_duplicate_exits_3_and_adds_nothing(self):
        self.cli("add", "Build a PDF table extractor", "--why", "reporting")
        dup = self.cli("add", "pdf table extractor tool", "--why", "reporting again")
        self.assertEqual(dup.returncode, 3, dup.stdout + dup.stderr)
        self.assertEqual(dup.stdout.strip(), "exists: R-0001 Build a PDF table extractor")
        self.assertEqual(len(self.lines()), 1)

    def test_force_adds_the_duplicate(self):
        self.cli("add", "Build a PDF table extractor", "--why", "reporting")
        self.cli("add", "pdf table extractor tool", "--why", "a")
        forced = self.cli("add", "pdf table extractor tool", "--why", "b", "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertIn("R-0002 filed:", forced.stdout)
        self.assertEqual([e["id"] for e in self.lines()], ["R-0001", "R-0002"])

    # -- built -----------------------------------------------------------

    def test_built_moves_out_of_default_list(self):
        self.cli("add", "Vector index pruner", "--why", "disk")
        built = self.cli("built", "R-0001", "--where", "skill://vector-prune")
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertEqual(built.stdout.strip(), "R-0001 built -> skill://vector-prune")

        default = self.cli("list")
        self.assertEqual(default.stdout.strip(), "no open requests")

        allc = self.cli("list", "--all")
        self.assertIn("R-0001", allc.stdout)
        self.assertIn("built", allc.stdout)
        self.assertIn("-> skill://vector-prune", allc.stdout)

    def test_built_unknown_id_exits_4(self):
        r = self.cli("built", "R-0042", "--where", "skill://nope")
        self.assertEqual(r.returncode, 4)
        self.assertIn("unknown id", r.stderr)
        self.assertEqual(self.lines(), [])

    def test_building_twice_exits_5(self):
        self.cli("add", "Chat transcript indexer", "--why", "search")
        self.cli("built", "R-0001", "--where", "skill://chat-index")
        again = self.cli("built", "R-0001", "--where", "skill://chat-index-2")
        self.assertEqual(again.returncode, 5, again.stdout + again.stderr)
        self.assertIn("already built", again.stderr)
        self.assertEqual(len(self.lines()), 2)

    # -- drop ------------------------------------------------------------

    def test_drop_hides_it_from_default_list(self):
        self.cli("add", "Desktop screenshot annotator", "--why", "reviews")
        drop = self.cli("drop", "R-0001", "--reason", "design-lab covers it")
        self.assertEqual(drop.returncode, 0, drop.stderr)
        self.assertEqual(self.cli("list").stdout.strip(), "no open requests")
        self.assertIn("design-lab covers it", self.cli("list", "--all").stdout)
        self.assertEqual(self.lines()[-1]["event"], "dropped")

    def test_drop_unknown_id_exits_4(self):
        r = self.cli("drop", "R-0009", "--reason", "nope")
        self.assertEqual(r.returncode, 4)
        self.assertIn("unknown id", r.stderr)

    # -- json / show -----------------------------------------------------

    def test_list_json_reports_states(self):
        self.cli("add", "Model routing table", "--why", "routing")
        self.cli("add", "Queue depth gauge", "--why", "metrics")
        self.cli("built", "R-0001", "--where", "bin/model-router")
        self.cli("drop", "R-0002", "--reason", "not needed")

        r = self.cli("list", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual([row["id"] for row in data], ["R-0001", "R-0002"])
        self.assertEqual([row["state"] for row in data], ["built", "dropped"])
        self.assertEqual(data[0]["where"], "bin/model-router")
        self.assertEqual(data[0]["what"], "Model routing table")
        self.assertEqual(data[1]["reason"], "not needed")

    def test_list_json_empty_is_empty_array(self):
        self.assertEqual(json.loads(self.cli("list", "--json").stdout), [])

    def test_show_lists_every_event(self):
        self.cli("add", "Capability registry search", "--why", "discovery")
        self.cli("built", "R-0001", "--where", "skill://registry", "--note", "shipped")

        text = self.cli("show", "R-0001").stdout
        self.assertIn("open", text)
        self.assertIn("skill://registry", text)
        self.assertIn("Capability registry search", text)

        events = json.loads(self.cli("show", "R-0001", "--json").stdout)
        self.assertEqual([e["event"] for e in events], ["open", "built"])
        self.assertEqual(events[1]["note"], "shipped")

        missing = self.cli("show", "R-0777")
        self.assertEqual(missing.returncode, 4)

    def test_help_works(self):
        r = self.cli("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("add", r.stdout)
        self.assertEqual(self.cli("built").returncode, 2)  # missing required args

    # -- concurrency -----------------------------------------------------

    def test_ten_parallel_adds_get_distinct_ids(self):
        nouns = ["kapok", "lumen", "myrrh", "nacre", "ocher",
                 "prism", "quill", "runic", "sable", "tapis"]
        procs = [
            subprocess.Popen(
                [sys.executable, str(SCRIPT), "add", "discuss %s ingestion" % n, "--why", "x"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env=self.env, cwd=str(self.root),
            )
            for n in nouns
        ]
        outs = [p.communicate(timeout=120) for p in procs]
        self.assertEqual([p.returncode for p in procs], [0] * 10, outs)

        events = self.lines()
        ids = [e["id"] for e in events]
        self.assertEqual(len(events), 10)
        self.assertEqual(sorted(ids), ["R-%04d" % i for i in range(1, 11)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
