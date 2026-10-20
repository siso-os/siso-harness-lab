"""Failure-injected rotation checks; fake MCP alone writes the isolated fixture DB."""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('fresh', str(Path(__file__).resolve().parents[1] / 'bin/seat-fresh-t3'))
spec = importlib.util.spec_from_loader(loader.name, loader)
f = importlib.util.module_from_spec(spec)
loader.exec_module(f)


class Rotation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.args = argparse.Namespace(seats=self.root / 'seats.json', db=self.root / 'state.sqlite', dry_run=False)
        self.args.seats.write_text(json.dumps({'TEST': {'thread': 'old', 'cwd': '/repo', 'keep': 'yes'},
                                             'OTHER': {'thread': 'other', 'cwd': '/other'}}))
        self.writer = sqlite3.connect(self.args.db)
        self.addCleanup(self.writer.close)
        self.writer.executescript('''
            create table orchestration_v2_projection_threads (thread_id text, payload_json text);
            create table orchestration_v2_projection_runs (thread_id text,run_id text,ordinal int,status text,completed_at text);
            create table orchestration_v2_projection_messages (thread_id text,role text,streaming int,created_at text,message_id text,payload_json text);
            create table orchestration_v2_projection_turn_items (thread_id text,turn_item_id text);
        ''')
        self.old = dict(id='old', title='Seat', projectId='project', modelSelection={'instanceId': 'codex', 'model': 'm'},
                        runtimeMode='full-access', interactionMode='default', branch='dev', worktreePath='/repo', archivedAt=None)
        self.writer.execute('insert into orchestration_v2_projection_threads values (?,?)', ('old', json.dumps(self.old)))
        self.writer.execute('insert into orchestration_v2_projection_runs values (?,?,?,?,?)', ('old', 'run', 1, 'completed', 'now'))
        self.writer.commit()
        self.db = sqlite3.connect(self.args.db.as_uri() + '?mode=ro', uri=True)
        self.addCleanup(self.db.close)
        self.calls = []
        self.lose_launch = False
        self.fail_archive = False
        self.bad_config = False
        self.client = type('Client', (), {'call': lambda _, tool, args: self.call(tool, args)})()

    def call(self, tool, args):
        self.calls.append(tool)
        if tool == 't3_thread_configuration':
            return {**self.old, **({'runtimeMode': 'wrong'} if self.bad_config else {})}
        if tool == 't3_thread_launch':
            self.assertEqual(args['modelSelection'], self.old['modelSelection'])
            self.assertEqual(args['workspaceStrategy'], {'type': 'existing_worktree', 'worktreePath': '/repo', 'branch': 'dev'})
            self.assertIn('/repo/.agents/HANDOFF.md', args['message'])
            self.writer.execute('insert into orchestration_v2_projection_threads values (?,?)', ('new', json.dumps({**self.old, 'id': 'new'})))
            self.writer.execute('insert into orchestration_v2_projection_runs values (?,?,?,?,?)', ('new', 'newrun', 1, 'running', None))
            self.writer.execute('insert into orchestration_v2_projection_messages values (?,?,?,?,?,?)',
                                ('new', 'user', 0, 'now', 'm', json.dumps({'text': args['message']})))
            self.writer.commit()
            if self.lose_launch:
                raise ValueError('lost response')
            return {'threadId': 'new'}
        if tool == 't3_thread_read':
            return {}
        if tool == 't3_thread_organize':
            # Seat map must already point at the verified replacement before archive.
            self.assertEqual(json.loads(self.args.seats.read_text())['TEST']['thread'], 'new')
            if self.fail_archive:
                raise ValueError('archive unavailable')
            self.writer.execute('update orchestration_v2_projection_threads set payload_json=? where thread_id=?',
                                (json.dumps({**self.old, 'archivedAt': 'now'}), 'old'))
            self.writer.commit()
            return {}
        self.fail(tool)

    def rotate(self):
        return f.rotate(self.db, 'TEST', self.args, self.client)

    def test_rotate_configuration_verify_map_archive_order_and_metadata(self):
        self.assertEqual(self.rotate()['status'], 'rotated')
        self.assertEqual(self.calls, ['t3_thread_configuration', 't3_thread_launch', 't3_thread_read', 't3_thread_organize'])
        seats = json.loads(self.args.seats.read_text())
        self.assertEqual(seats['TEST'], {'thread': 'new', 'previous_thread': 'old', 'cwd': '/repo', 'keep': 'yes'})
        self.assertEqual(seats['OTHER']['thread'], 'other')
        self.assertEqual(json.loads(Path(str(self.args.seats) + '.fresh.json').read_text()), {})

    def test_lost_launch_reconciles_receipt_without_duplicate(self):
        self.lose_launch = True
        with self.assertRaisesRegex(ValueError, 'lost response'):
            self.rotate()
        self.assertEqual(self.rotate()['thread'], 'new')
        self.assertEqual(self.calls.count('t3_thread_launch'), 1)

    def test_archive_failure_retries_same_replacement_after_map_update(self):
        self.fail_archive = True
        with self.assertRaisesRegex(ValueError, 'archive unavailable'):
            self.rotate()
        self.fail_archive = False
        self.assertEqual(self.rotate()['thread'], 'new')
        self.assertEqual(self.calls.count('t3_thread_launch'), 1)

    def test_active_queued_and_failed_latest_turn_refused(self):
        for status in ('running', 'queued', 'waiting', 'preparing', 'starting', 'failed', 'interrupted'):
            self.writer.execute('update orchestration_v2_projection_runs set status=?', (status,))
            self.writer.commit()
            with self.assertRaises(ValueError):
                self.rotate()
        self.assertEqual(self.calls, [])

    def test_configuration_drift_never_launches(self):
        self.bad_config = True
        with self.assertRaisesRegex(ValueError, 'Configuration changed'):
            self.rotate()
        self.assertEqual(self.calls, ['t3_thread_configuration'])

    def test_busy_after_launch_retains_old_and_resumes(self):
        original = self.client.call
        def changed(tool, args):
            result = original(tool, args)
            if tool == 't3_thread_read':
                self.writer.execute("update orchestration_v2_projection_runs set status='queued' where thread_id='old'")
                self.writer.commit()
            return result
        self.client.call = changed
        with self.assertRaisesRegex(ValueError, 'active/queued'):
            self.rotate()
        self.assertEqual(json.loads(self.args.seats.read_text())['TEST']['thread'], 'old')
        self.assertNotIn('t3_thread_organize', self.calls)

    def test_all_long_threshold_agent_zero_and_busy_skip(self):
        seats = json.loads(self.args.seats.read_text())
        seats['Agent Zero'] = {'thread': f.AGENT_ZERO, 'cwd': '/a0'}
        self.args.seats.write_text(json.dumps(seats))
        self.writer.executemany('insert into orchestration_v2_projection_turn_items values (?,?)', [('old', str(i)) for i in range(800)])
        self.writer.commit()
        with patch.object(f, 'rotate') as rotate:
            f.all_long(self.args)
            rotate.assert_not_called()
            self.writer.execute("insert into orchestration_v2_projection_turn_items values ('old','801')")
            self.writer.commit()
            rotate.return_value = {'status': 'rotated'}
            f.all_long(self.args)
            self.assertEqual(rotate.call_args.args[1], 'TEST')
            self.assertEqual(rotate.call_count, 1)


class Authentication(unittest.TestCase):
    def test_nonlocal_origin_rejected_before_credentials(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / 'server-runtime.json').write_text(json.dumps({'origin': 'http://example.com'}))
            with self.assertRaisesRegex(ValueError, 'loopback'):
                f.Mcp(argparse.Namespace(db=root / 'state.sqlite', seats=root / 'seats.json'))

    def test_oauth_pkce_cli_output_private_and_cache_mode(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            client = object.__new__(f.Mcp)
            client.origin = 'http://127.0.0.1:5490'
            client.cache = root / 'auth.json'
            calls = []
            def post(path, body, form=False, headers=None):
                calls.append((path, body))
                if path.endswith('/register'):
                    return {}, json.dumps({'client_id': 'client'})
                if path.endswith('/decision'):
                    self.assertEqual(body['decision']['code'], 'private-grant')
                    self.assertEqual(body['authorization']['code_challenge_method'], 'S256')
                    state = body['authorization']['state']
                    return {}, json.dumps({'redirectTo': 'http://127.0.0.1/seat-fresh-callback?code=code&state=' + state})
                self.assertTrue(form)
                self.assertEqual(body['code'], 'code')
                return {}, json.dumps({'access_token': 'private-token', 'expires_in': 3600})
            client.post = post
            result = type('Result', (), {'returncode': 0, 'stdout': '{"credential":"private-grant"}'})()
            with patch.object(f.subprocess, 'run', return_value=result) as run:
                client.authorize(root)
                argv = run.call_args.args[0]
                self.assertIn('pairing', argv)
                self.assertNotIn('private-grant', argv)
            self.assertEqual(client.token, 'private-token')
            self.assertEqual(client.cache.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(calls), 3)

    def test_mcp_sse_response_and_session_header(self):
        client = object.__new__(f.Mcp)
        client.token, client.session = 'secret', None
        def post(path, body, **kwargs):
            self.assertEqual(kwargs['headers']['Authorization'], 'Bearer secret')
            return {'mcp-session-id': 'session'}, 'event: message\ndata: ' + json.dumps({
                'id': body['id'], 'jsonrpc': '2.0', 'result': {'ok': True}}) + '\n\n'
        client.post = post
        self.assertEqual(client.rpc('test', {}), {'ok': True})
        self.assertEqual(client.session, 'session')


class Installation(unittest.TestCase):
    def test_revisioned_install_and_launchd_plist(self):
        import runpy
        import plistlib
        import contextlib
        import io
        source = Path(f.__file__).resolve()
        def git(argv, **kwargs):
            return 'a' * 40 + '\n' if 'rev-parse' in argv else source.read_bytes()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            with patch.object(Path, 'home', return_value=root), patch.object(f.subprocess, 'check_output', side_effect=git), patch.object(f.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(source.with_name('seat-fresh-t3-install')))
            target = root / '.local/lib/siso-harness-lab' / ('a' * 12) / 'bin/seat-fresh-t3'
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertFalse(target.is_symlink())
            job = plistlib.loads((root / 'Library/LaunchAgents/com.siso.seat-fresh-t3.plist').read_bytes())
            self.assertEqual(job['StartInterval'], 900)
            self.assertEqual(job['ProgramArguments'], [str(root / '.local/bin/seat-fresh-t3'), '--all-long'])
            self.assertEqual(job['StandardOutPath'], str(root / '.local/state/agent-base/seat-fresh.log'))
            self.assertEqual((root / '.local/state/agent-base/seat-fresh.log').stat().st_mode & 0o777, 0o600)
            self.assertEqual(run.call_args.args[0][1], 'bootstrap')


if __name__ == '__main__':
    unittest.main()
