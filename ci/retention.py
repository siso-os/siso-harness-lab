"""Disk retention for the CI work root: when free space is under the floor, remove regenerable CI clones.

Nothing here touches anything outside the work root. Only these units are ever candidates, oldest first:
  workers/<slot>/clones/<owner>/<repo>   a slot's warm clone and its node_modules
  workers/manual-<n>                     a `siso-ci pr` run's whole scratch dir
  trains/<owner>/<repo>/<branch>/{clones,cache}
  recovery/<repo>/<incident>/{checkout,cache}   (probe.json and lock stay: they are the receipt)
A unit is skipped while its owner lock is held or any process mentions its path, and while it was used within `days`.
"""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import time

GIB = 1024 ** 3


def units(root):
    root = Path(root)
    found = []  # (unit path, lock file that guards it)
    for slot in sorted(root.glob('workers/*')):
        if slot.is_symlink() or not slot.is_dir():
            continue
        lock = slot / 'worker.lock'
        if slot.name.startswith('manual-'):
            found.append((slot, lock))
            continue
        for repo in sorted(slot.glob('clones/*/*')):
            found.append((repo, lock))
    for kind in ('clones', 'cache'):
        for unit in sorted(root.glob(f'trains/*/*/*/*/{kind}')):
            found.append((unit, unit.parent / 'train.lock'))
    for kind in ('checkout', 'cache'):
        for unit in sorted(root.glob(f'recovery/*/*/{kind}')):
            found.append((unit, unit.parent / 'lock'))
    return [(p, l) for p, l in found if p.is_dir() and not p.is_symlink()]


def last_used(unit):
    """Newest mtime among the unit and the files git touches on every fetch or checkout."""
    unit = Path(unit)
    stamps = []
    for rel in ('', '.git', '.git/FETCH_HEAD', '.git/HEAD', '.git/index'):
        try:
            stamps.append((unit / rel).stat().st_mtime)
        except OSError:
            pass
    return max(stamps) if stamps else 0.0


def lock_held(lock):
    if not Path(lock).exists():
        return False
    with open(lock, 'a') as fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def running_commands():
    """Every process's command line and environment (own user), so a test run inside a clone is seen."""
    try:
        return subprocess.run(['ps', '-axwwE', '-o', 'command='], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def tree_bytes(path):
    total = 0
    for dirpath, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_blocks * 512
            except OSError:
                pass
    return total


def select(candidates, now, days, busy):
    """Pure selection: units not used for `days` days and not busy, oldest first. candidates = [(path, last_used)]."""
    cutoff = now - days * 86400
    old = [(used, str(path)) for path, used in candidates if used <= cutoff and not busy(path)]
    return [path for _, path in sorted(old)]


def prune(root, floor_gib=25, margin_gib=5, days=2, dry_run=False, free_fn=None, now=None, log=print,
          processes=..., size_fn=tree_bytes, remove_fn=shutil.rmtree, pnpm=True):
    # processes: the ps text; None means it could not be read (treated as busy); default reads it.
    """Return the list of removed (or, in dry-run, selected) unit paths."""
    root = Path(root).resolve()
    free_fn = free_fn or (lambda: shutil.disk_usage(root).free)
    now = time.time() if now is None else now
    free = free_fn()
    if free >= floor_gib * GIB:
        return []
    target = (floor_gib + margin_gib) * GIB
    log(f'retention: {free / GIB:.1f} GiB free, under the {floor_gib} GiB floor; pruning CI clones unused for {days}+ days'
        f' until {floor_gib + margin_gib} GiB{" (dry run)" if dry_run else ""}')
    text = running_commands() if processes is ... else processes
    locks = {}
    owner = {}
    used = {}
    for path, lock in units(root):
        locks[str(path)] = lock
        used[str(path)] = last_used(path)
    candidates = [(p, u) for p, u in used.items()]

    def busy(path):
        if str(path) in owner:
            return owner[str(path)]
        held = lock_held(locks[str(path)])
        # An unreadable process list is treated as busy: never guess.
        seen = text is None or str(path) in text
        owner[str(path)] = held or seen
        return owner[str(path)]

    removed = []
    simulated = free
    for path in select(candidates, now, days, busy):
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root) or resolved == root or Path(path).is_symlink():
            continue
        size = size_fn(path) if dry_run else 0
        if dry_run:
            simulated += size
        else:
            remove_fn(path)
        removed.append(path)
        age = (now - used[str(path)]) / 86400
        log(f'retention: {"would remove" if dry_run else "removed"} {path} (unused {age:.1f} d' +
            (f', {size / GIB:.1f} GiB)' if dry_run else ')'))
        if (simulated if dry_run else free_fn()) >= target:
            break
    if removed and not dry_run and pnpm and shutil.which('pnpm'):
        try:
            subprocess.run(['pnpm', 'store', 'prune'], capture_output=True, text=True, timeout=600)
            log('retention: pnpm store prune done')
        except (OSError, subprocess.SubprocessError) as e:
            log('retention: pnpm store prune failed:', type(e).__name__)
    now_free = simulated if dry_run else free_fn()
    log(f'retention: {len(removed)} unit(s) {"selected" if dry_run else "removed"}; {now_free / GIB:.1f} GiB free'
        f'{" (estimated)" if dry_run else ""}')
    return removed
