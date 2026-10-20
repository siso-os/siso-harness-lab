import fcntl
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
import retention

DAY = 86400
GIB = retention.GIB
NOW = 1_800_000_000.0


def make(root, rel, age_days, gib):
    p = Path(root) / rel
    (p / '.git').mkdir(parents=True)
    for q in (p / '.git', p):
        os.utime(q, (NOW - age_days * DAY,) * 2)
    SIZES[str(p)] = gib * GIB
    return p


SIZES = {}


class Retention(unittest.TestCase):
    def setUp(self):
        SIZES.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.logs = []

    def tearDown(self):
        self.tmp.cleanup()

    def run_prune(self, free, dry_run=True, days=2, processes='', **kw):
        state = {'free': free * GIB}

        def remove(path):
            state['free'] += SIZES[str(path)]
            import shutil
            shutil.rmtree(path)

        return retention.prune(self.root, 25, 5, days, dry_run=dry_run, free_fn=lambda: state['free'], now=NOW,
                               log=lambda *a: self.logs.append(' '.join(map(str, a))), processes=processes,
                               size_fn=lambda p: SIZES[str(p)], remove_fn=remove, pnpm=False, **kw)

    def test_nothing_when_above_floor(self):
        make(self.root, 'workers/mini-0/clones/o/r', 9, 10)
        self.assertEqual(self.run_prune(30), [])
        self.assertEqual(self.logs, [])

    def test_oldest_first_until_floor_plus_margin(self):
        a = make(self.root, 'workers/mini-0/clones/o/old', 9, 4)
        b = make(self.root, 'workers/mini-1/clones/o/mid', 5, 4)
        c = make(self.root, 'workers/mini-1/clones/o/new', 3, 4)
        picked = self.run_prune(18)  # needs 12 GiB more to reach 30: a, b and c
        self.assertEqual(picked, [str(a), str(b), str(c)])
        picked = self.run_prune(22)  # needs 8: the two oldest
        self.assertEqual(picked, [str(a), str(b)])
        picked = self.run_prune(26 - 1.5)  # needs 5.5: still the two oldest, never the newest
        self.assertEqual(picked, [str(a), str(b)])

    def test_recent_units_are_kept(self):
        make(self.root, 'workers/mini-0/clones/o/fresh', 1.5, 20)
        old = make(self.root, 'workers/mini-0/clones/o/old', 2.5, 1)
        self.assertEqual(self.run_prune(10), [str(old)])
        self.assertEqual(self.run_prune(10, days=1), [str(old), str(self.root / 'workers/mini-0/clones/o/fresh')])

    def test_held_lock_and_running_process_are_skipped(self):
        locked = make(self.root, 'workers/mini-0/clones/o/r', 9, 5)
        (self.root / 'workers/mini-0/worker.lock').touch()
        free = make(self.root, 'workers/mini-1/clones/o/r', 8, 5)
        running = make(self.root, 'trains/o/r/main/clones', 7, 5)
        (running.parent / 'train.lock').touch()
        with open(self.root / 'workers/mini-0/worker.lock', 'a') as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            picked = self.run_prune(1, processes=f'npm test GIT_DIR={running}/x')
        self.assertEqual(picked, [str(free)])
        self.assertTrue(locked.exists() and running.exists())

    def test_unreadable_process_list_means_busy(self):
        make(self.root, 'workers/mini-0/clones/o/r', 9, 5)
        self.assertEqual(self.run_prune(1, processes=None), [])

    def test_only_listed_units_and_receipts_stay(self):
        keep = self.root / 'workers/mini-0/state.json'
        keep.parent.mkdir(parents=True)
        keep.write_text('{}')
        (self.root / 'tmp/x').mkdir(parents=True)
        (self.root / 'trains/o/r/main').mkdir(parents=True)
        (self.root / 'trains/o/r/main/deployed.json').write_text('{}')
        rec = make(self.root, 'recovery/r/red-main-1/checkout', 9, 2)
        (rec.parent / 'probe.json').write_text('{}')
        manual = make(self.root, 'workers/manual-5', 9, 2)
        picked = self.run_prune(1, dry_run=False)
        self.assertCountEqual(picked, [str(rec), str(manual)])
        self.assertFalse(rec.exists() or manual.exists())
        self.assertTrue(keep.exists() and (rec.parent / 'probe.json').exists() and (self.root / 'tmp/x').exists())
        self.assertTrue((self.root / 'trains/o/r/main/deployed.json').exists())

    def test_symlink_unit_is_never_followed(self):
        outside = Path(self.tmp.name + '-outside')
        (outside / '.git').mkdir(parents=True)
        (self.root / 'workers/mini-0/clones/o').mkdir(parents=True)
        os.symlink(outside, self.root / 'workers/mini-0/clones/o/r')
        self.assertEqual(self.run_prune(1, dry_run=False), [])
        self.assertTrue(outside.exists())
        import shutil
        shutil.rmtree(outside)

    def test_dry_run_removes_nothing(self):
        a = make(self.root, 'workers/mini-0/clones/o/r', 9, 10)
        self.assertEqual(self.run_prune(10), [str(a)])
        self.assertTrue(a.exists())
        self.assertTrue(any('would remove' in l for l in self.logs))


if __name__ == '__main__':
    unittest.main()
