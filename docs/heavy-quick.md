# Keep short checks out of the bulk queue

`heavy --class quick -- COMMAND` reserves capacity for a bounded foreground check.
`heavy -- COMMAND` remains the bulk path. `HEAVY_CLASS=quick|bulk` is equivalent;
invalid values fail before queue registration. A CLI class overrides the environment.
`heavy --help` and `heavy -h` return usage before pool setup or queue admission;
`heavy -- --help` keeps the payload boundary and runs the named command.

The same persistent pool and kernel slot locks enforce total capacity. With five
slots, at most four new bulk commands run concurrently. Quick commands can use
all idle slots while no bulk command is waiting. Once a bulk waiter arrives,
new quick commands stop borrowing until the running quick count is below one;
already running commands finish normally. This lets queued bulk work take the
next free capacity. A quick command prefers the last slot but may use any free slot. FIFO holds
within each class; a one-slot pool retains the original global FIFO. Holds apply
to both classes, and dead waiter leases are pruned before admission.

Use quick for a small targeted check whose duration and memory use are known.
Full builds, historical secret scans, watch servers, and large browser suites
belong on the bulk path, preferably in a verified Mini checkout. The scheduler
limits admitted commands, not every descendant thread or process they spawn.
There is no automatic command timeout or guess about arbitrary wrapper scripts.

New ordinary commands leave one command slot available even when quick is idle.
Quick commands can borrow unused bulk capacity without increasing the total cap.
The reservation trades up to one bulk slot for foreground response; it does not create more
CPU or memory. The OS resource cost of quick work still matters.

## Live upgrades

The executable may be replaced without restarting payloads. Existing holders and
waiters keep their locks and tickets. Records without a class are bulk; new
readers publish slot class metadata under the admission mutex. A new quick waiter
also owns a leased priority barrier that older global-FIFO wrappers see at their
queue head. This prevents them from refilling a newly freed slot ahead of quick
work. The actual quick ticket stays numeric so earlier class-aware wrappers keep
the same quick FIFO order. Dead barriers release and prune like other leases.
All five slots may still be occupied by existing payloads; a quick waiter needs
one of those jobs to finish. No active process is cancelled or reclassified.

`heavy --status` reports class queues and the reservation. Reverting the executable
restores the old FIFO policy while using the same lock pool; do not unlink a lock,
change capacity, or move an active pool directory to force an upgrade.

Remote calls accept `heavy --class quick --on mini --cwd ABS -- COMMAND`. Explicit
classes require the new version at the remote canonical heavy path. Calls without
an explicit class retain the prior transport protocol and never fall back locally.

## Evidence

Run `tests/heavy.test.py`, `tests/heavy-quick.test.py`, and
`tests/heavy-remote.test.py` on the Mini through its canonical heavy wrapper.
`scripts/heavy-latency-proof.py --before BASELINE --after CANDIDATE` compares the
same deterministic check under three gated background commands and a three-slot
private pool. Admission wait, payload execution, and request-to-finish are separate.
This is a scheduling fixture, not a whole-laptop speed or CPU saving claim.
