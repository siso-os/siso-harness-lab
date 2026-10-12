import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("replay", Path(__file__).parents[1] / "scripts/efficiency-replay.py")
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ReplayTest(unittest.TestCase):
    def test_distinct_status_codes_preserved(self):
        text = "ERROR request failed HTTP 404 at line 12\nERROR request failed HTTP 500 at line 14\n"
        result = replay.log_replay(text)
        self.assertEqual(result["before_chars"], result["after_chars"])
        self.assertEqual(result["duplicate_lines"], 0)

    def test_roundtrip_context_and_positions(self):
        error = "ERROR deeply nested request failed HTTP 500 at source.ts:123\n"
        result = replay.log_replay(error + "cause: connection reset\n" + error + "different cause\n" + error)
        self.assertTrue(result["roundtrip_pass"])
        self.assertEqual(result["duplicate_lines"], 2)
        self.assertLess(result["after_chars"], result["before_chars"])

    def test_numeric_ids_are_not_normalized(self):
        result = replay.log_replay("ERROR user 123 denied access to resource 456\nERROR user 321 denied access to resource 654\n")
        self.assertEqual(result["duplicate_lines"], 0)

    def test_marker_like_source_is_literal(self):
        result = replay.log_replay("[repeat of line 1]\nERROR one\n[repeat of line 1]\n")
        self.assertTrue(result["roundtrip_pass"])
        self.assertEqual(result["duplicate_lines"], 0)

    def test_images_are_not_text_tokens(self):
        self.assertEqual(replay.text_content([{"type": "image", "source": {"data": "A" * 10000}}, {"type": "text", "text": "ok"}]), "ok")

    def test_changed_bytes_and_ranges_not_deduped(self):
        pilot = replay.Replay()
        pilot.read(("a", 1, 50), "a" * 100)
        pilot.read(("a", 1, 50), "b" * 100)
        pilot.read(("a", 50, 100), "b" * 100)
        self.assertEqual(pilot.stats["identical_range_reads"], 0)

    def test_reset_prevents_stale_reference(self):
        pilot = replay.Replay()
        pilot.read(("a", 1, 50), "a" * 100)
        pilot.reset()
        pilot.read(("a", 1, 50), "a" * 100)
        self.assertEqual(pilot.stats["identical_range_reads"], 0)

    def test_private_and_mixed_store_refused(self):
        self.assertFalse(replay.project("/SISO_Workspace/personal/siso-harness-lab"))
        self.assertFalse(replay.safe("/tmp/fahmy-login"))
        with self.assertRaisesRegex(ValueError, "mixed/private"):
            replay.claude(Path.home() / ".claude/projects", "2026-10-04")

    def test_day_timezone(self):
        self.assertTrue(replay.on_day("2026-10-03T17:00:00Z", "2026-10-04"))
        self.assertFalse(replay.on_day("broken", "2026-10-04"))


if __name__ == "__main__":
    unittest.main()
