import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('meter', Path(__file__).resolve().parents[1] / 'scripts/efficiency-hosts.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SESSION = '12345678-1234-1234-1234-123456789abc'
INSTANCE = '12345678-1234-1234-1234-123456789def'
NOW = dt.datetime(2026, 10, 8, 12, tzinfo=dt.timezone.utc)


class Hosts(unittest.TestCase):
    def host(self, **changes):
        return dict({'pid': 12, 'name': 'fixture', 'harness': 'codex', 'session': SESSION, 'hostInstanceId': INSTANCE, 'startedAt': NOW.timestamp() * 1000, 'updatedAt': NOW.timestamp() * 1000, 'cwd': '/safe', 'tokensIn': 100, 'tokensOut': 20, 'state': 'working', 'token': 'MUST-NOT-EXPORT'}, **changes)

    def procs(self):
        return {12: {'started': NOW.timestamp() - 3, 'node': True, 'scripts': ['/safe/services/host/src/codex-host.ts']}}

    def snapshot(self, root, hosts):
        for name, host in hosts.items():
            (root / name).write_text(json.dumps(host))
        return m.snapshot(root, root / 'activity', self.procs(), NOW, NOW.replace(hour=0))

    def test_stale_pid_and_wrong_executable_are_not_capacity(self):
        self.assertEqual(m.bound(self.host(), {}), 'missing_process')
        procs = self.procs(); procs[12]['node'] = False
        self.assertEqual(m.bound(self.host(), procs), 'wrong_executable')
        procs = self.procs(); procs[12]['started'] += 100
        self.assertEqual(m.bound(self.host(), procs), 'start_mismatch')
        self.assertEqual(m.bound(self.host(), self.procs()), 'matched_script_and_start')

    def test_privacy_auth_and_bad_metadata_are_excluded(self):
        with tempfile.TemporaryDirectory(prefix='.siso-ephemeral-efficiency-hosts-') as tmp:
            root = Path(tmp)
            (root / 'name-fahmy.json').write_text('must not parse')
            result = self.snapshot(root, {'safe.json': self.host(), 'private.json': self.host(cwd='/personal/secret'), 'bad.json': []})
            self.assertEqual(result['unique_sessions'], 1)
            self.assertNotIn('MUST-NOT-EXPORT', json.dumps(result))
            self.assertNotIn('/personal/secret', json.dumps(result))
            self.assertEqual(result['skipped']['private_or_unsafe_file'], 1)
            self.assertEqual(result['skipped']['private_metadata'], 1)
            self.assertEqual(result['skipped']['invalid_metadata'], 1)

    def test_duplicate_session_counted_once_conflicting_usage_rejected(self):
        with tempfile.TemporaryDirectory(prefix='.siso-ephemeral-efficiency-hosts-') as tmp:
            result = self.snapshot(Path(tmp), {'one.json': self.host(), 'two.json': self.host(tokensIn=99)})
            self.assertEqual(result['process_bound_records'], 2)
            self.assertEqual(result['unique_sessions'], 1)
            self.assertEqual(result['unique_host_processes'], 1)
            self.assertEqual(result['rows'][0]['duplicate_hosts'], 1)
            self.assertTrue(result['rows'][0]['usage_conflict'])
            self.assertEqual(result['codex_sessions_with_usage'], 0)

    def test_lifecycle_is_scoped_deduplicated_and_not_acceptance(self):
        with tempfile.TemporaryDirectory(prefix='.siso-ephemeral-efficiency-hosts-') as tmp:
            root = Path(tmp)
            event = {'v': 1, 'id': 'a', 'at': NOW.isoformat(), 'kind': 'run.completed', 'ref': {'hostInstanceId': INSTANCE, 'sessionId': SESSION}}
            wrong = dict(event, id='b', ref={'hostInstanceId': INSTANCE, 'sessionId': 'other'})
            (root / (INSTANCE + '.jsonl')).write_text('\n'.join(json.dumps(e) for e in (event, event, wrong)))
            result = m.lifecycle(root, INSTANCE, SESSION, NOW.replace(hour=0), NOW)
            self.assertEqual(result['completed'], 1)
            self.assertEqual(result['coverage'], 'current_host_journal_only')
            self.assertEqual(m.lifecycle(root, '../outside', SESSION, NOW, NOW)['coverage'], 'missing')

    def attempts(self, task='t-0536', outcome='run.completed'):
        ref = {'hostInstanceId': INSTANCE, 'sessionId': SESSION, 'runId': 'run-1', 'taskId': task, 'workspaceId': 'ws-1'}
        usage = {'cumulative': True, 'inputTokens': 100, 'outputTokens': 10, 'cacheReadInputTokens': 80, 'cacheCreationInputTokens': None}
        start = {'v': 1, 'id': 'start', 'at': (NOW-dt.timedelta(seconds=10)).isoformat(), 'kind': 'run.started', 'ref': ref, 'usage': usage}
        end = dict(start, id='end', at=NOW.isoformat(), kind=outcome, usage=dict(usage, inputTokens=160, outputTokens=20, cacheReadInputTokens=120))
        return start, end

    def test_explicit_task_cost_is_delta_cache_not_added_twice(self):
        attempts = m.task_attempts(self.attempts(), NOW.replace(hour=0), NOW)
        self.assertEqual(attempts[0]['usage']['totalTokens'], 70)
        self.assertEqual(attempts[0]['usage']['cacheReadInputTokens'], 40)
        coverage = m.task_coverage([{'lifecycle': {'attempts': attempts}}])
        self.assertEqual(coverage['tasks']['t-0536']['tokens'], 70)
        self.assertIsNone(coverage['tokens_per_landed_change'])

    def test_failed_cancelled_attempts_stay_in_task_cost(self):
        attempts = []
        for i, outcome in enumerate(('run.completed', 'run.failed', 'run.cancelled')):
            events = self.attempts(outcome=outcome)
            for event in events:
                event['ref'] = dict(event['ref'], runId='run-' + str(i))
            attempts += m.task_attempts(events, NOW.replace(hour=0), NOW)
        result = m.task_coverage([{'lifecycle': {'attempts': attempts}}])['tasks']['t-0536']
        self.assertEqual((result['completed'], result['failed'], result['cancelled'], result['tokens']), (1, 1, 1, 210))

    def test_missing_reset_or_mismatched_usage_never_becomes_zero(self):
        for defect in ('missing-start', 'missing-end', 'reset', 'identity', 'duplicate-terminal', 'reversed-time'):
            start, end = self.attempts(); events = [start, end]
            if defect == 'missing-start': events = [end]
            elif defect == 'missing-end': end['usage'] = None
            elif defect == 'reset': end['usage']['inputTokens'] = 5
            elif defect == 'identity': start['ref'] = dict(start['ref'], taskId='t-other')
            elif defect == 'duplicate-terminal': events.append(dict(end, id='different', kind='run.failed'))
            elif defect == 'reversed-time': start['at'] = (NOW+dt.timedelta(seconds=1)).isoformat()
            attempt = m.task_attempts(events, NOW.replace(hour=0), NOW)[0]
            self.assertIsNone(attempt['usage'], defect)
            result = m.task_coverage([{'lifecycle': {'attempts': [attempt]}}])['tasks']['t-0536']
            self.assertIsNone(result['tokens'], defect)
            self.assertFalse(result['complete_usage'])

    def test_prior_day_start_is_usable_but_prior_day_terminal_excluded(self):
        start, end = self.attempts(); since = NOW-dt.timedelta(seconds=5)
        result = m.task_attempts([start,end], since, NOW)
        self.assertEqual(result[0]['usage']['totalTokens'],70)
        self.assertEqual(m.task_attempts([start,end],NOW+dt.timedelta(seconds=1),NOW+dt.timedelta(seconds=2)),[])

    def test_legacy_or_private_task_is_not_guessed_from_name(self):
        for task in (None, 'fahmy-secret', '../unsafe', 'read this prompt'):
            attempts = m.task_attempts(self.attempts(task=task), NOW.replace(hour=0), NOW)
            coverage = m.task_coverage([{'name': 't-0536', 'lifecycle': {'attempts': attempts}}])
            self.assertEqual(coverage['explicit_task_attempts'],0)
            self.assertEqual(coverage['tasks'],{})


    def pair(self):
        row = dict(self.host(), project='Agent Base', usage_conflict=False)
        a = {'schema': 1, 'scope': '/safe', 'at': (NOW - dt.timedelta(minutes=1)).isoformat(), 'rows': [row]}
        b = dict(a, at=NOW.isoformat(), rows=[dict(row, tokensIn=150, tokensOut=25, hostInstanceId='restart')])
        return a, b

    def test_interval_uses_difference_even_across_host_restart(self):
        result = m.delta(*self.pair())
        self.assertEqual((result['input_delta'], result['output_delta']), (50, 5))
        self.assertEqual(result['restarted_hosts'], 1)
        self.assertTrue(result['complete_cohort'])
        self.assertIsNone(result['tokens_per_landed_change'])

    def test_reset_or_missing_usage_is_not_negative_or_zero_cost(self):
        for value in (None, -1, True, 1):
            a, b = self.pair(); b['rows'][0]['tokensIn'] = value
            result = m.delta(a, b)
            self.assertEqual(result['matched_sessions'], 0)
            self.assertFalse(result['complete_cohort'])
            self.assertEqual(result['rejected_sessions'], [SESSION])

    def test_missing_new_and_changed_scope_are_visible(self):
        a, b = self.pair(); b['rows'][0]['session'] = 'new'
        result = m.delta(a, b)
        self.assertEqual((result['missing_sessions'], result['new_sessions']), (1, 1))
        self.assertFalse(result['complete_cohort'])
        a, b = self.pair(); b['rows'][0]['project'] = 'unmapped'
        self.assertIn('changed_scope', m.delta(a, b)['by_project'])

    def test_wrong_scope_or_time_is_rejected(self):
        a, b = self.pair(); b['scope'] = '/elsewhere'
        with self.assertRaises(ValueError): m.delta(a, b)
        a, b = self.pair(); b['at'] = a['at']
        with self.assertRaises(ValueError): m.delta(a, b)


if __name__ == '__main__':
    unittest.main(verbosity=2)
