"""Real Git fixtures; network/land replaced only at the publishing boundary."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'ci'))
import red_main
loader = importlib.machinery.SourceFileLoader('fixture_ci', str(ROOT / 'ci/siso-ci'))
spec = importlib.util.spec_from_loader(loader.name, loader)
ci = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = ci
loader.exec_module(ci)


class RedMain(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='siso-red-main-test-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'repo'
        self.remote = self.root / 'remote.git'
        self.source.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.source / 'value').write_text('green\n')
        (self.source / 'noop.py').write_text('VALUE = 1\n')
        (self.source / 'check.sh').write_text('python3 -c "import noop"\ntest "$(cat value)" = green\n')
        self.good = self.commit('green')
        (self.source / 'value').write_text('red\n')
        self.culprit = self.commit('breaking change')
        (self.source / 'later').write_text('keep this unrelated good change\n')
        self.bad = self.commit('later good change')
        self.git('init', '-q', '--bare', str(self.remote))
        self.git('remote', 'add', 'origin', str(self.remote))
        # Seed a throwaway bare origin without ever pushing main.
        subprocess.run(['git', '-C', str(self.remote), 'fetch', '-q', str(self.source),
                        'refs/heads/main:refs/heads/main'], check=True)
        self.patch = patch.dict(os.environ, {'SISO_RED_MAIN_WORK': str(self.root / 'worktrees')})
        self.patch.start()
        self.commands = {'setup': '', 'test': 'sh check.sh'}
        self.prs = []
        self.issues = []
        self.land_calls = 0
        self.fail_issue = False
        self.real_step = ci.run_step
        self.real_sh = ci.sh
        self.patches = [patch.object(ci, 'run_step', self.step), patch.object(ci, 'gh_json', self.gh),
                        patch.object(ci, 'sh', self.sh)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.patch.stop()
        self.temp.cleanup()

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd or self.source, text=True,
                                       stderr=subprocess.PIPE).strip()

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-qm', message)
        return self.git('rev-parse', 'HEAD')

    def sync(self):
        subprocess.run(['git', '-C', str(self.remote), 'fetch', '-q', str(self.source),
                        'refs/heads/main:refs/heads/main'], check=True)

    def step(self, cmd, d, env, timeout=None):
        if cmd.endswith('land'):
            self.land_calls += 1
            self.assertEqual(env['SISO_LAND_PR_ONLY'], '1')
            sha = self.git('rev-parse', 'HEAD', cwd=d)
            self.assertEqual(self.git('show', 'HEAD:value', cwd=d), 'green')
            self.assertEqual(self.git('show', 'HEAD:later', cwd=d), 'keep this unrelated good change')
            self.prs = [{'url': 'https://github.com/fixture/repo/pull/1', 'state': 'OPEN', 'headRefOid': sha}]
            return 0, self.prs[0]['url']
        return self.real_step(cmd, d, env, timeout)

    def gh(self, *args):
        if args[:2] == ('pr', 'list'):
            return self.prs
        if args[:2] == ('issue', 'list'):
            return self.issues
        raise AssertionError(args)

    def sh(self, cmd, **kwargs):
        if cmd[:3] == ['gh', 'issue', 'create']:
            if self.fail_issue:
                return subprocess.CompletedProcess(cmd, 1, '', 'fixture outage')
            body = Path(cmd[cmd.index('--body-file') + 1]).read_text()
            self.assertIn(self.culprit, body)
            self.assertIn('sh check.sh', body)
            if self.prs: self.assertIn(self.prs[0]['headRefOid'], body)
            title = cmd[cmd.index('--title') + 1]
            self.issues.append({'title': title, 'url': 'https://github.com/fixture/repo/issues/2'})
            return subprocess.CompletedProcess(cmd, 0, self.issues[0]['url'], '')
        self.assertFalse(cmd[:2] == ['git', 'push'], 'bot must publish only through land')
        return self.real_sh(cmd, **kwargs)

    def run_bot(self, good=None, commands=None):
        return red_main.recover(ci, 'fixture/repo', str(self.source), commands or self.commands,
                                self.bad, self.good if good is None else good)

    def test_reverts_breaking_commit_and_preserves_later_good_commit(self):
        # Shared checkout has unrelated edits. The bot must not touch any of them.
        (self.source / 'later').write_text('operator uncommitted work\n')
        before = self.git('status', '--porcelain')
        result = self.run_bot()
        self.assertEqual(result['culprit'], self.culprit)
        tree = self.root / 'worktrees/repo' / ('red-main-fixture-' + self.bad[:16]) / 'checkout'
        self.assertFalse((tree / '__pycache__').exists(), 'recovery must not rewrite bytecode')
        self.assertNotEqual(result['culprit'], self.bad)
        self.assertEqual(self.git('show', result['revert'] + ':value'), 'green')
        self.assertEqual(self.git('show', result['revert'] + ':later'), 'keep this unrelated good change')
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.bad)
        self.assertEqual(self.git('rev-parse', 'refs/heads/main', cwd=self.remote), self.bad)
        self.assertEqual(self.run_bot(), result)
        self.assertEqual(self.land_calls, 1)
        self.assertEqual(len(self.issues), 1)
        print('PROOF: breaking commit reverted; later good commit preserved; main untouched; land PR and issue created')

    def test_report_only_names_the_culprit_and_files_an_issue_without_reverting(self):
        result = red_main.recover(ci, 'fixture/repo', str(self.source), self.commands, self.bad, self.good, report_only=True)
        self.assertEqual(result['culprit'], self.culprit)
        self.assertTrue(result['issue'])
        self.assertTrue(self.issues[0]['title'].startswith('red-main: nightly culprit '))
        self.assertEqual(self.land_calls, 0)
        self.assertNotIn('revert', result)
        print('PROOF: nightly report-only run names the culprit, files an issue, reverts and lands nothing')

    def test_issue_outage_retries_without_second_revert_or_land(self):
        self.fail_issue = True
        with self.assertRaisesRegex(red_main.RecoveryBlocked, 'issue creation failed') as e:
            self.run_bot()
        self.assertTrue(e.exception.retry)
        self.fail_issue = False
        result = self.run_bot()
        self.assertEqual(result['culprit'], self.culprit)
        self.assertEqual(self.land_calls, 1)
        self.assertEqual(len(self.issues), 1)

    def test_missing_green_stops_before_worktree(self):
        with self.assertRaisesRegex(red_main.RecoveryBlocked, 'no recorded green'):
            self.run_bot(good='')
        self.assertEqual(self.land_calls, 0)
        self.assertFalse((self.root / 'worktrees').exists())

    def test_setup_failure_does_not_blame_a_commit(self):
        with self.assertRaisesRegex(red_main.RecoveryBlocked, 'green no longer passes'):
            self.run_bot(commands={'setup': 'exit 1', 'test': 'sh check.sh'})
        self.assertEqual(self.land_calls, 0)

    def test_skipped_culprit_is_ambiguous_and_not_published(self):
        commands = {'setup': 'test "$(git log -1 --format=%s)" != "breaking change"', 'test': 'sh check.sh'}
        with self.assertRaisesRegex(red_main.RecoveryBlocked, 'bisect failed or skipped'):
            self.run_bot(commands=commands)
        self.assertEqual(self.land_calls, 0)

    def test_fixed_main_is_not_reverted(self):
        (self.source / 'value').write_text('green\n')
        self.commit('already repaired')
        self.sync()
        with self.assertRaisesRegex(red_main.RecoveryBlocked, 'main is already green'):
            self.run_bot()
        self.assertEqual(self.land_calls, 0)

    def test_conflict_retains_work_without_publishing(self):
        (self.source / 'value').write_text('another red value\n')
        self.commit('overlapping later edit')
        self.sync()
        with self.assertRaisesRegex(red_main.RecoveryBlocked, 'revert conflicts'):
            self.run_bot()
        self.assertEqual(self.land_calls, 0)

    def test_merge_landing_is_culprit_and_reverted_with_first_parent(self):
        # Build another graph, using new refs without rewriting existing history.
        self.git('switch', '-qc', 'clean-base', self.good)
        (self.source / 'main-only').write_text('main\n')
        base = self.commit('main advance')
        self.git('switch', '-qc', 'feature', self.good)
        (self.source / 'value').write_text('red\n')
        self.commit('feature break')
        self.git('switch', '-q', 'clean-base')
        self.git('merge', '--no-ff', '-qm', 'merge broken feature', 'feature')
        self.culprit = self.git('rev-parse', 'HEAD')
        (self.source / 'later').write_text('keep this unrelated good change\n')
        self.bad = self.commit('later good change')
        # A new bare origin is seeded from this fixture's clean-base mainline.
        remote = self.root / 'merge-origin.git'
        self.git('init', '-q', '--bare', str(remote))
        subprocess.run(['git', '-C', str(remote), 'fetch', '-q', str(self.source),
                        'refs/heads/clean-base:refs/heads/main'], check=True)
        self.git('remote', 'set-url', 'origin', str(remote))
        result = self.run_bot(good=base)
        self.assertEqual(result['culprit'], self.culprit)
        self.assertEqual(self.git('show', result['revert'] + ':main-only'), 'main')
        self.assertEqual(self.git('show', result['revert'] + ':value'), 'green')

    def test_old_main_pushing_kit_is_blocked(self):
        (self.source / 'bin').mkdir()
        land = self.source / 'bin/land'
        land.write_text('#!/bin/sh\ngit push origin HEAD:main\n')
        land.chmod(0o755)
        self.bad = self.commit('old kit')
        self.sync()
        with self.assertRaisesRegex(red_main.RecoveryBlocked, 'kit land needs'):
            self.run_bot()
        self.assertEqual(self.land_calls, 0)

    def test_run_commit_routes_red_main_and_records_success_boundary(self):
        state = {'green': {'fixture/repo@main': self.good}}
        with patch.object(ci, 'checkout', return_value=str(self.source)), \
             patch.object(ci, 'run_tests', return_value=(1, 'not ok 1 - regression', 0.01)), \
             patch.object(ci, 'post_status'), patch.object(ci, 'state_save'), \
             patch.object(ci, 'gh_json', return_value={}), \
             patch.object(ci, 'auto_revert') as legacy, \
             patch.object(red_main, 'recover', return_value={'culprit': self.culprit, 'revert': 'r',
                                                           'pr': 'pr', 'issue': 'issue'}) as bot:
            ci.run_commit('fixture/repo', {'revert': True, **self.commands}, 'main', self.bad, state)
            self.assertEqual(bot.call_args.args[-1], self.good)
            legacy.assert_not_called()
        with patch.object(ci, 'checkout', return_value=str(self.source)), \
             patch.object(ci, 'run_tests', return_value=(0, '', 0.01)), \
             patch.object(ci, 'post_status'), patch.object(ci, 'state_save'):
            ci.run_commit('fixture/repo', self.commands, 'main', self.good, state)
            self.assertEqual(state['green']['fixture/repo@main'], self.good)

    def test_non_main_target_preserves_main_and_sets_land_base(self):
        subprocess.run(['git', '-C', str(self.remote), 'fetch', '-q', str(self.source),
                        'refs/heads/main:refs/heads/halo/v2'], check=True)
        before = self.git('rev-parse', 'refs/heads/main', cwd=self.remote)
        result = red_main.recover(ci, 'fixture/repo', str(self.source), self.commands,
                                  self.bad, self.good, target='halo/v2')
        tree = next((self.root/'worktrees/repo').glob('red-main-*/checkout'))
        self.assertEqual(self.git('config', 'branch.' + result['branch'] + '.gh-merge-base', cwd=tree), 'halo/v2')
        self.assertEqual(self.git('rev-parse', 'refs/heads/main', cwd=self.remote), before)


if __name__ == '__main__':
    unittest.main()
