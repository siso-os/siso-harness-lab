"""Bounded host slots, warm owned clones and fail-closed disk admission."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import fcntl
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tarfile
import time


def infrastructure_category(output):
    """Match diagnostic syntax, never bare marker words in test names/fixtures."""
    for line in re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', output).splitlines():
        line = line.strip()
        if re.match(r'^(?:ok |not ok |[✓✔✖×] |(?:# )?(?:Subtest|test):)', line):
            continue
        if re.search(r'(?:^|: )(?:OSError: )?\[Errno 28\] No space left on device', line, re.I):
            return 'disk-full'
        if re.match(r'^(?:npm (?:ERR!|error) code ENOSPC\b|Error: ENOSPC\b)', line):
            return 'disk-full'
        if re.match(r'^(?:npm (?:ERR!|error) code (?:ENOTFOUND|EAI_AGAIN)\b|Error: (?:getaddrinfo )?(?:ENOTFOUND|EAI_AGAIN)\b)', line):
            return 'network-resolution'
        if re.match(r'^(?:fatal: |error: |(?:sh|bash|git|tar|cp|write): ).*No space left on device', line, re.I):
            return 'disk-full'
    return None


@contextmanager
def lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as fd:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd.fileno()


def archive(path, destination):
    """Archive only CI-owned disposable content; verify bytes before retiring originals."""
    path, destination = Path(path), Path(destination)
    if path.is_symlink():
        raise RuntimeError('refusing symlink archive')
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / (path.name + '-' + str(time.time_ns()) + '.tar.gz')
    target.touch(mode=0o600)
    with tarfile.open(target, 'w:gz') as tf:
        tf.add(path, arcname=path.name)
    with tarfile.open(target) as tf:
        for member in tf.getmembers():
            if member.isfile():
                original = path.parent / member.name
                with original.open('rb') as src, tf.extractfile(member) as saved:
                    while True:
                        a, b = src.read(1024 * 1024), saved.read(1024 * 1024)
                        if a != b:
                            raise RuntimeError('archive verification failed')
                        if not a:
                            break
    # No shell deletion or following links; only the tree just archived and verified.
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return str(target)


def disk_guard(root, minimum_mb=2048):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    receipts = []
    archive_root = Path(os.environ.get('SISO_CI_ARCHIVE', str(root / '_archive')))
    archive_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free >= minimum_mb * 1024**2:
        return receipts
    # Only runner-owned, ignored build caches. Never operator worktrees, dependencies,
    # databases or global stores. Compression retains recoverability on the same disk.
    for repo in sorted(root.glob('clones/*/*')):
        if not (repo / '.git').exists():
            continue
        for rel in ('.cache', '.turbo', 'node_modules/.cache', 'v2/node_modules/.cache'):
            cache = repo / rel
            ignored = subprocess.run(['git', 'check-ignore', '-q', rel], cwd=repo).returncode == 0
            if cache.is_dir() and ignored and not cache.is_symlink():
                receipts.append(archive(cache, archive_root))
                if shutil.disk_usage(root).free >= minimum_mb * 1024**2:
                    return receipts
        listing = subprocess.check_output(['git', 'worktree', 'list', '--porcelain'], cwd=repo, text=True)
        default = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], cwd=repo, text=True, capture_output=True)
        if default.returncode == 0:
            for entry in listing.strip().split('\n\n'):
                fields = dict(line.split(' ', 1) for line in entry.splitlines() if ' ' in line)
                tree = Path(fields.get('worktree', '/'))
                if tree == repo or not tree.is_relative_to(root) or not fields.get('branch'):
                    continue
                clean = subprocess.check_output(['git', 'status', '--porcelain'], cwd=tree, text=True).strip() == ''
                merged = subprocess.run(['git', 'merge-base', '--is-ancestor', fields['HEAD'], default.stdout.strip()], cwd=repo).returncode == 0
                if clean and merged:
                    receipts.append(archive(tree, archive_root))
        # Git's prune removes stale registration records, never live worktree files.
        subprocess.run(['git', 'worktree', 'prune'], cwd=repo, check=True)
    if shutil.disk_usage(root).free < minimum_mb * 1024**2:
        raise RuntimeError('disk guard: insufficient free space after owned-cache archival')
    return receipts


def slots(config_path):
    cfg = json.loads(Path(config_path).read_text())
    local = cfg.get(socket.gethostname(), cfg['default'])
    answer = []
    for host in local['hosts']:
        if host.get('enabled', True):
            for n in range(host['workers']):
                answer.append({**host, 'slot': host['name'] + '-' + str(n)})
    if not answer:
        raise RuntimeError('no CI worker slots configured')
    return answer


def dispatch(jobs, hosts, script, root):
    """One sequential queue per slot; independent slots overlap without sharing a clone."""
    import queue
    pending = queue.Queue()
    for job in jobs:
        pending.put((job.get('enqueued_at', time.time()), job))
    def consume(host):
        results = []
        while True:
            try:
                enqueued, job = pending.get_nowait()
            except queue.Empty:
                return results
            if host.get('repos') and job['repo'] not in host['repos']:
                # Assign only supported jobs; coordinator filters host eligibility below.
                pending.put((enqueued, job))
                return results
            request = {**job, 'queue_wait_seconds': time.time() - enqueued,
                       'minimum_free_mb': host.get('minimum_free_mb', 2048)}
            if host.get('ssh'):
                request['_github_token'] = subprocess.check_output(['gh', 'auth', 'token'], text=True).strip()
                import shlex
                cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', host['ssh'],
                       'env PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH" ' +
                       'SISO_CI_WORK=' + shlex.quote(host['work'] + '/workers/' + host['slot']) +
                       ' python3 ' + shlex.quote(host['script']) + ' worker']
            else:
                cmd = [sys.executable, str(script), 'worker']
            env = {**os.environ, 'SISO_CI_WORK': str(Path(root) / 'workers' / host['slot'])}
            p = subprocess.run(cmd, input=json.dumps(request), text=True, capture_output=True, env=env)
            # Test output stays on its host. Print only bounded orchestration receipts.
            results.append({'repo': job['repo'], 'kind': job['kind'], 'slot': host['slot'],
                            'exit': p.returncode, 'receipt': worker_receipt(p.stdout, p.stderr, p.returncode)})
        return results
    # Partition by eligibility so an incompatible remote cannot starve a local job.
    groups = {}
    for job in jobs:
        eligible = tuple(i for i, h in enumerate(hosts) if not h.get('repos') or job['repo'] in h['repos'])
        if not eligible:
            raise RuntimeError('no eligible host for ' + job['repo'])
        groups.setdefault(eligible, []).append(job)
    if len(groups) > 1:
        result = []
        # Re-enter per compatible group; each group still uses all eligible slots.
        for eligible, group in groups.items():
            result += dispatch(group, [hosts[i] for i in eligible], script, root)
        return result
    with ThreadPoolExecutor(max_workers=len(hosts)) as executor:
        return [item for group in executor.map(consume, hosts) for item in group]


def worker_receipt(stdout, stderr, code):
    # Worker output and tracebacks can contain credentials. Export only fixed categories.
    for line in reversed(stdout.splitlines()):
        try:
            receipt = json.loads(line)
        except ValueError:
            continue
        if isinstance(receipt, dict) and receipt.get('state') in ('success', 'failure', 'error', 'skipped'):
            safe = {'state': receipt['state']}
            wait = receipt.get('queue_wait_seconds')
            if type(wait) in (int, float) and 0 <= wait < 10**9:
                safe['queue_wait_seconds'] = wait
            category = receipt.get('category')
            if category in ('clone-tracked-changes', 'disk-full', 'network-resolution', 'worker-command-failed'):
                safe['category'] = category
            return safe
    category = infrastructure_category(stderr) or 'worker-command-failed'
    if 'RuntimeError: owned CI clone has tracked changes; retained for inspection' in stderr:
        category = 'clone-tracked-changes'
    return {'state': 'error', 'category': category} if code else {'state': 'success'}


class Controller:
    """Keep discovery responsive while long jobs run. One future owns each host slot."""
    def __init__(self, hosts, script, root):
        self.hosts, self.script, self.root = hosts, script, root
        self.pool = ThreadPoolExecutor(max_workers=len(hosts))
        self.active, self.pending = {}, {}

    @staticmethod
    def key(job):
        return (job['repo'], job['kind'], job.get('pr', {}).get('headRefOid', job.get('sha')))

    def tick(self, jobs):
        receipts = []
        for slot, (future, key) in list(self.active.items()):
            if future.done():
                try:
                    receipts.extend(future.result())
                except Exception as error:
                    receipts.append({'slot': slot, 'exit': 1, 'error': type(error).__name__})
                del self.active[slot]
        busy = {key for _, key in self.active.values()}
        current = {self.key(j): j for j in jobs}
        # Only undispatched current heads stay queued; running old heads may finish.
        self.pending = {key: self.pending.get(key, {**job, 'enqueued_at': time.time()})
                        for key, job in current.items() if key not in busy}
        for host in self.hosts:
            if host['slot'] in self.active:
                continue
            for key, job in list(self.pending.items()):
                if host.get('repos') and job['repo'] not in host['repos']:
                    continue
                future = self.pool.submit(dispatch, [job], [host], self.script, self.root)
                self.active[host['slot']] = (future, key)
                del self.pending[key]
                break
        return receipts
