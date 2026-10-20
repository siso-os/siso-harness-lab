"""SSH transport fixtures; isolated pools, no network or user checkout writes."""
import json
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'bin/heavy'


class RemoteHeavy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='heavy-remote-')
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.home = self.root / 'remote-home'
        remote = self.home / 'SISO_Workspace/SISO_Agents/siso-harness-lab/bin/heavy'
        remote.parent.mkdir(parents=True)
        shutil.copy2(SOURCE, remote)
        self.cwd = self.root / "work ' $(touch INJECTED); dir\nnext"
        self.cwd.mkdir()
        self.log = self.root / 'ssh.json'
        self.pool = self.root / 'sender-pool'
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'HEAVY_DIR': str(self.pool), 'HEAVY_SLOTS': '1', 'HEAVY_QOS': 'off',
                    'SSH_LOG': str(self.log), 'REMOTE_HOME': str(self.home)}
        self.env.pop('SISO_HEAVY_LEASE', None)
        self.env.pop('HEAVY_CLASS', None)
        self.mock = self.bin / 'ssh'
        self.mock.write_text('#!' + sys.executable + '''
import json,os,sys
with open(os.environ['SSH_LOG'],'w') as f:json.dump(sys.argv[1:],f)
if os.environ.get('SSH_FAIL'):sys.exit(255)
env=dict(os.environ)
for name in ('HEAVY_DIR','HEAVY_SLOTS','SISO_HEAVY_LEASE'):env.pop(name,None)
env['HOME']=env['REMOTE_HOME']
os.execve('/bin/sh',['sh','-c',sys.argv[-1]],env)
''')
        self.mock.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_heavy(self, args, **kwargs):
        return sp.run([sys.executable, '-B', str(SOURCE), *args], env=self.env,
                      capture_output=True, text=True, timeout=10, **kwargs)

    def remote(self, *payload):
        return ['--on', 'mini', '--cwd', str(self.cwd), '--', *payload]

    def test_roundtrip_streams_arguments_status_and_remote_slot(self):
        args = ['', 'a b', "single'quote", '"double"', '$(touch INJECTED)', '; false',
                'a\nb', '\\', '*', '--on', 'é']
        code = """import json,os,sys
print(json.dumps([os.getcwd(),sys.argv[1:],sys.stdin.read(),json.loads(os.environ['SISO_HEAVY_LEASE'])['root']]))
print('payload-stderr',file=sys.stderr)
sys.exit(23)
"""
        r = self.run_heavy(self.remote(sys.executable, '-c', code, *args), input='stdin\n')
        self.assertEqual(r.returncode, 23, r.stderr)
        cwd, actual, stdin, pool = json.loads(r.stdout)
        self.assertEqual(cwd, str(self.cwd.resolve()))
        self.assertEqual(actual, args)
        self.assertEqual(stdin, 'stdin\n')
        self.assertEqual(pool, str((self.home / '.cache/siso-heavy').resolve()))
        self.assertIn('payload-stderr', r.stderr)
        self.assertFalse(self.pool.exists())
        self.assertFalse((self.cwd / 'INJECTED').exists())
        self.assertTrue((Path(pool) / 'ticket').exists())
        ssh = json.loads(self.log.read_text())
        self.assertEqual(ssh[:-1], ['-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                                  '-o', 'ConnectionAttempts=1', '-o', 'RemoteCommand=none', 'mac-mini'])

    def test_connection_failure_no_local_payload_or_admission(self):
        self.env['SSH_FAIL'] = '1'
        marker = self.root / 'payload'
        r = self.run_heavy(self.remote(sys.executable, '-c',
                                      'import pathlib,sys;pathlib.Path(sys.argv[1]).touch()', str(marker)))
        self.assertEqual(r.returncode, 255)
        self.assertFalse(marker.exists())
        self.assertFalse(self.pool.exists())

    def test_explicit_quick_class_reaches_remote_reserved_slot(self):
        code = "import json,os;print(json.loads(os.environ['SISO_HEAVY_LEASE'])['slot'])"
        r = self.run_heavy(['--class', 'quick', *self.remote(sys.executable, '-c', code)])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), '4')
        self.assertFalse(self.pool.exists())

    def test_missing_ssh_no_fallback(self):
        self.mock.unlink()
        self.env['PATH'] = str(self.bin)
        r = self.run_heavy(self.remote('/usr/bin/true'))
        self.assertEqual(r.returncode, 127)
        self.assertFalse(self.pool.exists())

    def test_missing_remote_cwd_no_payload(self):
        self.cwd.rmdir()
        r = self.run_heavy(self.remote('/usr/bin/true'))
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.pool.exists())
        self.assertFalse((self.home / '.cache/siso-heavy').exists())

    def test_invalid_remote_syntax_does_not_admit(self):
        for args in (['--on'], ['--on', 'elsewhere', '--cwd', '/', '--', 'true'],
                     ['--on', 'mini', '--cwd', 'relative', '--', 'true'],
                     ['--on', 'mini', '--cwd', '/', '--'],
                     ['--on', 'mini', '--cwd', '/', 'true']):
            with self.subTest(args=args):
                self.assertEqual(self.run_heavy(args).returncode, 2)
                self.assertFalse(self.log.exists())
                self.assertFalse(self.pool.exists())

    def test_sender_payload_count_before_after(self):
        code = "import os;print('remote' if os.environ.get('HOME') == os.environ['REMOTE_HOME'] else 'sender')"
        before = self.run_heavy(['--', sys.executable, '-c', code])
        ticket = (self.pool / 'ticket').read_bytes()
        after = self.run_heavy(self.remote(sys.executable, '-c', code))
        self.assertEqual((before.returncode, after.returncode), (0, 0))
        self.assertEqual(before.stdout.strip(), 'sender')
        self.assertEqual(after.stdout.strip(), 'remote')
        self.assertEqual((self.pool / 'ticket').read_bytes(), ticket)
        print('placement fixture: sender payload executions 1 -> 0; remote payload executions 0 -> 1')


if __name__ == '__main__':
    unittest.main()
