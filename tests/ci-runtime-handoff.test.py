"""Real local Git/plist/request fixtures; no network or production paths."""
import json
import os
from pathlib import Path
import plistlib
import pwd
import runpy
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

CI = Path(__file__).resolve().parents[1] / 'ci'
sys.path.insert(0, str(CI))
import runtime_handoff as h
import worker_pool


class Executed(BaseException):
    pass


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.work = self.root / 'work'
        self.directory = self.work / 'handoff'
        self.directory.mkdir(parents=True, mode=0o700)
        self.env = patch.dict(os.environ, {'SISO_CI_WORK': str(self.work),
            'SISO_CI_ARCHIVE': str(self.work / 'archive'), 'SISO_RED_MAIN_WORK': str(self.work / 'recovery'),
            'TMPDIR': str(self.work / 'tmp')})
        self.env.start()
        self.source = self.root / 'source'
        self.target = self.root / 'target'
        for root, ci, remote in ((self.source, 'ci', 'siso-harness-lab'),
                                 (self.target, 'agents/harness/ci', 'siso')):
            folder = root / ci
            folder.mkdir(parents=True)
            for name in (*h.CODE, 'affected.py', 'retention.py', 'red_main.py'):
                shutil.copyfile(CI / name, folder / name)
            (folder / 'repos.json').write_text('{"fixture/repo":{"test":"true"}}\n')
            (folder / 'workers.json').write_text(json.dumps({'default': {
                'hosts': [{'name': 'local', 'workers': 1}], 'work_root': str(self.work),
                'temp_root': str(self.work / 'tmp')}}))
            self.git(root, 'init', '-q', '-b', 'main')
            self.git(root, 'config', 'user.name', 'Fixture')
            self.git(root, 'config', 'user.email', 'fixture@example.invalid')
            self.git(root, 'remote', 'add', 'origin', 'https://github.com/sisodias/' + remote + '.git')
            self.commit(root)
        self.script = self.source / 'ci/siso-ci'
        self.target_script = self.target / h.TARGET_SCRIPT
        self.base = self.git(self.target, 'rev-parse', 'HEAD')
        self.launch = self.root / 'launch/com.siso.ci.plist'
        self.launch.parent.mkdir()
        self.original = plistlib.dumps({'Label': 'com.siso.ci', 'ProgramArguments':
            [sys.executable, str(self.script), 'serve', '--every', '60'],
            'EnvironmentVariables': {'EXACT_ROUTE': 'unchanged'}, 'KeepAlive': True})
        self.launch.write_bytes(self.original)
        self.launch.chmod(0o600)
        self.request = {'version': 1, 'id': 'a' * 32, 'operation': 'adopt',
            'source_sha': self.git(self.source, 'rev-parse', 'HEAD'),
            'target_root': str(self.target), 'target_script': str(self.target_script),
            'target_sha': self.base, 'approved_ancestor': self.base,
            'launch_sha256': h.digest(self.original)}
        self.arm()
        self.handoff = self.make_handoff()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE,
                                       env={**os.environ, 'GIT_NO_LAZY_FETCH': '1'}).decode().strip()

    def commit(self, root):
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'fixture')

    def make_handoff(self, script=None):
        return h.Handoff(script or self.script, self.work, self.target, self.launch, self.base)

    def arm(self):
        p = self.directory / 'request.json'
        p.write_text(json.dumps(self.request))
        p.chmod(0o600)

    def reject(self):
        with worker_pool.lock(self.work / 'coordinator.lock') as fd, patch.object(os, 'execve') as execute:
            self.assertEqual(self.handoff.attempt(fd), 'rejected')
            execute.assert_not_called()
        self.assertEqual(self.launch.read_bytes(), self.original)

    def prepare(self, fd):
        with patch.object(os, 'execve', side_effect=Executed) as execute:
            with self.assertRaises(Executed):
                self.handoff.attempt(fd)
        return execute.call_args.args[2]

    def workers_launch(self, command=None):
        self.launch = self.launch.with_name('com.siso.ci.workers.plist')
        ssh = ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'IdentitiesOnly=yes', '-o', 'ServerAliveInterval=30', '-i',
               str(Path.home() / '.ssh/siso-ci-loopback'), pwd.getpwuid(os.getuid()).pw_name + '@127.0.0.1']
        path = str(Path.home() / '.local/bin') + ':/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'
        command = command or ('env PATH=' + path + ' /opt/homebrew/bin/python3 "' + str(self.script) + '" serve --every 60')
        self.original = plistlib.dumps({'Label': 'com.siso.ci.workers', 'ProgramArguments': ssh + [command],
            'EnvironmentVariables': {'EXACT_ROUTE': 'unchanged'}, 'KeepAlive': True,
            'StandardOutPath': str(self.work / 'serve.log')})
        self.launch.write_bytes(self.original)
        self.launch.chmod(0o600)
        self.request['launch_sha256'] = h.digest(self.original)
        self.arm()
        self.handoff = self.make_handoff()

    def test_busy_worker_and_busy_train_leave_every_byte_untouched(self):
        before = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        for workers, trains in ((True, False), (False, True), (True, True)):
            self.assertEqual(self.handoff.attempt(-1, workers, trains), 'pending')
            self.assertEqual({p.name: p.read_bytes() for p in self.directory.iterdir()}, before)
            self.assertEqual(self.launch.read_bytes(), self.original)

    def test_invalid_sha_and_canonical_path(self):
        for field, value in (('target_sha', 'abcd'), ('source_sha', 'f' * 40),
                             ('target_root', str(self.source)), ('target_script', str(self.script)),
                             ('target_sha', '0' * 40), ('approved_ancestor', '0' * 40)):
            with self.subTest(field=field, value=value):
                old = self.request[field]
                self.request[field] = value
                self.arm()
                self.reject()
                self.request[field] = old

    def test_launch_hash_mismatch_and_target_not_descended_from_approval(self):
        self.request['launch_sha256'] = '0' * 64
        self.arm()
        self.reject()
        self.request['launch_sha256'] = h.digest(self.original)
        self.git(self.target, 'checkout', '-q', '--orphan', 'unapproved')
        self.git(self.target, 'commit', '-qm', 'unapproved root')
        self.git(self.target, 'branch', '-M', 'main')
        self.request['target_sha'] = self.git(self.target, 'rev-parse', 'HEAD')
        self.request['approved_ancestor'] = self.request['target_sha']
        self.arm()
        self.reject()

    def test_permissions_symlinks_and_oversized_bad_json(self):
        p = self.directory / 'request.json'
        for mode in (0o644, 0o666, 0o400):
            p.chmod(mode)
            self.reject()
            p.chmod(0o600)
        self.directory.chmod(0o755)
        self.reject()
        self.directory.chmod(0o700)
        p.unlink()
        p.symlink_to(self.launch)
        self.reject()
        p.unlink()
        for raw in ('{broken', '[' + ' ' * 17000 + ']'):
            p.write_text(raw)
            p.chmod(0o600)
            self.reject()

    def test_unsafe_parent_and_symlink_target(self):
        self.root.chmod(0o777)
        self.reject()
        self.root.chmod(0o700)
        link = self.root / 'link'
        link.symlink_to(self.target, target_is_directory=True)
        self.request.update(target_root=str(link), target_script=str(link / h.TARGET_SCRIPT))
        self.handoff.canonical = link
        self.arm()
        self.reject()

    def test_branch_remote_dirty_and_untracked_executable(self):
        self.git(self.target, 'checkout', '-qb', 'other')
        self.reject()
        self.git(self.target, 'checkout', '-q', 'main')
        self.arm()
        self.git(self.target, 'remote', 'set-url', 'origin', 'https://github.com/foreign/siso.git')
        self.reject()
        self.git(self.target, 'remote', 'set-url', 'origin', 'https://github.com/sisodias/siso.git')
        self.arm()
        p = self.target_script.parent / 'repos.json'
        original = p.read_bytes()
        p.write_text('{}')
        self.reject()
        p.write_bytes(original)
        self.arm()
        (self.target_script.parent / 'extra.py').write_text('print("untracked")')
        self.reject()

    def test_source_implementation_repos_workers_and_state_mismatch(self):
        for name in ('worker_pool.py', 'repos.json', 'workers.json'):
            with self.subTest(name=name):
                p = self.target_script.parent / name
                original = p.read_bytes()
                if name == 'worker_pool.py':
                    p.write_bytes(original + b'\n# different implementation\n')
                elif name == 'repos.json':
                    p.write_text('{"different/repo":{"test":"true"}}')
                else:
                    d = json.loads(original)
                    d['default']['hosts'][0]['workers'] = 2
                    p.write_text(json.dumps(d))
                self.commit(self.target)
                self.request['target_sha'] = self.git(self.target, 'rev-parse', 'HEAD')
                self.arm()
                self.reject()
                p.write_bytes(original)
                self.commit(self.target)
        self.request['target_sha'] = self.git(self.target, 'rev-parse', 'HEAD')
        self.arm()
        self.handoff.state['temp'] = str(self.root / 'different-tmp')
        self.reject()

    def test_actual_target_selftest_failure(self):
        for root, p in ((self.source, self.script.parent), (self.target, self.target_script.parent)):
            (p / 'repos.json').write_text('{}')
            self.commit(root)
        self.request.update(source_sha=self.git(self.source, 'rev-parse', 'HEAD'),
                            target_sha=self.git(self.target, 'rev-parse', 'HEAD'))
        self.arm()
        self.handoff = self.make_handoff()
        self.reject()
        self.assertEqual(json.loads((self.directory / 'failure.json').read_text())['reason'], 'target selftest failed')

    def test_request_mutated_during_real_selftest_is_rejected(self):
        for root, script in ((self.source, self.script), (self.target, self.target_script)):
            code = script.read_text().replace("        return selftest()", "        Path(os.environ['FIXTURE_REQUEST']).write_text('{}')\n        return selftest()")
            script.write_text(code)
            self.commit(root)
        self.request.update(source_sha=self.git(self.source, 'rev-parse', 'HEAD'),
                            target_sha=self.git(self.target, 'rev-parse', 'HEAD'))
        self.arm()
        self.handoff = self.make_handoff()
        with patch.dict(os.environ, {'FIXTURE_REQUEST': str(self.directory / 'request.json')}):
            self.reject()
        self.assertEqual(json.loads((self.directory / 'failure.json').read_text())['reason'], 'request changed during validation')

    def test_idle_handoff_once_startup_and_preserved_launch_bytes(self):
        # Explicit default retention and its absence have identical semantics.
        p = self.target_script.parent / 'workers.json'
        cfg = json.loads(p.read_text())
        cfg['default']['retention'] = {'floor_gib': 25, 'margin_gib': 5, 'days': 2}
        p.write_text(json.dumps(cfg))
        self.commit(self.target)
        self.request['target_sha'] = self.git(self.target, 'rev-parse', 'HEAD')
        self.arm()
        with worker_pool.lock(self.work / 'coordinator.lock') as fd:
            env = self.prepare(fd)
            self.assertFalse((self.directory / 'request.json').exists())
            self.assertEqual(self.launch.read_bytes(), self.original.replace(str(self.script).encode(), str(self.target_script).encode()))
            self.assertEqual((self.directory / ('launch-before-' + self.request['id'] + '.plist')).read_bytes(), self.original)
            with patch.dict(os.environ, {h.PENDING_ENV: env[h.PENDING_ENV]}):
                identity = self.make_handoff(self.target_script).startup(fd)
            completed = json.loads((self.directory / ('completed-' + self.request['id'] + '.json')).read_text())
            self.assertEqual(completed['startup'], identity)
            self.assertEqual(identity['pid'], os.getpid())
            self.assertEqual(identity['sha'], self.request['target_sha'])
            self.assertEqual(self.handoff.attempt(fd), 'absent')

    def test_exec_failure_restores_plist_consumes_and_does_not_retry(self):
        with worker_pool.lock(self.work / 'coordinator.lock') as fd, patch.object(os, 'execve', side_effect=OSError('fixture')) as execute:
            self.assertEqual(self.handoff.attempt(fd), 'rejected')
            self.assertEqual(self.launch.read_bytes(), self.original)
            self.assertFalse(os.get_inheritable(fd))
            self.assertEqual(self.handoff.attempt(fd), 'absent')
            self.assertEqual(execute.call_count, 1)
            h.validate_lock(fd, self.work / 'coordinator.lock')

    def test_target_startup_mismatch_rolls_back_before_dispatch(self):
        with worker_pool.lock(self.work / 'coordinator.lock') as fd:
            env = self.prepare(fd)
            target = self.make_handoff(self.target_script)
            target.sha = 'f' * 40
            with patch.dict(os.environ, {h.PENDING_ENV: env[h.PENDING_ENV]}), patch.object(os, 'execve', side_effect=Executed) as execute:
                with self.assertRaises(Executed):
                    target.startup(fd)
            self.assertEqual(self.launch.read_bytes(), self.original)
            self.assertEqual(execute.call_args.args[1][1], str(self.script))
            self.assertFalse(any(self.directory.glob('completed-*')))

    def test_explicit_owner_rollback_uses_completed_source_only(self):
        with worker_pool.lock(self.work / 'coordinator.lock') as fd:
            env = self.prepare(fd)
            target = self.make_handoff(self.target_script)
            with patch.dict(os.environ, {h.PENDING_ENV: env[h.PENDING_ENV]}):
                target.startup(fd)
            self.request.update(id='b' * 32, operation='rollback', rollback_of='a' * 32,
                source_sha=target.sha, target_root=str(self.source), target_script=str(self.script),
                target_sha=self.handoff.sha, approved_ancestor=self.handoff.sha,
                launch_sha256=h.digest(self.launch.read_bytes()))
            self.arm()
            with patch.object(os, 'execve', side_effect=Executed) as execute:
                with self.assertRaises(Executed):
                    target.attempt(fd)
            self.assertEqual(execute.call_args.args[1][1], str(self.script))
            self.assertEqual(self.launch.read_bytes(), self.original)

    def test_adopt_rejects_unlocked_or_wrong_inode_descriptor(self):
        lock = self.work / 'coordinator.lock'
        with open(lock, 'a') as fd:
            with self.assertRaises(h.Rejected):
                h.validate_lock(fd.fileno(), lock)
        with worker_pool.lock(lock), open(self.root / 'other', 'w') as fd:
            with self.assertRaises(h.Rejected):
                h.validate_lock(fd.fileno(), lock)

    def test_lock_rejects_same_inode_foreign_description_but_accepts_inherited_owner(self):
        lock = self.work / 'coordinator.lock'
        with worker_pool.lock(lock) as owner, open(lock, 'a') as foreign:
            with self.assertRaises(h.Rejected):
                h.validate_lock(foreign.fileno(), lock)
            h.validate_lock(owner, lock)
            inherited = os.dup(owner)
            try:
                h.validate_lock(inherited, lock)
            finally:
                os.close(inherited)

    def test_realistic_workers_ssh_adopt_and_exact_quoted_rollback(self):
        moved = self.root / "canonical target with space and ' quote"
        self.target.rename(moved)
        self.target = moved
        self.target_script = self.target / h.TARGET_SCRIPT
        self.request.update(target_root=str(self.target), target_script=str(self.target_script))
        self.workers_launch()
        original_cfg = plistlib.loads(self.original)
        with worker_pool.lock(self.work / 'coordinator.lock') as fd:
            env = self.prepare(fd)
            cfg = plistlib.loads(self.launch.read_bytes())
            self.assertEqual(cfg['ProgramArguments'][:-1], original_cfg['ProgramArguments'][:-1])
            self.assertEqual(shlex.split(cfg['ProgramArguments'][-1])[3], str(self.target_script))
            old_word = '"' + str(self.script) + '"'
            expected = self.original.replace(old_word.encode(), shlex.quote(str(self.target_script)).encode())
            self.assertEqual(self.launch.read_bytes(), expected)
            target = self.make_handoff(self.target_script)
            with patch.dict(os.environ, {h.PENDING_ENV: env[h.PENDING_ENV]}):
                target.startup(fd)
            self.request.update(id='b' * 32, operation='rollback', rollback_of='a' * 32,
                source_sha=target.sha, target_root=str(self.source), target_script=str(self.script),
                target_sha=self.handoff.sha, approved_ancestor=self.handoff.sha,
                launch_sha256=h.digest(self.launch.read_bytes()))
            self.arm()
            with patch.object(os, 'execve', side_effect=Executed):
                with self.assertRaises(Executed):
                    target.attempt(fd)
            self.assertEqual(self.launch.read_bytes(), self.original)

    def test_workers_rejects_invalid_ambiguous_or_active_shell_tokens(self):
        self.workers_launch()
        command = plistlib.loads(self.original)['ProgramArguments'][-1]
        for bad in (command.replace(str(self.script), str(self.script) + '.other'),
                    command + ' ' + shlex.quote(str(self.script)),
                    command.replace('"' + str(self.script) + '"', '"$(printf ' + str(self.script) + ')"'),
                    command + '; true', command + '\ntrue', command.replace('"' + str(self.script) + '"', '"unterminated')):
            with self.subTest(command=bad):
                self.workers_launch(bad)
                self.reject()

    def test_workers_accepts_actual_unquoted_command_shape(self):
        self.workers_launch()
        quoted = plistlib.loads(self.original)['ProgramArguments'][-1]
        command = quoted.replace('"' + str(self.script) + '"', str(self.script))
        self.workers_launch(command)
        with worker_pool.lock(self.work / 'coordinator.lock') as fd:
            self.prepare(fd)
        self.assertEqual(self.launch.read_bytes(), self.original.replace(str(self.script).encode(), str(self.target_script).encode()))

    def test_workers_default_and_legacy_require_matching_label_and_path(self):
        default = h.Handoff(self.script, self.work, self.target, baseline=self.base)
        self.assertEqual(default.launch, Path.home() / 'Library/LaunchAgents/com.siso.ci.workers.plist')
        # Existing direct argv is supported only under its legacy known label/path.
        self.handoff.launch = self.launch.with_name('unknown.plist')
        self.handoff.launch.write_bytes(self.original)
        self.handoff.launch.chmod(0o600)
        self.reject()
        self.workers_launch()
        cfg = plistlib.loads(self.original)
        cfg['ProgramArguments'][1] = '-t'
        self.original = plistlib.dumps(cfg)
        self.launch.write_bytes(self.original)
        self.request['launch_sha256'] = h.digest(self.original)
        self.arm()
        self.reject()

    def test_real_exec_retains_pid_and_sole_lock(self):
        after = self.root / 'after.py'
        after.write_text('''import os,sys,subprocess
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import runtime_handoff as h
with h.coordinator_lock(Path(sys.argv[2])) as fd:
 assert os.getpid()==int(sys.argv[3])
 p=subprocess.run([sys.executable,'-c',"import fcntl,sys; f=open(sys.argv[1],'a'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)",sys.argv[2]],capture_output=True)
 assert p.returncode!=0
 print('same PID; sole inherited lock')
''')
        before = self.root / 'before.py'
        before.write_text('''import os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import worker_pool,runtime_handoff as h
with worker_pool.lock(Path(sys.argv[2])) as fd:
 h.exec_locked(fd,sys.argv[3],[sys.argv[1],sys.argv[2],str(os.getpid())])
''')
        p = subprocess.run([sys.executable, '-B', str(before), str(CI), str(self.work / 'coordinator.lock'), str(after)],
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('same PID; sole inherited lock', p.stdout)

    def test_serve_both_idle_gate_and_self_update_before_any_dispatch(self):
        ns = runpy.run_path(str(self.script), run_name='fixture_ci')
        serve = ns['serve']
        # runpy functions retain their execution globals, distinct from the result dict.
        scope = serve.__globals__
        events = []
        controller = SimpleNamespace(active={}, tick=lambda jobs: events.append('workers') or [])
        trains = SimpleNamespace(active=False, tick=lambda: events.append('trains') or [])
        runtime = SimpleNamespace(coordinator_lock=h.coordinator_lock,
                                  Handoff=lambda script, work: self.make_handoff(script))
        scope.update(WORK=str(self.work), runtime_handoff=runtime, log=lambda *a: None,
                     self_update=lambda fd: events.append('self_update'), prune=lambda: events.append('prune'),
                     discover_jobs=lambda: [])
        with patch.object(worker_pool, 'Controller', return_value=controller), patch.dict(scope, {'Trains': lambda: trains}), \
             patch.object(scope['time'], 'sleep', side_effect=Executed):
            for workers, train in (({'busy': True}, False), ({}, True)):
                controller.active, trains.active = workers, train
                original = (self.directory / 'request.json').read_bytes()
                events.clear()
                with self.assertRaises(Executed):
                    serve(60)
                self.assertEqual(events, ['workers', 'trains'])
                self.assertEqual((self.directory / 'request.json').read_bytes(), original)
            controller.active, trains.active = {}, False
            events.clear()
            with patch.object(os, 'execve', side_effect=Executed):
                with self.assertRaises(Executed):
                    serve(60)
            self.assertEqual(events, ['self_update'])
            self.assertFalse((self.directory / 'request.json').exists())


if __name__ == '__main__':
    unittest.main()
