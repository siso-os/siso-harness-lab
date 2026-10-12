#!/usr/bin/env python3
"""On-demand hosted-agent capacity/usage coverage; no conversations or auth exported.

Counters are provider-reported cumulative input/output, including cached input;
interval differences are not billed tokens. A completed turn is not a landed change.
Read current host metadata plus fixed-schema lifecycle journals only. No scheduling,
network requests, process control, directory creation or implicit output writes.
"""
import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess

PRIVATE = ('fahmy', 'bykonz', 'whatsapp', 'personal')
HOME = Path.home()
UUID = re.compile(r'^[0-9a-fA-F-]{36}$')


def private(value):
    return any(word in str(value).lower() for word in PRIVATE)


def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def processes():
    """Keep argv in memory only; emit no arbitrary arguments or environment."""
    env = dict(os.environ, LC_ALL='C')
    result = subprocess.run(['ps', '-axo', 'pid=,lstart=,comm='], capture_output=True, text=True, check=True, env=env, timeout=20)
    args = subprocess.run(['ps', '-axo', 'pid=,args='], capture_output=True, text=True, check=True, env=env, timeout=20)
    commands = {}
    for line in args.stdout.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) == 2 and fields[0].isdigit():
            commands[int(fields[0])] = fields[1]
    rows = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 6)
        if len(fields) != 7:
            continue
        try:
            pid = int(fields[0])
            started = dt.datetime.strptime(' '.join(fields[1:6]), '%a %b %d %H:%M:%S %Y').astimezone().timestamp()
            tokens = shlex.split(commands.get(pid, ''))
        except (ValueError, OverflowError):
            continue
        scripts = [t for t in tokens if t.endswith(('/services/host/src/codex-host.ts', '/services/host/src/host.ts'))]
        rows[pid] = {'started': started, 'node': Path(fields[6]).name in ('node', 'nodejs'), 'scripts': scripts}
    return rows


def bound(host, procs):
    pid = count(host.get('pid'))
    proc = procs.get(pid)
    start = host.get('startedAt')
    if not proc:
        return 'missing_process'
    expected = 'codex-host.ts' if host.get('harness') == 'codex' else 'host.ts'
    if not proc['node'] or not any(Path(s).name == expected for s in proc['scripts']):
        return 'wrong_executable'
    if not isinstance(start, (int, float)) or not math.isfinite(start):
        return 'missing_start'
    # Producer starts a few seconds after node. Reject stale metadata/PID reuse.
    if not -1 <= start / 1000 - proc['started'] <= 60:
        return 'start_mismatch'
    return 'matched_script_and_start'



def run_usage(start, end):
    """Subtract explicit same-run cumulative snapshots; cached input is a subset."""
    if not isinstance(start, dict) or not isinstance(end, dict) or start.get('cumulative') is not True or end.get('cumulative') is not True:
        return None
    keys = ('inputTokens', 'outputTokens', 'cacheReadInputTokens', 'cacheCreationInputTokens')
    result = {}
    for key in keys:
        a, b = count(start.get(key)), count(end.get(key))
        if key in ('inputTokens', 'outputTokens') and (a is None or b is None or b < a):
            return None
        result[key] = b - a if a is not None and b is not None and b >= a else None
    if result['cacheReadInputTokens'] is not None and result['cacheReadInputTokens'] > result['inputTokens']:
        return None
    result['totalTokens'] = result['inputTokens'] + result['outputTokens']
    return result


def task_attempts(events, since, now):
    """Every explicit attempt stays visible, including failed/cancelled or unknown cost."""
    runs = {}
    for event in events:
        ref = event.get('ref') or {}
        run = ref.get('runId')
        if not isinstance(run, str) or not run or len(run) > 128:
            continue
        row = runs.setdefault(run, {'start': None, 'end': None, 'conflict': False})
        kind = event.get('kind')
        if kind == 'run.started':
            if row['start'] is not None and row['start'] != event:
                row['conflict'] = True
            row['start'] = event
        elif kind in ('run.completed', 'run.failed', 'run.cancelled', 'runtime.failed'):
            if row['end'] is not None and row['end'] != event:
                row['conflict'] = True
            row['end'] = event
    attempts = []
    for run, pair in runs.items():
        end, start = pair['end'], pair['start']
        if end is None:
            continue
        try:
            at = dt.datetime.fromisoformat(end['at'].replace('Z', '+00:00'))
            if at.tzinfo is None or not since <= at <= now:
                continue
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        ref = end['ref']
        task = ref.get('taskId')
        if not isinstance(task, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', task) or private(task):
            task = None
        workspace = ref.get('workspaceId')
        if not isinstance(workspace, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', workspace):
            workspace = None
        identity_ok = start is not None and all(start.get('ref', {}).get(k) == ref.get(k) for k in ('runId', 'sessionId', 'hostInstanceId', 'taskId', 'workspaceId'))
        if identity_ok:
            try:
                began = dt.datetime.fromisoformat(start['at'].replace('Z', '+00:00'))
                identity_ok = began.tzinfo is not None and began <= at
            except (KeyError, ValueError, TypeError, AttributeError):
                identity_ok = False
        delta = None if pair['conflict'] or not identity_ok else run_usage(start.get('usage'), end.get('usage'))
        attempts.append({'runId': run, 'taskId': task, 'workspaceId': workspace,
                         'outcome': end['kind'], 'usage': delta,
                         'usage_status': 'measured_delta' if delta is not None else 'unknown',
                         'identity_conflict': pair['conflict'] or (start is not None and not identity_ok)})
    return attempts


def task_coverage(rows):
    tasks = {}; total = identified = measured = 0
    for row in rows:
        for attempt in row.get('lifecycle', {}).get('attempts', []):
            total += 1
            task = attempt.get('taskId')
            if not task:
                continue
            identified += 1
            group = tasks.setdefault(task, {'attempts': 0, 'completed': 0, 'failed': 0, 'cancelled': 0, 'measured_attempts': 0, 'known_tokens': 0})
            group['attempts'] += 1
            outcome = attempt['outcome'].split('.')[-1]
            group['failed' if outcome == 'failed' else outcome] += 1
            usage = attempt.get('usage')
            if usage:
                measured += 1; group['measured_attempts'] += 1; group['known_tokens'] += usage['totalTokens']
    for group in tasks.values():
        group['complete_usage'] = group['measured_attempts'] == group['attempts']
        group['tokens'] = group['known_tokens'] if group['complete_usage'] else None
    return {'terminal_attempts': total, 'explicit_task_attempts': identified, 'measured_task_attempts': measured,
            'tasks': tasks, 'tokens_per_landed_change': None,
            'limit': 'Current host journals only. Known tokens retain failed and cancelled attempts; missing usage is unknown. Task IDs identify work but do not establish acceptance or a live landing.'}

def lifecycle(activity_root, instance, session, since, now):
    result = {'started': 0, 'completed': 0, 'failed': 0, 'cancelled': 0, 'coverage': 'missing'}
    if not isinstance(instance, str) or not UUID.fullmatch(instance):
        return result
    path = activity_root / (instance + '.jsonl')
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_200_000:
            return result
    except OSError:
        return result
    seen = set(); events = []
    try:
        for line in path.read_text().splitlines():
            try:
                event = json.loads(line)
                ref = event.get('ref') or {}
                stamp = dt.datetime.fromisoformat(event.get('at', '').replace('Z', '+00:00'))
                if stamp.tzinfo is None or stamp > now:
                    continue
                if event.get('v') != 1 or ref.get('hostInstanceId') != instance or ref.get('sessionId') != session:
                    continue
                ident = event.get('id')
                if not isinstance(ident, str) or ident in seen:
                    continue
                seen.add(ident)
                events.append(event)
                if stamp < since:
                    continue
                kind = event.get('kind')
                if kind in ('run.started', 'run.completed', 'run.failed', 'run.cancelled'):
                    result[kind.split('.')[1]] += 1
            except (ValueError, TypeError, AttributeError):
                continue
        result['coverage'] = 'current_host_journal_only'
        result['attempts'] = task_attempts(events, since, now)
    except OSError:
        pass
    return result


def snapshot(hosts, activity, procs, now, since):
    rows = {}; skipped = {}; candidates = 0; bound_pids = set()
    for path in sorted(hosts.glob('*.json')):
        reason = None
        try:
            if private(path) or path.is_symlink() or path.stat().st_size > 256_000:
                reason = 'private_or_unsafe_file'
            else:
                host = json.loads(path.read_text())
                if not isinstance(host, dict):
                    raise ValueError()
        except (ValueError, OSError):
            reason = 'invalid_metadata'
        if not reason and private(' '.join(str(host.get(k, '')) for k in ('cwd', 'name', 'label'))):
            reason = 'private_metadata'
        if not reason:
            reason = bound(host, procs)
            if reason == 'matched_script_and_start':
                reason = None
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        session = host.get('session')
        if not isinstance(session, str) or not UUID.fullmatch(session):
            skipped['missing_session'] = skipped.get('missing_session', 0) + 1
            continue
        candidates += 1
        bound_pids.add(host['pid'])
        cwd = str(host.get('cwd', ''))
        projects = [HOME / 'SISO_Workspace/SISO_Agency/apps/siso-internal-labs/siso-internal-labs-agent-base', HOME / 'SISO_Workspace/_data/worktrees/siso-internal-labs-agent-base']
        project = 'Agent Base' if any(Path(cwd) == p or p in Path(cwd).parents for p in projects) else 'unmapped'
        row = {k: host.get(k) for k in ('pid', 'name', 'session', 'harness', 'model', 'state', 'hostInstanceId', 'workspaceId', 'taskId', 'parentSession', 'startedAt', 'updatedAt')}
        if not isinstance(row.get('taskId'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', row['taskId']) or private(row['taskId']):
            row['taskId'] = None
        row.update(project=project, tokensIn=count(host.get('tokensIn')), tokensOut=count(host.get('tokensOut')), process_binding='matched_script_and_start', duplicate_hosts=0, usage_conflict=False)
        row['lifecycle'] = lifecycle(activity, row['hostInstanceId'], session, since, now)
        old = rows.get(session)
        if old:
            latest, earlier = (row, old) if (row.get('updatedAt') or 0) >= (old.get('updatedAt') or 0) else (old, row)
            latest['duplicate_hosts'] = old['duplicate_hosts'] + 1
            latest['usage_conflict'] = old['usage_conflict'] or (latest['tokensIn'], latest['tokensOut']) != (earlier['tokensIn'], earlier['tokensOut'])
            latest['state'] = 'working' if 'working' in (row['state'], old['state']) else latest['state']
            rows[session] = latest
        else:
            rows[session] = row
    ordered = sorted(rows.values(), key=lambda r: r['session'])
    return {'schema': 1, 'at': now.isoformat(), 'since': since.isoformat(), 'scope': str(hosts.resolve()), 'process_bound_records': candidates, 'unique_host_processes': len(bound_pids), 'unique_sessions': len(ordered), 'working_sessions': sum(r['state'] == 'working' for r in ordered), 'codex_sessions_with_usage': sum(r['harness'] == 'codex' and r['tokensIn'] is not None and r['tokensOut'] is not None and not r['usage_conflict'] for r in ordered), 'skipped': skipped, 'task_usage': task_coverage(ordered), 'rows': ordered, 'limits': ['Current process-bound hosts only; terminated hosts and rotated journals are not complete historical coverage.', 'PID script and start-time match has 60s startup tolerance; it is not cryptographic process attestation.', 'Cumulative provider input/output counters include cache use, not billed tokens; never sum lifetime counters as daily use.', 'Working state and completed lifecycle turns do not prove useful work or landed changes; no token-per-landed-change ratio is inferred.']}


def delta(before, after):
    if before.get('schema') != 1 or after.get('schema') != 1 or before.get('scope') != after.get('scope'):
        raise ValueError('baseline schema and scope must match')
    start = dt.datetime.fromisoformat(before['at']); end = dt.datetime.fromisoformat(after['at'])
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise ValueError('snapshot times must be aware and increasing')
    prior = {r['session']: r for r in before['rows'] if r.get('harness') == 'codex'}
    current = {r['session']: r for r in after['rows'] if r.get('harness') == 'codex'}
    result = {'from': before['at'], 'to': after['at'], 'matched_sessions': 0, 'input_delta': 0, 'output_delta': 0, 'new_sessions': len(current.keys() - prior.keys()), 'missing_sessions': len(prior.keys() - current.keys()), 'rejected_sessions': [], 'restarted_hosts': 0, 'by_project': {}, 'tokens_per_landed_change': None, 'complete_cohort': False}
    for session in sorted(prior.keys() & current.keys()):
        old, new = prior[session], current[session]
        values = [count(row.get(k)) for row in (old, new) for k in ('tokensIn', 'tokensOut')]
        if None in values or old.get('usage_conflict') or new.get('usage_conflict') or values[2] < values[0] or values[3] < values[1]:
            result['rejected_sessions'].append(session)
            continue
        di, do = values[2] - values[0], values[3] - values[1]
        result['input_delta'] += di; result['output_delta'] += do; result['matched_sessions'] += 1
        result['restarted_hosts'] += old.get('hostInstanceId') != new.get('hostInstanceId')
        project = new['project'] if old['project'] == new['project'] else 'changed_scope'
        group = result['by_project'].setdefault(project, {'sessions': 0, 'input_delta': 0, 'output_delta': 0})
        group['sessions'] += 1; group['input_delta'] += di; group['output_delta'] += do
    result['complete_cohort'] = not (result['new_sessions'] or result['missing_sessions'] or result['rejected_sessions']) and result['matched_sessions'] > 0
    result['limit'] = 'Observed surviving-session interval counters, not calendar-day billing or all completed work. Project uses cwd, not ticket attribution. Complete cohort means these two snapshot populations only.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hosts', type=Path, default=HOME / '.local/state/agent-base/hosts')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    if private(args.hosts) or args.hosts.is_symlink() or not args.hosts.is_dir():
        parser.error('hosts directory missing or disallowed')
    now = dt.datetime.now().astimezone(); since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result = snapshot(args.hosts, args.hosts.parent / 'activity', processes(), now, since)
    memory = subprocess.run(['memory_pressure'], capture_output=True, text=True, timeout=20)
    match = re.search(r'System-wide memory free percentage:\s*(\d+)%', memory.stdout)
    free = int(match.group(1)) if match else None
    result['resources'] = {'load': list(os.getloadavg()), 'cores': os.cpu_count(), 'memory_free_pct': free}
    result['resources']['one_minute_headroom'] = free is not None and free > 30 and result['resources']['load'][0] < (os.cpu_count() or 1)
    result['resources']['sustained_useful_capacity'] = None
    if args.baseline:
        if private(args.baseline) or args.baseline.is_symlink():
            parser.error('baseline disallowed')
        try:
            result['delta'] = delta(json.loads(args.baseline.read_text()), result)
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
