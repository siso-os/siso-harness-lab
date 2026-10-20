#!/usr/bin/env python3
"""Recover a red main in an owned worktree; all publication goes through land.

Imported by siso-ci. `probe REQUEST` is the fixed command used by git bisect run.
No third-party Scion code is used. See ci/red-main.md for boundaries and recovery.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import sys


class RecoveryBlocked(RuntimeError):
    def __init__(self, message, retry=False):
        super().__init__(message)
        self.retry = retry


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    os.replace(temporary, path)


def probe(request):
    """Setup/infrastructure failures are unknown (125), never a guilty commit.

    Keep the command and comparison base fixed throughout the bisect. Capture
    output inside siso-ci's process-group runner; never print test logs/secrets.
    """
    ci = runpy.run_path(str(Path(__file__).with_name('siso-ci')), run_name='probe_ci')
    cfg = json.loads(Path(request).read_text())
    env = {'npm_config_cache': str(Path(request).parent / 'cache' / 'npm'), 'SISO_CI_BASE': cfg['good'], 'CI': '1', 'FORCE_COLOR': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
    if ci['HOST_CONFIG'].get('temp_root'):
        Path(ci['HOST_CONFIG']['temp_root']).mkdir(parents=True, exist_ok=True)
        env['TMPDIR'] = ci['HOST_CONFIG']['temp_root']
    for step in ('setup', 'test'):
        command = cfg.get(step)
        if not command:
            continue
        code, output = ci['run_step']('sh -c ' + shlex.quote(command), os.getcwd(), env, cfg['timeout'])
        if code and any(marker in output.lower() for marker in ('enospc', 'no space left on device', 'enotfound', 'eai_again')):
            return 125
        if code:
            return 125 if step == 'setup' or code < 0 or code >= 124 else code
    return 0


def recover(ci, repo, source, commands, bad, good, target='main', report_only=False):
    """Receipt makes a repeated CI observation/issue failure safe to retry.

    Fail closed without a proven green ancestor, unambiguous bisect, green
    revert, or a PR-capable land command. Never mutate the shared CI checkout.
    """
    if not target or target.startswith('-') or any(c in target for c in ' ~^:?*[\\'):
        raise RecoveryBlocked('invalid recovery branch')
    if not good:
        raise RecoveryBlocked('no recorded green main ancestor; no revert attempted')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise RecoveryBlocked('invalid repository name')
    if not all(re.fullmatch(r'[0-9a-f]{40,64}', sha or '') for sha in (good, bad)):
        raise RecoveryBlocked('recovery requires full commit IDs')
    if not commands.get('test'):
        raise RecoveryBlocked('no failing test command')
    root = Path(os.environ.get('SISO_RED_MAIN_WORK',
                os.path.expanduser('~/SISO_Workspace/_data/worktrees')))
    incident = root / repo.split('/')[1] / ('red-main-' + repo.split('/')[0] + '-' + target.replace('/', '-') + '-' + bad[:16])
    incident.mkdir(parents=True, exist_ok=True)
    with (incident / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RecoveryBlocked('recovery already running') from None
        receipt = incident / 'receipt.json'
        record = json.loads(receipt.read_text()) if receipt.exists() else {'repo': repo, 'bad': bad, 'good': good, 'target': target}
        if record.get('target', 'main') != target:
            raise RecoveryBlocked('recovery receipt belongs to a different branch')
        if record.get('issue'):
            return record
        tree = incident / 'checkout'

        def git(*args, check=True, cwd=tree):
            # Never include subprocess stderr: remotes/test output may contain credentials.
            p = ci.sh(['git', *args], cwd=str(cwd), check=False, timeout=120)
            if check and p.returncode:
                raise RecoveryBlocked('git ' + args[0] + ' failed; owned worktree retained')
            return p

        if not record.get('revert'):
            if tree.exists():
                raise RecoveryBlocked('unfinished recovery worktree retained; inspect before retrying')
            git('fetch', '-q', 'origin', target, cwd=source)
            head = git('rev-parse', 'FETCH_HEAD', cwd=source).stdout.strip()
            if git('merge-base', '--is-ancestor', bad, head, cwd=source, check=False).returncode:
                raise RecoveryBlocked('red commit is no longer on main')
            chain = git('rev-list', '--first-parent', bad, cwd=source).stdout.splitlines()
            if good not in chain or good == bad:
                raise RecoveryBlocked('green boundary is not an earlier main first-parent ancestor')
            git('worktree', 'add', '--detach', str(tree), bad, cwd=source)
            request = incident / 'probe.json'
            save(request, {**commands, 'good': good, 'timeout': commands.get('timeout', ci.TIMEOUT)})
            probe_command = [sys.executable, str(Path(__file__).resolve()), 'probe', str(request)]
            # Admit the entire bisect once; nested heavy is explicitly unsupported.
            heavy = [] if os.environ.get('SISO_HEAVY_LEASE') else [str(Path(__file__).resolve().parents[1] / 'bin/heavy'), '--']

            def check_at(sha):
                git('checkout', '-q', '--detach', sha)
                code, _ = ci.run_step(shlex.join(heavy + probe_command), str(tree), {}, ci.TIMEOUT * 2 + 60)
                return code

            if check_at(good) != 0:
                raise RecoveryBlocked('recorded green no longer passes the failing command')
            if check_at(bad) not in range(1, 124):
                raise RecoveryBlocked('red failure does not reproduce (or infrastructure failed)')
            git('bisect', 'start', '--first-parent', bad, good)
            try:
                code, _ = ci.run_step(shlex.join(heavy + ['git', 'bisect', 'run', *probe_command]),
                                      str(tree), {}, ci.TIMEOUT * 16)
                if code:
                    raise RecoveryBlocked('bisect failed or skipped candidates are ambiguous')
                culprit = git('rev-parse', 'refs/bisect/bad').stdout.strip()
            finally:
                git('bisect', 'reset')
            if culprit == good or culprit not in chain:
                raise RecoveryBlocked('bisect did not identify a main landing')
            parent = git('rev-parse', culprit + '^1').stdout.strip()
            if check_at(parent) != 0 or check_at(culprit) not in range(1, 124):
                raise RecoveryBlocked('culprit/parent confirmation failed')
            if report_only:  # the nightly run names the culprit and files the issue; nothing is reverted or landed
                record.update(culprit=culprit, test=commands['test'], report_only=True)
                save(receipt, record)
                return _issue(ci, repo, incident, record, bad, good)
            # Work against fresh main, not the observed failing snapshot.
            git('fetch', '-q', 'origin', target)
            head = git('rev-parse', 'FETCH_HEAD').stdout.strip()
            if git('merge-base', '--is-ancestor', bad, head, check=False).returncode:
                raise RecoveryBlocked('main changed ancestry during diagnosis')
            head_code = check_at(head)
            if head_code == 0:
                raise RecoveryBlocked('main is already green; no revert needed')
            if head_code not in range(1, 124):
                raise RecoveryBlocked('current main cannot be tested')
            branch = 'siso/red-main-' + culprit
            git('config', 'branch.' + branch + '.gh-merge-base', target)
            # One branch per culprit prevents duplicate reverts for later red commits.
            prs = ci.gh_json('pr', 'list', '--repo', repo, '--head', branch, '--state', 'all',
                             '--json', 'url,state,headRefOid') or []
            if prs:
                raise RecoveryBlocked('a recovery PR already exists for this culprit: ' + prs[0]['url'])
            git('switch', '-c', branch)
            merge = len(git('rev-list', '--parents', '-n', '1', culprit).stdout.split()) > 2
            p = git('-c', 'user.name=siso-ci', '-c', 'user.email=siso-ci@users.noreply.github.com',
                    'revert', '--no-edit', *(['-m', '1'] if merge else []), culprit, check=False)
            if p.returncode:
                git('revert', '--abort', check=False)
                raise RecoveryBlocked('culprit revert conflicts; no publication attempted')
            code, _ = ci.run_step(shlex.join(heavy + probe_command), str(tree), {}, ci.TIMEOUT * 2 + 60)
            if code:
                raise RecoveryBlocked('revert does not pass the failing command; not published')
            if git('status', '--porcelain').stdout.strip():
                raise RecoveryBlocked('tests left changes in the recovery worktree; not published')
            record.update(culprit=culprit, revert=git('rev-parse', 'HEAD').stdout.strip(),
                          branch=branch, test=commands['test'], main=head)
            save(receipt, record)
        if not record.get('pr'):
            if git('status', '--porcelain').stdout.strip() or git('rev-parse', 'HEAD').stdout.strip() != record['revert']:
                raise RecoveryBlocked('recovery worktree changed; refusing to publish')
            # land implementations supporting --pr must advertise it; older kit
            # versions push main directly. Never silently call those versions.
            kit = tree / 'bin' / 'land'
            if kit.exists() and os.access(kit, os.X_OK) and ('SISO_LAND_PR_ONLY' not in kit.read_text() or (target != 'main' and 'SISO_LAND_BASE' not in kit.read_text())):
                raise RecoveryBlocked('kit land needs SISO_LAND_PR_ONLY support; green revert retained')
            prs = ci.gh_json('pr', 'list', '--repo', repo, '--head', record['branch'], '--state', 'all',
                             '--json', 'url,state,headRefOid') or []
            if not prs:
                heavy = [] if os.environ.get('SISO_HEAVY_LEASE') else [str(Path(__file__).resolve().parents[1] / 'bin/heavy'), '--']
                code, _ = ci.run_step(shlex.join(heavy + ['land']), str(tree),
                                      {'SISO_LAND_PR_ONLY': '1', 'SISO_LAND_BASE': target, 'PATH': os.path.expanduser('~/.local/bin') + os.pathsep + os.environ.get('PATH', '')}, ci.TIMEOUT)
                if code:
                    raise RecoveryBlocked('land failed; tested revert retained for retry', retry=True)
                prs = ci.gh_json('pr', 'list', '--repo', repo, '--head', record['branch'], '--state', 'all',
                                 '--json', 'url,state,headRefOid') or []
            if len(prs) != 1 or prs[0]['state'] == 'CLOSED':
                raise RecoveryBlocked('land did not leave an open or merged recovery PR')
            if prs[0]['headRefOid'] != git('rev-parse', 'HEAD').stdout.strip():
                raise RecoveryBlocked('recovery PR head does not match the owned revert')
            record.update(pr=prs[0]['url'], revert=prs[0]['headRefOid'])
            save(receipt, record)
        return _issue(ci, repo, incident, record, bad, good)


def _issue(ci, repo, incident, record, bad, good):
    title = ('red-main: nightly culprit ' if record.get('report_only') else 'red-main: revert ') + record['culprit'][:12]
    existing = ci.gh_json('issue', 'list', '--repo', repo, '--state', 'all', '--search',
                          title + ' in:title', '--json', 'title,url') or []
    record['issue'] = next((i['url'] for i in existing if i['title'] == title), None)
    if not record['issue']:
        body = incident / 'issue.md'
        body.write_text(f"siso-ci observed red main at `{bad}` after last green `{good}`.\n\n"
                        f"First bad landing: `{record['culprit']}`\n\n"
                        f"Failing test command: `{record['test']}`\n\n"
                        + ("Reported by the nightly full run; nothing was reverted.\n" if record.get('report_only') else
                           f"Tested revert: `{record['revert']}`\n\nRecovery PR: {record['pr']}\n\n"
                           "The revert passed locally; main is repaired only when the PR merges on green siso-ci.\n"))
        result = ci.sh(['gh', 'issue', 'create', '--repo', repo, '--title', title,
                        '--body-file', str(body)], check=False, timeout=120)
        if result.returncode:
            raise RecoveryBlocked('recovery PR exists; issue creation failed, retry is safe', retry=True)
        record['issue'] = result.stdout.strip()
    save(incident / 'receipt.json', record)
    return record


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'probe':
        sys.exit(probe(sys.argv[2]))
    sys.exit('usage: red_main.py probe REQUEST')
