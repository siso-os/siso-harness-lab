"""Private kernel-lock fixtures: no existing job or pool is touched."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess as sp
import sys
import tempfile
import time
import unittest

SOURCE = str(Path(os.environ.get("HEAVY_SOURCE", Path(__file__).parents[1] / "bin/heavy")).resolve())
PAYLOAD = """import json,sys,time,pathlib
with open(sys.argv[1],'a') as f:f.write(json.dumps([sys.argv[2],'start',time.time()])+'\\n')
if sys.argv[5]:
 end=time.monotonic()+8
 while not pathlib.Path(sys.argv[5]).exists() and time.monotonic()<end:time.sleep(.005)
time.sleep(float(sys.argv[3]))
with open(sys.argv[1],'a') as f:f.write(json.dumps([sys.argv[2],'end',time.time()])+'\\n')
sys.exit(int(sys.argv[4]))
"""

class Heavy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="heavy-proof-")
        self.root = Path(self.tmp.name)
        self.log = self.root / "events"
        self.errpath = self.root / "stderr"
        self.err = self.errpath.open("w")
        self.env = {**os.environ, "HEAVY_DIR": str(self.root), "HEAVY_SLOTS": "1", "HEAVY_QOS": "off"}
        self.env.pop("SISO_HEAVY_LEASE", None)
        self.children = []

    def tearDown(self):
        # Release fixture barriers/holds even when an assertion fails. Only owned
        # payloads exist here; never send signals to another agent's process.
        (self.root / "go").touch()
        (self.root / "hold").unlink(missing_ok=True)
        for p in self.children:
            p.communicate(timeout=10)
        self.err.close()
        self.tmp.cleanup()

    def launch(self, argv, env=None, pass_fds=()):
        p = sp.Popen([sys.executable, "-B", SOURCE, "--", *argv], env=env or self.env,
                     stdout=sp.PIPE, stderr=self.err, text=True, pass_fds=pass_fds)
        self.children.append(p)
        return p

    def job(self, label, duration=.03, rc=0, env=None, gated=False):
        return self.launch([sys.executable, "-c", PAYLOAD, str(self.log), label, str(duration), str(rc),
                            str(self.root / "go") if gated else ""], env)

    def events(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def until(self, predicate, why):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(.005)
        self.fail(why + "\n" + self.errpath.read_text())

    def started(self, label):
        self.until(lambda: any(e[:2] == [label, "start"] for e in self.events()), "payload did not start: " + label)

    def waiting(self, p):
        self.until(lambda: any("waiting" in l and f"pid {p.pid}" in l for l in self.errpath.read_text().splitlines()), "no waiting diagnostic")

    def done(self, p, expected=0):
        out, _ = p.communicate(timeout=8)
        self.assertEqual(p.returncode, expected, out + self.errpath.read_text())
        return out

    def control(self, *args, expected=0):
        r = sp.run([sys.executable, "-B", SOURCE, *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, expected, r.stdout + r.stderr)
        return r

    def test_fifo_and_capacity(self):
        for slots in (1, 2):
            if slots == 2:
                # Distinct pool: capacity belongs to the root, not the caller.
                self.env["HEAVY_DIR"] = str(self.root / "second")
                self.env["HEAVY_SLOTS"] = "2"
                (self.root / "go").unlink()
            first = [self.job(f"{slots}-block-{i}", gated=True) for i in range(slots)]
            for i in range(slots):
                self.started(f"{slots}-block-{i}")
            rest = []
            for i in range(3):
                p = self.job(f"{slots}-wait-{i}", .07)
                self.waiting(p)
                rest.append(p)
            (self.root / "go").touch()
            for p in first + rest:
                self.done(p)
            pids = {p.pid for p in rest}
            admissions = [int(m[1]) for l in self.errpath.read_text().splitlines()
                          if (m := re.search(r"ticket (\d+) admitted .* pid (\d+)$", l)) and int(m[2]) in pids]
            self.assertEqual(admissions, list(range(slots + 1, slots + 4)))
            count = peak = 0
            for label, phase, _ in sorted(self.events(), key=lambda e:e[2]):
                if not label.startswith(f"{slots}-"):
                    continue
                count += 1 if phase == "start" else -1
                peak = max(count, peak)
            self.assertLessEqual(peak, slots)

    def test_hold_added_while_waiting(self):
        blocker = self.job("blocker", gated=True)
        self.started("blocker")
        waiter = self.job("held")
        self.waiting(waiter)
        self.control("--hold", "1", "fixture")
        (self.root / "go").touch()
        self.done(blocker)
        time.sleep(.3)
        self.assertFalse(any(e[:2] == ["held", "start"] for e in self.events()))
        self.control("--release")
        self.done(waiter)

    def test_naturally_exited_waiter_lease_is_pruned(self):
        self.control("--status")
        # A fixture actor registers under the real mutex then exits naturally,
        # leaving the same unlocked inode as a crashed waiter would leave.
        code = """import runpy,sys
m=runpy.run_path(sys.argv[1]);m['prepare']();m['register']()
"""
        r = sp.run([sys.executable, "-c", code, SOURCE], env=self.env, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list((self.root / "queue").glob("*.wait"))), 1)
        self.done(self.job("next"))
        self.assertEqual(list((self.root / "queue").glob("*.wait")), [])

    def test_exit_and_exec_failure_release_slot(self):
        self.done(self.job("seven", rc=7), 7)
        self.done(self.launch([str(self.root / "nonexistent-command")]), 127)
        self.done(self.job("next"))

    def test_nested_wrappers_fail_fast_with_and_without_fd(self):
        for close in (False, True):
            code = f"""import subprocess,sys
r=subprocess.run([sys.executable,'-B',sys.argv[1],'--',sys.executable,'-c','print(42)'],close_fds={close},capture_output=True,text=True)
print(r.stderr,end='');sys.exit(r.returncode)
"""
            out = self.done(self.launch([sys.executable, "-c", code, SOURCE]), 2)
            self.assertIn("nested heavy is not supported", out)
            self.assertNotIn("42", out)

    def test_unlocked_descriptor_cannot_bypass_hold(self):
        self.control("--hold", "1", "fixture")
        fd = os.open(self.root / "slots/slot-0.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            env = {**self.env, "SISO_HEAVY_LEASE": json.dumps({"root": str(self.root.resolve()), "slot": 0, "fd": fd})}
            out = self.done(self.launch([sys.executable, "-c", "print('UNSAFE')"], env, (fd,)), 2)
            self.assertNotIn("UNSAFE", out)
            self.assertFalse((self.root / "ticket").exists())
        finally:
            os.close(fd)

    def test_conflicting_capacity_rejected(self):
        blocker = self.job("blocker", gated=True)
        self.started("blocker")
        self.done(self.job("bypass", env={**self.env, "HEAVY_SLOTS": "2"}), 2)
        self.assertFalse(any(e[0] == "bypass" for e in self.events()))
        (self.root / "go").touch()
        self.done(blocker)

    def test_nonfinite_hold_rejected_without_overwrite(self):
        self.control("--hold", "1", "fixture")
        before = (self.root / "hold").read_bytes()
        for duration in ("nan", "inf", "-inf", "invalid"):
            self.control("--hold", duration, expected=2)
            self.assertEqual((self.root / "hold").read_bytes(), before)
        (self.root / "hold").write_text("nan\tinvalid")
        self.assertIn("unreadable hold", self.control("--status").stdout)

    def test_hold_expiry_and_unlocked_stale_ticket(self):
        self.control("--hold", "1", "fixture")
        (self.root / "hold").write_text(f"{time.time()-.1}\texpired")
        (self.root / "queue/00000000000000000001.wait").write_text("dead lease")
        self.done(self.job("ready"))
        self.assertEqual(list((self.root / "queue").glob("*.wait")), [])

if __name__ == "__main__":
    unittest.main()
