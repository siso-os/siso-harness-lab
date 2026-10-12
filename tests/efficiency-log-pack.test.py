import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).parents[1] / "scripts/efficiency-log-pack.py"
spec = importlib.util.spec_from_file_location("pack", SCRIPT)
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


class LogPackTest(unittest.TestCase):
    def test_repeated_block_preserves_every_distinct_diagnostic(self):
        block = "ERROR HTTP 404 request 123 at a.ts:12\ncaused by missing route\n" * 8
        text = block + "ERROR HTTP 500 request 321 at b.ts:14\nnew cause\n" + block
        packed = pack.pack(text)
        self.assertLess(len(packed), len(text))
        self.assertEqual(pack.restore(packed), text)
        self.assertIn("HTTP 404", packed)
        self.assertIn("HTTP 500", packed)
        self.assertIn("new cause", packed)

    def test_no_gain_and_literal_markers_pass_through(self):
        for text in ("", "short\nshort\n", "[SISO repeat original lines 1-2]\n" * 20,
                     "ordinary SISO-LOG-PACK/1 literal\n" * 20):
            self.assertEqual(pack.pack(text), text)

    def test_unicode_crlf_unterminated_line_and_cli_roundtrip(self):
        text = ("WARNING λ request 999 at src/α.ts:23\r\n" * 25) + "final cause without newline"
        packed = subprocess.check_output([sys.executable, str(SCRIPT)], input=text.encode())
        restored = subprocess.check_output([sys.executable, str(SCRIPT), "--restore"], input=packed)
        self.assertEqual(restored, text.encode())

    def test_corruption_and_forward_references_rejected(self):
        packed = pack.pack("ERROR unique diagnostic at some-file.ts:321\n" * 30)
        self.assertRaises(ValueError, pack.restore, packed.replace("unique", "changed"))
        self.assertRaises(ValueError, pack.restore, packed.replace("original lines 1-", "original lines 999-"))

    def test_references_can_include_previously_restored_blocks(self):
        text = ("long diagnostic HTTP 404 at service/a.ts:123\n" * 10 + "second diagnostic HTTP 500 at service/b.ts:456\n") * 8
        self.assertEqual(pack.restore(pack.pack(text)), text)


if __name__ == "__main__":
    unittest.main()
