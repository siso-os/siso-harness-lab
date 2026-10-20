#!/usr/bin/env python3
"""On-demand Claude quota + Codex usage report. Counts only; no prompts or credentials saved.

heavy -- python3 tokens/plan-watch.py --since 2026-10-16T16:27:00+07:00 --sample
Quota forecasts use same-reset percentage deltas, never API list dollars. Samples are ignored JSONL.
Codex token_usage_record wins over cumulative token_count within each session (no double count).
"""
import argparse
import collections
import datetime as dt
import importlib.machinery
import importlib.util
import json
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parent
FIELDS = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens')


def epoch(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def codex_scan(root, since, until):
    rows = collections.defaultdict(collections.Counter)
    limits = {}
    sessions = set()
    for path in sorted(pathlib.Path(root).rglob('*.jsonl')):
        if path.stat().st_mtime < since:
            continue
        sid, model, previous = path.stem, 'unknown', {}
        records, fallback = [], []
        try:
            with path.open(errors='replace') as stream:
                for line in stream:
                    if not any(k in line for k in ('"session_meta"', '"turn_context"', '"token_usage_record"', '"token_count"')):
                        continue
                    try:
                        e = json.loads(line)
                        p = e.get('payload') or {}
                        at = epoch(e['timestamp'])
                    except (ValueError, KeyError, TypeError):
                        continue
                    typ = e.get('type')
                    if typ == 'session_meta':
                        sid = p.get('id') or sid
                    if typ == 'turn_context':
                        model = p.get('model') or 'unknown'
                    if typ == 'token_usage_record' and p.get('usage'):
                        records.append((at, model, p['usage']))
                    if typ == 'event_msg' and p.get('type') == 'token_count':
                        total = (p.get('info') or {}).get('total_token_usage')
                        if total:
                            # Duplicate cumulative events contribute zero; counter resets start a new segment.
                            delta = {k: max(0, total.get(k, 0) - previous.get(k, 0)) for k in FIELDS}
                            if total.get('input_tokens', 0) < previous.get('input_tokens', 0):
                                delta = {k: total.get(k, 0) for k in FIELDS}
                            previous = total
                            if any(delta.values()):
                                fallback.append((at, model, delta))
                        r = p.get('rate_limits')
                        if r and at <= until:
                            key = r.get('limit_id') or 'unknown'
                            if at > limits.get(key, {}).get('epoch', 0):
                                limits[key] = {'epoch': at, 'observed_at': e['timestamp'], 'rate_limits': r}
        except OSError:
            continue
        if sid in sessions:
            continue
        sessions.add(sid)
        for at, model, u in records or fallback:
            if since <= at < until:
                row = rows[(sid, model)]
                row['calls'] += 1
                for k in FIELDS:
                    row[k] += u.get(k, 0) or 0
    return [{'session': sid, 'model': model, **r} for (sid, model), r in rows.items()], limits


def same_reset(left, right):
    if not left or not right:
        return False
    try:
        # The usage endpoint recomputes fractional seconds (observed +/-0.3s).
        return abs(epoch(left) - epoch(right)) < 60
    except (ValueError, TypeError):
        return left == right


def quota_forecast(current, samples, deadline):
    result = {}
    for login, row in current['claude'].items():
        wk = row.get('seven_day') or {}
        used, reset = wk.get('utilization'), wk.get('resets_at')
        if used is None or not reset:
            continue
        candidates = [s for s in samples if s['at'] < current['at'] and
                      same_reset((s.get('claude', {}).get(login, {}).get('seven_day') or {}).get('resets_at'), reset)]
        remaining = 100 - used
        result[login] = {'remaining_percent': remaining, 'forecast': 'insufficient samples'}
        if not candidates:
            continue
        base = min(candidates, key=lambda s: s['at'])
        hours = (epoch(current['at']) - epoch(base['at'])) / 3600
        delta = used - base['claude'][login]['seven_day']['utilization']
        if hours <= 0 or delta < 0:
            continue
        rate = delta / hours
        horizon = max(0, (deadline - epoch(current['at'])) / 3600)
        # Report a conservative one-percentage-point measurement-resolution allowance.
        high_rate = (delta + 1) / hours
        result[login].update(baseline_at=base['at'], percent_per_hour=rate,
                            resolution_upper_percent_per_hour=high_rate,
                            hours_to_empty=remaining / rate if rate else None,
                            deadline_required_percent=rate * horizon,
                            deadline_budget_percent_per_hour=remaining / horizon if horizon else None,
                            forecast=('exceeds deadline budget' if rate * horizon > remaining else
                                      'fits at observed burn' if high_rate * horizon <= remaining else
                                      'too little movement to establish runway'))
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--since', required=True)
    ap.add_argument('--deadline', default='2026-10-20T20:00:00+07:00')
    ap.add_argument('--sample', action='store_true')
    ap.add_argument('--samples', type=pathlib.Path, default=HERE / 'data/plan-samples.jsonl')
    a = ap.parse_args()
    since, now = epoch(a.since), time.time()
    ledger = load('ledger', HERE / 'ledger.py')
    cc = load('credits', HERE.parent / 'bin/claude-credits')
    result = {'at': dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(), 'since': a.since,
              'coverage': 'local transcripts; Claude quotas account-wide; Codex latest local event, freshness shown',
              'claude': {}, 'claude_local': {}}
    for login, cfg in cc.LOGINS:
        try:
            token = cc.token(cfg)
            if not token:
                raise ValueError('missing credential')
            usage = cc.get('/api/oauth/usage', token)
            result['claude'][login] = {k: usage.get(k) for k in ('five_hour', 'seven_day')}
        except Exception as e:
            result['claude'][login] = {'error': f'{type(e).__name__} {getattr(e, "code", "")}'.strip()}
    seats = ledger.seat_map()
    groups = collections.defaultdict(collections.Counter)
    for c in ledger.scan(since, now):
        ledger.cost(c)
        row = groups[c['login']]
        row['calls'] += 1
        row['list_usd'] += c['total']
    for login, row in groups.items():
        row['list_usd_per_hour'] = row['list_usd'] / max((now - since) / 3600, 1e-9)
        result['claude_local'][login] = dict(row)
    rows, limits = codex_scan(ledger.CODEX, since, now)
    for row in rows:
        row['seat'] = seats.get(row['session'], 'unmapped')
    result['codex'] = {'usage': rows, 'limits': limits, 'pricing': 'not estimated; quota is not token-count capacity'}
    samples = []
    if a.samples.exists():
        for line in a.samples.read_text().splitlines():
            try:
                s = json.loads(line)
                if epoch(s['at']) >= since:
                    samples.append(s)
            except (ValueError, KeyError):
                continue
    result['forecast'] = quota_forecast(result, samples, epoch(a.deadline))
    if a.sample:
        a.samples.parent.mkdir(parents=True, exist_ok=True)
        with a.samples.open('a') as f:
            f.write(json.dumps({k: result[k] for k in ('at', 'since', 'claude')}) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
