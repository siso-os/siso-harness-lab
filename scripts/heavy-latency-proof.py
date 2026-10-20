#!/usr/bin/env python3
"""Measure quick-command latency in repeatable private three-slot fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

BG = """import json,pathlib,sys,time
events,label,gate=sys.argv[1:]
def mark(phase):
 with open(events,'a') as f:f.write(json.dumps([label,phase,time.time()])+'\\n')
mark('start')
while not pathlib.Path(gate).exists(): time.sleep(.005)
t=time.monotonic(); time.sleep(.025); elapsed=time.monotonic()-t
mark('end')
print(json.dumps({'payload_execution_seconds':elapsed}))
"""
QUICK = """import json,sys,time
events=sys.argv[1]; label='quick'
def mark(phase):
 with open(events,'a') as f:f.write(json.dumps([label,phase,time.time()])+'\\n')
mark('start')
t=time.monotonic(); x=sum(i*i for i in range(20000)); elapsed=time.monotonic()-t
mark('end')
print(json.dumps({'check':x==2666466670000,'payload_execution_seconds':elapsed}))
"""


def wait_until(predicate, deadline, why):
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    raise RuntimeError("fixture setup failed: " + why)


def run_trial(label, source, quick_class):
    source = Path(source).resolve()
    with tempfile.TemporaryDirectory(prefix="heavy-latency-proof-") as tmp:
        root = Path(tmp)
        events, gate = root / "events.jsonl", root / "release"
        env = dict(os.environ, HEAVY_DIR=str(root / "pool"), HEAVY_SLOTS="3", HEAVY_QOS="off")
        env.pop("SISO_HEAVY_LEASE", None)
        env.pop("HEAVY_CLASS", None)
        owned, handles = [], []

        def launch(name, args, stderr):
            p = subprocess.Popen([sys.executable, "-B", str(source), *args], env=env,
                                 stdout=subprocess.PIPE, stderr=stderr, text=True,
                                 start_new_session=True)
            owned.append((name, p))
            return p

        def event_count(phase):
            return sum(json.loads(line)[1] == phase for line in events.read_text().splitlines()) if events.exists() else 0

        def diagnostic(i):
            return (root / f"bulk-{i}.stderr").read_text() if (root / f"bulk-{i}.stderr").exists() else ""

        timer = None
        try:
            for i in range(3):
                err = (root / f"bulk-{i}.stderr").open("w+"); handles.append(err)
                cls = ["--class", "bulk"] if quick_class else []
                launch(f"bulk-{i}", [*cls, "--", sys.executable, "-c", BG,
                                     str(events), f"bulk-{i}", str(gate)], err)
                if i < 2 or not quick_class:
                    wait_until(lambda: event_count("start") == i + 1,
                               time.monotonic() + 3, f"bulk-{i} did not start")
                else:
                    wait_until(lambda: "waiting for admission" in diagnostic(i),
                               time.monotonic() + 3, f"bulk-{i} did not queue")
            expected_active = 2 if quick_class else 3
            if event_count("start") != expected_active:
                raise RuntimeError("fixture setup failed: active bulk count mismatch")

            requested = time.monotonic()
            qerr = (root / "quick.stderr").open("w+"); handles.append(qerr)
            cls = ["--class", "quick"] if quick_class else []
            q = launch("quick", [*cls, "--", sys.executable, "-c", QUICK, str(events)], qerr)
            timer = threading.Timer(5, gate.touch); timer.daemon = True; timer.start()
            out, _ = q.communicate(timeout=10)
            request_finish = time.monotonic() - requested
            qerr.flush(); qerr.seek(0); diag = qerr.read()
            admitted = re.search(r"admitted .* after ([0-9.]+)s", diag)
            quick = json.loads(out.strip())
            for _, p in owned:
                if p is not q:
                    p.wait(timeout=10)
            parsed = [json.loads(x) for x in events.read_text().splitlines()]
            running = peak = 0
            for _, phase, _ in sorted(parsed, key=lambda e: e[2]):
                running += 1 if phase == "start" else -1
                peak = max(peak, running)
            result = {"fixture": label, "source": str(source),
                      "request_to_finish_seconds": request_finish,
                      "admitted_wait_seconds": float(admitted.group(1)) if admitted else None,
                      "payload_execution_seconds": quick.get("payload_execution_seconds"),
                      "correct": q.returncode == 0 and quick.get("check") is True,
                      "exit_code": q.returncode, "max_concurrency": peak,
                      "waiting_diagnostics": [i for i in range(3) if "waiting for admission" in diagnostic(i)]}
            return result
        finally:
            if timer:
                timer.cancel()
            gate.touch()
            for _, p in owned:
                if p.poll() is None:
                    try: p.communicate(timeout=1)
                    except subprocess.TimeoutExpired:
                        os.killpg(p.pid, signal.SIGTERM)
            for _, p in owned:
                try: p.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL); p.communicate()
            for handle in handles:
                handle.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, help="baseline heavy executable path")
    parser.add_argument("--after", required=True, help="candidate heavy executable path")
    args = parser.parse_args()
    before = run_trial("baseline plain heavy", args.before, False)
    after = run_trial("candidate quick class", args.after, True)
    ratio = before["request_to_finish_seconds"] / after["request_to_finish_seconds"]
    ok = all(x["correct"] and x["max_concurrency"] <= 3 and x["admitted_wait_seconds"] is not None
             for x in (before, after))
    print(json.dumps({"scope": "scheduling fixture; not whole-laptop load",
                      "actual_payload_command": "python -c deterministic sum-of-squares check",
                      "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      "before": before, "after": after,
                      "request_latency_ratio_before_over_after": ratio,
                      "correct": ok}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError) as error:
        print(json.dumps({"correct": False, "error": str(error)}), file=sys.stderr)
        sys.exit(1)
