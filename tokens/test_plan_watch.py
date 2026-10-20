import importlib.util
import json
import pathlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('watch', pathlib.Path(__file__).with_name('plan-watch.py'))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class PlanWatchTests(unittest.TestCase):
    def scan(self, events):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, 'session.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
            return w.codex_scan(tmp, 20, 40)

    def event(self, typ, sec, payload):
        return {'type': typ, 'timestamp': f'1970-01-01T00:00:{sec:02d}Z', 'payload': payload}

    def count(self, sec, total):
        return self.event('event_msg', sec, {'type': 'token_count', 'info': {'total_token_usage': {'input_tokens': total}}})

    def test_explicit_records_are_not_added_to_cumulative_events(self):
        events = [self.event('turn_context', 10, {'model': 'gpt-6-astra'}), self.count(10, 100),
                  self.event('token_usage_record', 25, {'usage': {'input_tokens': 30}}), self.count(26, 130)]
        rows, _ = self.scan(events)
        self.assertEqual(rows[0]['input_tokens'], 30)
        self.assertEqual(rows[0]['calls'], 1)
        self.assertEqual(rows[0]['model'], 'gpt-6-astra')

    def test_legacy_baseline_duplicates_and_reset(self):
        rows, _ = self.scan([self.count(10, 100), self.count(21, 130), self.count(22, 130), self.count(30, 10)])
        self.assertEqual(rows[0]['input_tokens'], 40)
        self.assertEqual(rows[0]['calls'], 2)

    def test_latest_limit_per_bucket_and_freshness(self):
        events = [self.event('event_msg', n, {'type': 'token_count', 'rate_limits':
                  {'limit_id': k, 'primary': {'used_percent': pct, 'window_minutes': 10080}}})
                  for n, k, pct in [(21, 'codex', 10), (30, 'codex', 11), (31, 'other', 0), (45, 'codex', 99)]]
        _, limits = self.scan(events)
        self.assertEqual(limits['codex']['rate_limits']['primary']['used_percent'], 11)
        self.assertEqual(limits['codex']['epoch'], 30)
        self.assertEqual(len(limits), 2)

    def sample(self, at, used, reset='same'):
        return {'at': at, 'claude': {'fuze': {'seven_day': {'utilization': used, 'resets_at': reset}}}}

    def test_quota_rate_uses_delta_not_list_dollars(self):
        before = self.sample('2026-10-16T09:30:00Z', 2)
        after = self.sample('2026-10-16T10:30:00Z', 4)
        result = w.quota_forecast(after, [before], w.epoch('2026-10-20T13:00:00Z'))['fuze']
        self.assertEqual(result['percent_per_hour'], 2)
        self.assertEqual(result['hours_to_empty'], 48)
        self.assertEqual(result['forecast'], 'exceeds deadline budget')

    def test_usage_endpoint_reset_jitter_is_same_window(self):
        self.assertTrue(w.same_reset('2026-10-20T12:59:59.786493Z', '2026-10-20T13:00:00.082286Z'))
        self.assertFalse(w.same_reset('2026-10-20T13:00:00Z', '2026-10-27T13:00:00Z'))

    def test_quota_reset_and_zero_delta_do_not_invent_runway(self):
        before = self.sample('2026-10-16T09:30:00Z', 0)
        after = self.sample('2026-10-16T10:30:00Z', 0)
        r = w.quota_forecast(after, [before], w.epoch('2026-10-23T13:00:00Z'))['fuze']
        self.assertIsNone(r['hours_to_empty'])
        self.assertEqual(r['forecast'], 'too little movement to establish runway')
        after['claude']['fuze']['seven_day']['resets_at'] = 'changed'
        r = w.quota_forecast(after, [before], w.epoch('2026-10-23T13:00:00Z'))['fuze']
        self.assertEqual(r['forecast'], 'insufficient samples')


if __name__ == '__main__':
    unittest.main()
