"""Owner-armed, both-idle CI handoff; no network or launchd operations.

WORK/handoff must already be owner-only (0700), request.json owner-only (0600).
See the request fixture in tests/ci-runtime-handoff.test.py for the wire contract.
Rollback uses the same request/idle gates: operation=rollback, rollback_of=<id>,
target_root/script/sha equal that completed receipt's original source identity.
It never permits an arbitrary rollback target or relaxes code/config equivalence.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import time
from xml.sax.saxutils import escape

import worker_pool

FD_ENV = 'SISO_CI_HANDOFF_FD'
PENDING_ENV = 'SISO_CI_HANDOFF_PENDING'
TARGET_SCRIPT = 'agents/harness/ci/siso-ci'
BASELINE = 'fefd6e7a83db97183d56fd93d8a79cd261efa786'
CODE = ('siso-ci', 'worker_pool.py', 'runtime_handoff.py')
SHA = re.compile(r'[0-9a-f]{40}\Z')


class Rejected(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise Rejected(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def trusted_path(path):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.normpath(str(path)), 'noncanonical path')
    for part in (*reversed(path.parents), path):
        s = part.lstat()
        require(not stat.S_ISLNK(s.st_mode), 'symlink path')
        require(s.st_uid in (0, os.getuid()), 'foreign path owner')
        sticky_root = s.st_uid == 0 and stat.S_ISDIR(s.st_mode) and s.st_mode & stat.S_ISVTX
        require(not s.st_mode & 0o022 or sticky_root, 'writable path ancestor')
    return path


def read_file(path, mode=None, limit=2 * 1024 * 1024):
    path = trusted_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1,
                'unsafe file owner/type/links')
        require(mode is None or stat.S_IMODE(s.st_mode) == mode, 'unsafe file mode')
        require(s.st_size <= limit, 'oversized file')
        data = os.read(fd, limit + 1)
        after = os.fstat(fd)
        require(len(data) <= limit and (s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'file changed during read')
        require(path.stat().st_ino == s.st_ino, 'file replaced during read')
        return data
    finally:
        os.close(fd)


def atomic(path, data, mode=0o600):
    """Only used beneath already checked owner directories; durable atomic replace."""
    path = Path(path)
    trusted_path(path.parent)
    if path.exists() or path.is_symlink():
        read_file(path)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            os.fchmod(out.fileno(), mode)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_json(path, value):
    atomic(path, (json.dumps(value, sort_keys=True) + '\n').encode())


def git(root, *args):
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0',
           'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
    p = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
                        '-C', str(root), *args], capture_output=True, timeout=15, env=env)
    require(p.returncode == 0, 'local git validation failed')
    return p.stdout.decode().strip()


def root_of(script):
    return Path(git(Path(script).parent, 'rev-parse', '--show-toplevel'))


def selected(ci):
    all_hosts = json.loads(read_file(Path(ci) / 'workers.json'))
    cfg = all_hosts.get(socket.gethostname(), all_hosts['default'])
    cfg['retention'] = {'floor_gib': 25, 'margin_gib': 5, 'days': 2, **cfg.get('retention', {})}
    return cfg


def roots(cfg):
    def full(p):
        return os.path.abspath(os.path.expanduser(p))
    work = full(os.environ.get('SISO_CI_WORK', cfg.get('work_root', '~/SISO_Workspace/_data/siso-ci')))
    return {'work': work, 'state': str(Path(work) / 'state.json'),
            'archive': full(os.environ.get('SISO_CI_ARCHIVE', cfg.get('archive_root', str(Path(work) / '_archive')))),
            'temp': full(cfg.get('temp_root', os.environ.get('TMPDIR', tempfile.gettempdir()))),
            'red_main': full(os.environ.get('SISO_RED_MAIN_WORK', cfg.get('red_main_root', '~/SISO_Workspace/_data/worktrees')))}


def validate_lock(fd, path):
    trusted_path(path)
    s, on_disk = os.fstat(fd), Path(path).stat()
    require(stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1 and
            (s.st_dev, s.st_ino) == (on_disk.st_dev, on_disk.st_ino), 'inherited lock inode mismatch')
    # A different open description must be blocked: possession of an unlocked FD is not adoption.
    with open(path, 'a') as probe:
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise Rejected('inherited descriptor is not the lock owner') from error
            return
    raise Rejected('inherited descriptor does not hold coordinator lock')


@contextmanager
def coordinator_lock(path):
    inherited = os.environ.pop(FD_ENV, None)
    if inherited is None:
        require(PENDING_ENV not in os.environ, 'handoff missing inherited lock')
        with worker_pool.lock(path) as fd:
            validate_lock(fd, path)
            yield fd
    else:
        fd = int(inherited)
        validate_lock(fd, path)
        os.set_inheritable(fd, False)
        try:
            yield fd
        finally:
            os.close(fd)


def exec_locked(fd, script, argv, pending=None):
    env = {**os.environ, FD_ENV: str(fd)}
    if pending:
        env[PENDING_ENV] = str(pending)
    else:
        env.pop(PENDING_ENV, None)
    os.set_inheritable(fd, True)
    try:
        os.execve(sys.executable, [sys.executable, str(script), *argv], env)
    finally:  # exec failure only
        os.set_inheritable(fd, False)


def shell_words(command):
    """Literal POSIX words with exact spans; reject operators and expansions."""
    require('\n' not in command and '\r' not in command, 'multiline launch command')
    word = re.compile(r'''(?:[^\s'"\\;&|<>()$`]+|'[^']*'|"(?:[^"\\$`]|\\.)*"|\\[^\r\n])+''')
    words, offset = [], 0
    while offset < len(command):
        if command[offset].isspace():
            offset += 1
            continue
        match = word.match(command, offset)
        require(match is not None, 'unsafe shell launch token')
        decoded = shlex.split(match.group())
        require(len(decoded) == 1, 'invalid shell launch token')
        words.append((decoded[0], offset, match.end()))
        offset = match.end()
    return words


class Handoff:
    def __init__(self, script, work, canonical_root=None, launch=None, baseline=BASELINE):
        self.script = trusted_path(Path(script).absolute())
        self.root = root_of(self.script)
        self.sha = git(self.root, 'rev-parse', 'HEAD')
        self.work = Path(work).absolute()
        self.directory = self.work / 'handoff'
        # The owner pins the machine's exact canonical root in the private request.
        self.canonical = Path(canonical_root) if canonical_root is not None else None
        self.launch = Path(launch or Path.home() / 'Library/LaunchAgents/com.siso.ci.workers.plist')
        self.baseline = baseline
        self.loaded = {name: digest(read_file(self.script.parent / name)) for name in CODE}
        self.state = roots(selected(self.script.parent))
        require(self.state['work'] == str(self.work), 'serving work root mismatch')
        self.rejected = None

    def private_directory(self):
        p = trusted_path(self.directory)
        s = p.stat()
        require(s.st_uid == os.getuid() and stat.S_ISDIR(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o700,
                'handoff directory must be owner-only 0700')

    def clean(self, root, ci):
        trusted_path(root / '.git')
        trusted_path(Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')))
        require(git(root, 'rev-parse', '--show-toplevel') == str(root), 'wrong repository root')
        require(git(root, 'symbolic-ref', '--short', 'HEAD') == 'main', 'expected main branch')
        require(not git(root, 'status', '--porcelain', '--untracked-files=no'), 'dirty tracked source')
        rel = str(ci.relative_to(root))
        git(root, 'ls-files', '--error-unmatch', '--',
            *(str(Path(rel) / name) for name in (*CODE, 'repos.json', 'workers.json')))
        require(not any(line.startswith('120000 ') for line in git(root, 'ls-files', '-s', '--', rel).splitlines()),
                'tracked CI symlink')
        for flags in (('--others', '--exclude-standard'), ('--others', '--ignored', '--exclude-standard')):
            names = git(root, 'ls-files', *flags, '-z', '--', rel)
            for name in names.split('\0'):
                if not name:
                    continue
                p = root / name
                require(not p.is_symlink(), 'untracked CI symlink')
                require(not (p.stat().st_mode & 0o111 or p.suffix in ('.py', '.pyc', '.so', '.sh') or not p.suffix),
                        'untracked executable CI file')

    def validate(self, req):
        require(isinstance(req, dict) and req.get('version') == 1, 'invalid request version')
        require(re.fullmatch(r'[0-9a-f]{32}', req.get('id', '')) is not None, 'invalid request id')
        for key in ('source_sha', 'target_sha', 'approved_ancestor'):
            require(isinstance(req.get(key), str) and SHA.fullmatch(req[key]), 'full SHA required')
        require(req['source_sha'] == self.sha == git(self.root, 'rev-parse', 'HEAD'), 'serving source SHA mismatch')
        operation = req.get('operation')
        target_root = Path(req['target_root'])
        target = Path(req['target_script'])
        remote = 'siso'
        if operation == 'rollback':
            prior_id = req.get('rollback_of', '')
            require(re.fullmatch(r'[0-9a-f]{32}', prior_id) is not None, 'invalid rollback receipt')
            prior = json.loads(read_file(self.directory / ('completed-' + prior_id + '.json'), 0o600))
            require(prior['target_script'] == str(self.script) and prior['target_sha'] == self.sha,
                    'rollback serving identity mismatch')
            require(str(target_root) == prior['source_root'] and str(target) == prior['source_script'] and
                    req['target_sha'] == prior['source_sha'], 'rollback target must equal recorded source')
            remote = prior['source_remote']
        else:
            require(operation == 'adopt' and (self.canonical is None or target_root == self.canonical) and
                    target == target_root / TARGET_SCRIPT, 'target is not canonical CI')
        trusted_path(target_root)
        trusted_path(target)
        self.clean(self.root, self.script.parent)
        self.clean(target_root, target.parent)
        require(git(target_root, 'rev-parse', 'HEAD') == req['target_sha'], 'target HEAD mismatch')
        urls = (f'https://github.com/sisodias/{remote}', f'https://github.com/sisodias/{remote}.git',
                f'git@github.com:sisodias/{remote}.git', f'ssh://git@github.com/sisodias/{remote}.git')
        require(git(target_root, 'remote', 'get-url', 'origin') in urls, 'unexpected target remote')
        if operation == 'adopt':
            base = git(target_root, 'rev-parse', self.baseline + '^{commit}')
            git(target_root, 'merge-base', '--is-ancestor', base, req['approved_ancestor'])
        git(target_root, 'merge-base', '--is-ancestor', req['approved_ancestor'], req['target_sha'])
        for name, loaded in self.loaded.items():
            require(digest(read_file(self.script.parent / name)) == loaded == digest(read_file(target.parent / name)),
                    'implementation mismatch')
        require(read_file(self.script.parent / 'repos.json') == read_file(target.parent / 'repos.json'), 'repos config mismatch')
        require(selected(self.script.parent) == selected(target.parent), 'workers config mismatch')
        require(roots(selected(target.parent)) == self.state, 'effective state roots mismatch')
        return target

    def launch_change(self, req, target):
        before = read_file(self.launch)
        require(digest(before) == req['launch_sha256'], 'original launch hash mismatch')
        cfg = plistlib.loads(before)
        argv = cfg['ProgramArguments']
        label = cfg.get('Label')
        require(isinstance(label, str) and self.launch.name == label + '.plist',
                'launch label/path mismatch')
        if label == 'com.siso.ci.workers':
            ssh = ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                   '-o', 'IdentitiesOnly=yes', '-o', 'ServerAliveInterval=30', '-i',
                   str(Path.home() / '.ssh/siso-ci-loopback'), pwd.getpwuid(os.getuid()).pw_name + '@127.0.0.1']
            require(len(argv) == len(ssh) + 1 and argv[:-1] == ssh, 'unexpected loopback SSH arguments')
            old_value = argv[-1]
            tokens = shell_words(old_value)
            words = [word[0] for word in tokens]
            path = str(Path.home() / '.local/bin') + ':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'
            require(len(words) == 7 and words[:4] == ['env', 'PATH=' + path, '/opt/homebrew/bin/python3', str(self.script)]
                    and words[4:6] == ['serve', '--every'] and words[6].isdigit() and int(words[6]) > 0,
                    'unexpected embedded CI command')
            replacement = shlex.quote(str(target))
            if req.get('operation') == 'rollback':
                ident = req['rollback_of']
                prior = json.loads(read_file(self.directory / ('completed-' + ident + '.json'), 0o600))
                saved = read_file(self.directory / ('launch-before-' + ident + '.plist'), 0o600)
                require(digest(saved) == prior['launch_before'] and digest(before) == prior['launch_after'],
                        'rollback launch snapshot mismatch')
                saved_command = plistlib.loads(saved)['ProgramArguments'][-1]
                saved_tokens = shell_words(saved_command)
                require([word[0] for word in saved_tokens] == words[:3] + [str(target)] + words[4:],
                        'rollback embedded command mismatch')
                replacement = saved_command[saved_tokens[3][1]:saved_tokens[3][2]]
            new_value = old_value[:tokens[3][1]] + replacement + old_value[tokens[3][2]:]
            argv[-1] = new_value
        else:
            require(label == 'com.siso.ci' and len(argv) == 5 and argv[1:4] ==
                    [str(self.script), 'serve', '--every'] and argv[4].isdigit() and int(argv[4]) > 0,
                    'unexpected direct CI arguments')
            old_value, new_value = str(self.script), str(target)
            argv[1] = new_value
        old = ('<string>' + escape(old_value) + '</string>').encode()
        new = ('<string>' + escape(new_value) + '</string>').encode()
        require(before.count(old) == 1, 'launch must contain one exact XML script token')
        after = before.replace(old, new, 1)
        changed = plistlib.loads(after)
        require(changed == cfg, 'launch changed beyond script token')
        return before, after

    def fail(self, reason, raw=None):
        # Unsafe directories are never written. In-memory fingerprint also prevents tight retries.
        self.private_directory()
        save_json(self.directory / 'failure.json', {'status': 'failed', 'pid': os.getpid(),
                  'reason': reason, 'at': time.time(), 'source_sha': self.sha})
        request = self.directory / 'request.json'
        if raw is not None and read_file(request, 0o600, 16384) == raw:
            os.replace(request, self.directory / ('rejected-' + digest(raw) + '.json'))

    def attempt(self, fd, workers_busy=False, trains_busy=False):
        if workers_busy or trains_busy:
            return 'pending'
        request = self.directory / 'request.json'
        if not request.exists() and not request.is_symlink():
            return 'absent'
        raw = before = after = None
        changed = False
        try:
            marker = request.lstat()
            token = (marker.st_ino, marker.st_mtime_ns, marker.st_ctime_ns, marker.st_size)
            if self.rejected == token:
                return 'rejected'
            self.rejected = token
            self.private_directory()
            raw = read_file(request, 0o600, 16384)
            req = json.loads(raw)
            target = self.validate(req)
            validate_lock(fd, self.work / 'coordinator.lock')
            before, after = self.launch_change(req, target)
            env = {k: v for k, v in os.environ.items() if k not in (FD_ENV, PENDING_ENV)}
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            test = subprocess.run([sys.executable, '-B', str(target), 'selftest'], cwd=target.parent,
                                  env=env, capture_output=True, timeout=30)
            require(test.returncode == 0, 'target selftest failed')
            self.validate(req)  # source, target, configs and request must still be the approved snapshot
            require(read_file(request, 0o600, 16384) == raw, 'request changed during validation')
            require(read_file(self.launch) == before, 'launch changed during validation')
            ident = req['id']
            require(not (self.directory / ('consumed-' + ident + '.json')).exists(), 'request already consumed')
            source_url = git(self.root, 'remote', 'get-url', 'origin')
            require(source_url in ('https://github.com/sisodias/siso-harness-lab.git',
                    'git@github.com:sisodias/siso-harness-lab.git', 'https://github.com/sisodias/siso.git',
                    'git@github.com:sisodias/siso.git'), 'unexpected serving remote')
            prepared = {'status': 'prepared', 'id': ident, 'pid': os.getpid(), 'source_root': str(self.root),
                        'source_script': str(self.script), 'source_sha': self.sha,
                        'source_remote': 'siso' if source_url.endswith('/siso.git') or source_url.endswith(':sisodias/siso.git') else 'siso-harness-lab',
                        'target_script': str(target), 'target_sha': req['target_sha'], 'state': self.state,
                        'implementation_sha256': self.loaded,
                        'launch_before': digest(before), 'launch_after': digest(after),
                        'launch_mode': stat.S_IMODE(self.launch.stat().st_mode), 'at': time.time()}
            atomic(self.directory / ('launch-before-' + ident + '.plist'), before)
            pending = self.directory / ('prepared-' + ident + '.json')
            save_json(pending, prepared)
            atomic(self.launch, after, prepared['launch_mode'])
            changed = True
            os.replace(request, self.directory / ('consumed-' + ident + '.json'))
            exec_locked(fd, target, ['serve', *sys.argv[2:]], pending)
            raise Rejected('exec returned unexpectedly')
        except Exception as error:
            if changed:
                require(read_file(self.launch) == after, 'cannot rollback concurrently modified launch')
                atomic(self.launch, before, prepared['launch_mode'])
            try:
                self.fail(str(error) if isinstance(error, Rejected) else type(error).__name__,
                          raw if request.exists() else None)
            except (OSError, Rejected):
                pass
            return 'rejected'

    def startup(self, fd):
        pending = os.environ.pop(PENDING_ENV, None)
        identity = {'script': str(self.script), 'sha': self.sha, 'pid': os.getpid(),
                    'lock_inode': os.fstat(fd).st_ino, 'state': self.state}
        if pending:
            self.private_directory()
            p = Path(pending)
            require(p.parent == self.directory and re.fullmatch(r'prepared-[0-9a-f]{32}\.json', p.name),
                    'unexpected prepared receipt path')
            receipt = json.loads(read_file(p, 0o600))
            ident = receipt['id']
            require(p.name == 'prepared-' + ident + '.json', 'receipt ID mismatch')
            try:
                require(receipt['status'] == 'prepared' and receipt['pid'] == os.getpid(), 'startup PID/status mismatch')
                require(not (self.directory / ('completed-' + ident + '.json')).exists(), 'startup already completed')
                require(receipt['target_script'] == str(self.script) and receipt['target_sha'] == self.sha,
                        'startup target identity mismatch')
                validate_lock(fd, self.work / 'coordinator.lock')
                require(self.state == receipt['state'], 'startup state mismatch')
                req = json.loads(read_file(self.directory / ('consumed-' + ident + '.json'), 0o600, 16384))
                # Re-run the original validation from the preserved source perspective before dispatch.
                source = Handoff(receipt['source_script'], self.work, self.canonical, self.launch, self.baseline)
                source.validate(req)
                require(digest(read_file(self.launch)) == receipt['launch_after'], 'startup launch mismatch')
                save_json(self.directory / ('completed-' + ident + '.json'),
                          {**receipt, 'status': 'completed', 'startup': identity, 'completed_at': time.time()})
            except Exception:
                # Never dispatch from an invalid target. Restore only our exact launch mutation.
                before = read_file(self.directory / ('launch-before-' + ident + '.plist'), 0o600)
                require(digest(before) == receipt['launch_before'] and
                        digest(read_file(self.launch)) == receipt['launch_after'], 'unsafe startup rollback')
                atomic(self.launch, before, receipt['launch_mode'])
                save_json(self.directory / 'failure.json', {'status': 'failed', 'reason': 'startup validation failed',
                          'pid': os.getpid(), 'id': ident})
                require(git(receipt['source_root'], 'rev-parse', 'HEAD') == receipt['source_sha'], 'rollback source changed')
                self.clean(Path(receipt['source_root']), Path(receipt['source_script']).parent)
                for name, checksum in receipt['implementation_sha256'].items():
                    require(digest(read_file(Path(receipt['source_script']).parent / name)) == checksum,
                            'rollback implementation changed')
                exec_locked(fd, receipt['source_script'], ['serve', *sys.argv[2:]])
                raise Rejected('startup rollback exec returned')
        return identity
