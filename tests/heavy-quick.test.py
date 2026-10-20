"""Quick-lane admission fixtures; every pool is private and barrier-driven."""
import fcntl
import json
import os
from pathlib import Path
import subprocess as sp
import sys
import tempfile
import time
import unittest

SOURCE = str(Path(os.environ.get("HEAVY_SOURCE", Path(__file__).parents[1] / "bin/heavy")).resolve())
PAYLOAD = """import json,sys,time,pathlib
log,label,gate=sys.argv[1:]
with open(log,'a') as f:f.write(json.dumps([label,'start',time.time()])+'\\n')
if gate:
    while not pathlib.Path(gate).exists(): time.sleep(.005)
with open(log,'a') as f:f.write(json.dumps([label,'end',time.time()])+'\\n')
"""


class QuickLane(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="heavy-quick-proof-")
        self.root = Path(self.tmp.name)
        self.log = self.root / "events"
        self.errpath = self.root / "stderr"
        self.err = self.errpath.open("w")
        self.env = {**os.environ, "HEAVY_DIR": str(self.root), "HEAVY_SLOTS": "3", "HEAVY_QOS": "off"}
        self.env.pop("SISO_HEAVY_LEASE", None)
        self.env.pop("HEAVY_CLASS", None)
        self.children = []
        self.gates = {self.root / "go"}

    def tearDown(self):
        for gate in self.gates:
            gate.touch()
        (self.root / "hold").unlink(missing_ok=True)
        for child in self.children:
            child.communicate(timeout=10)
        self.err.close()
        self.tmp.cleanup()

    def launch(self, label, class_name=None, *, env_class=None, gated=False, gate_path=None):
        env = dict(self.env)
        if env_class:
            env["HEAVY_CLASS"] = env_class
        prefix = ["--class", class_name] if class_name else []
        gate_file = gate_path or (self.root / "go" if gated else None)
        if gate_file:
            gate_file = Path(gate_file)
            self.gates.add(gate_file)
        gate = str(gate_file) if gate_file else ""
        args = [sys.executable, "-c", PAYLOAD, str(self.log), label, gate]
        p = sp.Popen([sys.executable, "-B", SOURCE, *prefix, "--", *args], env=env,
                     stdout=sp.PIPE, stderr=self.err, text=True)
        self.children.append(p)
        return p

    def launch_raw(self, args, *, env=None):
        p = sp.Popen([sys.executable, "-B", SOURCE, *args], env=env or self.env,
                     stdout=sp.PIPE, stderr=self.err, text=True)
        self.children.append(p)
        return p

    def control(self, *args, expected=0):
        result = sp.run([sys.executable, "-B", SOURCE, *args], env=self.env,
                        capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def lease_waiter(self, name, contents):
        path = self.root / "queue" / name
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, contents.encode())
        return path, fd

    def v1_quick_head(self):
        """Minimal pre-barrier class selector: only the exact quick suffix is quick."""
        for name in sorted(n for n in os.listdir(self.root / "queue") if n.endswith(".wait")):
            path = self.root / "queue" / name
            fd = os.open(path, os.O_RDWR)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    with open(path) as record:
                        if record.read().split()[-2:] == ["class", "quick"]:
                            return name
                else:
                    os.unlink(path)
            finally:
                os.close(fd)
        return None

    def legacy_head(self):
        """Minimal pre-lane global selector: first locked .wait file wins."""
        for name in sorted(n for n in os.listdir(self.root / "queue") if n.endswith(".wait")):
            path = self.root / "queue" / name
            fd = os.open(path, os.O_RDWR)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return name
                else:
                    os.unlink(path)
            finally:
                os.close(fd)
        return None

    def events(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def until(self, predicate, message):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.005)
        self.fail(message + "\n" + self.errpath.read_text())

    def started(self, label):
        self.until(lambda: any(e[:2] == [label, "start"] for e in self.events()),
                   "payload did not start: " + label)

    def waiting(self, process):
        self.until(lambda: any("waiting" in line and f"pid {process.pid}" in line
                               for line in self.errpath.read_text().splitlines()),
                   "process did not report waiting")

    def finish(self, process, expected=0):
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, expected, self.errpath.read_text())

    def starts(self, prefix):
        return [event[0] for event in self.events()
                if event[1] == "start" and event[0].startswith(prefix)]

    def admission_order(self, processes):
        labels = {process.pid: label for label, process in processes}
        order = []
        for line in self.errpath.read_text().splitlines():
            fields = line.split()
            if "admitted" not in fields or "pid" not in fields:
                continue
            pid = int(fields[fields.index("pid") + 1])
            if pid in labels:
                order.append(labels[pid])
        return order

    def peak(self):
        running = peak = 0
        for event in sorted(self.events(), key=lambda item: item[2]):
            running += 1 if event[1] == "start" else -1
            peak = max(peak, running)
        return peak

    def test_background_saturation_admits_quick_before_bulk_release(self):
        bulk = []
        for i in range(2):
            bulk.append(self.launch(f"bulk-holder-{i}", "bulk", gated=True))
            self.started(f"bulk-holder-{i}")
        quick = self.launch("quick", "quick", gated=True)
        self.started("quick")
        queued_bulk = self.launch("bulk-wait", "bulk")
        self.waiting(queued_bulk)
        (self.root / "go").touch()
        for process in bulk + [quick, queued_bulk]:
            self.finish(process)
        self.assertEqual(self.starts("bulk-holder-"), ["bulk-holder-0", "bulk-holder-1"])
        self.assertIn("quick", self.starts("quick"))

    def test_fifo_within_each_class_and_total_peak_cap(self):
        initial = [self.launch(f"initial-b{i}", "bulk", gated=True) for i in range(2)]
        initial.append(self.launch("initial-q", "quick", gated=True))
        for label in ["initial-b0", "initial-b1", "initial-q"]:
            self.started(label)
        waiters = [self.launch("bulk-a", "bulk")]
        self.waiting(waiters[-1])
        waiters.append(self.launch("bulk-b", "bulk"))
        self.waiting(waiters[-1])
        waiters.append(self.launch("quick-a", "quick"))
        self.waiting(waiters[-1])
        waiters.append(self.launch("quick-b", "quick"))
        for process in waiters:
            self.waiting(process)
        admission_pairs = [(label, process) for label, process in
                           [("bulk-a", waiters[0]), ("bulk-b", waiters[1]),
                            ("quick-a", waiters[2]), ("quick-b", waiters[3])]]
        (self.root / "go").touch()
        for process in initial + waiters:
            self.finish(process)
        self.assertEqual(self.peak(), 3)
        order = self.admission_order(admission_pairs)
        self.assertLess(order.index("bulk-a"), order.index("bulk-b"))
        self.assertLess(order.index("quick-a"), order.index("quick-b"))

    def test_hold_blocks_quick(self):
        self.control("--hold", "1", "fixture")
        quick = self.launch("held-quick", "quick")
        self.waiting(quick)
        time.sleep(.05)
        self.assertNotIn("held-quick", self.starts("held-"))
        self.control("--release")
        self.finish(quick)

    def test_quick_borrows_idle_bulk_capacity_without_bulk_waiters(self):
        first = self.launch("quick-holder", "quick", gated=True)
        self.started("quick-holder")
        second = self.launch("quick-borrower", "quick")
        self.started("quick-borrower")
        self.assertLessEqual(self.peak(), 3)
        (self.root / "go").touch()
        self.finish(first)
        self.finish(second)

    def test_queued_bulk_gets_freed_slot_before_quick_refill(self):
        release_quick = [self.root / f"release-quick-{i}" for i in range(2)]
        quick = []
        for i in range(2):
            quick.append(self.launch(f"quick-holder-{i}", "quick", gate_path=release_quick[i]))
            self.started(f"quick-holder-{i}")
        bulk_holder = self.launch("bulk-holder", "bulk", gated=True)
        self.started("bulk-holder")
        bulk_waiter = self.launch("bulk-waiter", "bulk", gated=True)
        self.waiting(bulk_waiter)
        quick_waiter = self.launch("quick-refill", "quick")
        self.waiting(quick_waiter)
        self.assertNotIn("quick-refill", self.starts("quick-refill"))

        release_quick[0].touch()
        self.started("bulk-waiter")
        self.assertLessEqual(self.peak(), 3)

        (self.root / "go").touch()
        release_quick[1].touch()
        for process in quick + [bulk_holder, bulk_waiter, quick_waiter]:
            self.finish(process)
        self.assertLess(self.starts("").index("bulk-waiter"), self.starts("").index("quick-refill"))
        self.assertEqual(self.peak(), 3)

    def test_quick_uses_free_low_slot_when_preferred_last_slot_is_legacy(self):
        self.control("--status")
        lock_path = self.root / "slots" / "slot-2.lock"
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            quick = self.launch("low-slot-quick", "quick")
            self.started("low-slot-quick")
            admissions = self.errpath.read_text()
            self.assertIn("admitted slot 0", admissions)
            self.finish(quick)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def test_invalid_class_rejected_before_payload(self):
        bad = self.launch("invalid", "sideways")
        self.finish(bad, 2)
        self.assertEqual(self.events(), [])

    def test_single_slot_is_global_fifo_across_classes(self):
        self.env["HEAVY_SLOTS"] = "1"
        blocker = self.launch("blocker", "bulk", gated=True)
        self.started("blocker")
        quick = self.launch("quick-after", "quick")
        self.waiting(quick)
        bulk = self.launch("bulk-after", "bulk")
        self.waiting(bulk)
        (self.root / "go").touch()
        for process in [blocker, quick, bulk]:
            self.finish(process)
        starts = self.starts("")
        self.assertLess(starts.index("quick-after"), starts.index("bulk-after"))

    def test_unknown_environment_class_rejected(self):
        bad = self.launch("invalid-env", env_class="sideways")
        self.finish(bad, 2)
        self.assertEqual(self.events(), [])

    def test_missing_class_argument_rejected(self):
        bad = self.launch_raw(["--class"])
        self.finish(bad, 2)
        self.assertEqual(self.events(), [])

    def test_legacy_missing_class_is_bulk_but_quick_lane_can_bypass(self):
        self.control("--status")
        queue = self.root / "queue" / "00000000000000000001.wait"
        fd = os.open(queue, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, b"pid 999 legacy waiter\n")
        try:
            quick = self.launch("legacy-quick", "quick")
            self.started("legacy-quick")
            bulk = self.launch("legacy-bulk", "bulk")
            self.waiting(bulk)
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            self.finish(quick)
            self.finish(bulk)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    def test_waiter_records_class_and_status_reports_reserved_lane(self):
        blockers = []
        for i in range(2):
            blockers.append(self.launch(f"status-blocker-{i}", "bulk", gated=True))
            self.started(f"status-blocker-{i}")
        quick_blocker = self.launch("status-quick-blocker", "quick", gated=True)
        self.started("status-quick-blocker")
        quick = self.launch("status-quick", env_class="quick")
        self.waiting(quick)
        records = list((self.root / "queue").glob("*.wait"))
        self.assertTrue(any("class quick" in record.read_text() for record in records))
        status = self.control("--status").stdout.lower()
        self.assertIn("reserved", status)
        self.assertIn("quick", status)
        (self.root / "go").touch()
        for blocker in blockers:
            self.finish(blocker)
        self.finish(quick_blocker)
        self.finish(quick)

    def test_live_quick_barrier_is_global_head_for_legacy_wrapper(self):
        self.control("--status")
        slots = []
        quick = None
        try:
            for slot in range(3):
                fd = os.open(self.root / "slots" / f"slot-{slot}.lock", os.O_RDWR | os.O_CREAT, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
                slots.append(fd)
            quick = self.launch("registered-quick", "quick")
            self.waiting(quick)
            barriers = list((self.root / "queue").glob("!*.wait"))
            tickets = list((self.root / "queue").glob("[0-9]*.wait"))
            self.assertEqual(len(barriers), 1)
            self.assertEqual(len(tickets), 1)
            self.assertEqual(self.legacy_head(), barriers[0].name)
            marker_fd = os.open(barriers[0], os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(marker_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(marker_fd)
        finally:
            for fd in slots:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        if quick is not None:
            self.finish(quick)

    def test_v1_quick_fifo_skips_barrier_without_prefix_deadlock(self):
        self.control("--status")
        early, early_fd = self.lease_waiter("00000000000000000001.wait", "pid 1 registered 1 class quick\n")
        try:
            later = self.launch("registered-later-quick", "quick")
            self.waiting(later)
            barriers = list((self.root / "queue").glob("!*.wait"))
            self.assertEqual(len(barriers), 1)
            self.assertEqual(self.v1_quick_head(), early.name)
            self.assertNotEqual(self.v1_quick_head(), barriers[0].name)
            fcntl.flock(early_fd, fcntl.LOCK_UN)
            os.close(early_fd)
            self.finish(later)
        finally:
            try:
                os.close(early_fd)
            except OSError:
                pass

    def test_status_excludes_live_barrier_from_waiter_counts(self):
        self.control("--status")
        barrier, fd = self.lease_waiter("!00000000000000000001.wait", "pid 1 class barrier\n")
        try:
            status = self.control("--status").stdout.lower()
            self.assertIn("0 registered waiters", status)
            self.assertIn("0 quick / 0 bulk waiting", status)
            self.assertTrue(barrier.exists())
        finally:
            os.close(fd)

    def test_status_prunes_unleased_stale_barrier(self):
        self.control("--status")
        barrier = self.root / "queue" / "!00000000000000000001.wait"
        barrier.write_text("pid 999 class barrier\n")
        status = self.control("--status").stdout.lower()
        self.assertIn("0 registered waiters", status)
        self.assertFalse(barrier.exists())


if __name__ == "__main__":
    unittest.main()
