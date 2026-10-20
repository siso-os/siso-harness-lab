"""Affected selection against real Git history, plus PR/main integration boundaries."""
import copy
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
import affected
loader = importlib.machinery.SourceFileLoader('affected_ci', str(ROOT / 'ci/siso-ci'))
spec = importlib.util.spec_from_loader(loader.name, loader)
ci = importlib.util.module_from_spec(spec)
loader.exec_module(ci)


class ActionableFailures(unittest.TestCase):
    def run_output(self, output):
        with patch.object(ci, 'run_step', return_value=(1, output)), patch.dict(os.environ, SISO_HEAVY_LEASE='fixture'):
            return ci.run_tests('fixture/repo', '.', {'test': 'fixture'}, 'base')

    def test_markers_in_fixtures_do_not_hide_assertion_failure(self):
        output = "ok 1 - ENOSPC no space left on device ENOTFOUND EAI_AGAIN\nnot ok 2 - fixture ENOSPC\nAssertionError: ENOSPC\n"
        script = 'print(' + repr(output) + '); assert False, "ENOSPC"'
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, SISO_HEAVY_LEASE='fixture'):
            code, out, _ = ci.run_tests('fixture/repo', tmp, {'test': 'python3 -c ' + ci.sh_quote(script)}, 'base')
        self.assertEqual(code, 1)
        self.assertIn('"category": "check-failed"', out.splitlines()[-1])

    def test_real_disk_and_network_diagnostics_are_infrastructure(self):
        for output, category in [('Error: ENOSPC: no space left on device, write', 'disk-full'),
                                 ('OSError: [Errno 28] No space left on device: private', 'disk-full'),
                                 ('npm error code ENOTFOUND', 'network-resolution'),
                                 ('Error: getaddrinfo EAI_AGAIN private.invalid', 'network-resolution')]:
            with self.subTest(output=output):
                code, out, _ = self.run_output(output)
                self.assertEqual(code, 125)
                self.assertIn(category, out.splitlines()[-1])

    def test_check_summary_survives_long_passing_tail_without_private_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp, 'agents/harness'); module.mkdir(parents=True)
            (module / 'check.sh').touch()
            output = 'check: FAILED agents/harness\ncheck: FAILED ../../private\nSECRET private stderr\n' + 'ok UI typecheck\n' * 100
            with patch.object(ci, 'run_step', return_value=(1, output)), patch.dict(os.environ, SISO_HEAVY_LEASE='fixture'):
                code, out, _ = ci.run_tests('fixture/repo', tmp, {'test': 'fixture'}, 'base')
            summary = out.splitlines()[-1]
            self.assertEqual(code, 1)
            self.assertIn('agents/harness', summary)
            self.assertNotIn('private', summary)
            self.assertNotIn('SECRET', summary)

    def test_bytecode_disabled_and_dirty_clone_guard_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            subprocess.run(['git', 'init', '-q', str(d)], check=True)
            (d / 'fixture.py').write_text('value = 1\n')
            with patch.dict(os.environ, SISO_HEAVY_LEASE='fixture'), patch.object(ci, 'WORK', tmp):
                code, _, _ = ci.run_tests('fixture/repo', tmp, {'test': 'python3 -c "import fixture"'}, 'base')
            self.assertEqual(code, 0)
            self.assertFalse((d / '__pycache__').exists())
            with patch.object(ci, 'repo_dir', return_value=tmp), patch.object(ci, 'sh', return_value=type('P', (), {'stdout': ' M tracked.pyc'})()) as shell:
                with self.assertRaisesRegex(RuntimeError, 'tracked changes'):
                    ci.checkout('fixture/repo', 'head')
                self.assertEqual(shell.call_count, 1)

    def test_commit_comment_exports_only_safe_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(ci, 'checkout', return_value=tmp), patch.object(ci, 'commands', return_value={'test': 'fixture'}), \
                 patch.object(ci, 'run_tests', return_value=(1, 'Error: ENOSPC private-token', .01)), \
                 patch.object(ci, 'sh'), patch.object(ci, 'post_status'), patch.object(ci, 'state_save'), \
                 patch.object(ci, 'gh_json', return_value={}) as github:
                ci.run_commit('fixture/repo', {}, 'main', 'a'*40, {})
            body = str(github.call_args)
            self.assertIn('disk-full', body)
            self.assertNotIn('private-token', body)


class Affected(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='siso-affected-')
        self.d = Path(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'CI fixture')
        self.git('config', 'user.email', 'ci@example.invalid')
        self.git('remote', 'add', 'origin', str(self.d))
        for name, body in {'a.js': 'a', 'b.js': 'b', 'shared.js': 'shared', 'package.json': '{}',
                           'a.test.mjs': "import {test} from 'node:test'; test('a',()=>{});",
                           'b.test.mjs': "import {test} from 'node:test'; test('b',()=>{});"}.items():
            (self.d / name).write_text(body + '\n')
        self.base = self.commit()
        # These assertions inspect TAP counts; do not rely on Node's default reporter.
        self.cfg = {'test': 'node --test --test-reporter=tap *.test.mjs', 'mode': 'all', 'affected': {
            'command': 'node --test --test-reporter=tap', 'test_globs': ['*.test.mjs'], 'shared': ['shared.js'],
            'rules': [{'paths': ['a.js', 'a.test.mjs'], 'tests': ['a.test.mjs']},
                      {'paths': ['b.js', 'b.test.mjs'], 'tests': ['b.test.mjs']}]}}

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.d, stderr=subprocess.PIPE, text=True).strip()

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture')
        return self.git('rev-parse', 'HEAD')

    def change(self, name):
        with (self.d / name).open('a') as f:
            f.write('\n')
        return self.commit()

    def select(self, head=None, cfg=None, base=None):
        return affected.select(str(self.d), cfg or self.cfg, base or self.base, head or self.git('rev-parse', 'HEAD'))

    def test_small_pr_executes_one_of_two_files(self):
        selected = self.select(self.change('a.js'))
        self.assertEqual(selected['selection']['selected'], 1)
        code, out, _ = ci.run_tests('fixture/repo', str(self.d), selected, self.base)
        self.assertEqual(code, 0, out)
        self.assertIn('# tests 1', out)
        print('PROOF small PR: 1/2 test files, 1 test passed')

    def test_docs_only_pr_runs_nothing(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['affected']['ignore'] = ['*.md']
        (self.d / 'notes.md').write_text('x\n')
        selected = self.select(self.commit(), cfg)
        self.assertEqual(selected['selection']['mode'], 'skip')
        self.assertEqual((selected['setup'] if 'setup' in selected else '', selected['test']), ('', 'true'))
        print('PROOF docs-only PR: skip, no install, no tests')

    def test_changed_mode_uses_runner_graph_and_full_on_lockfile(self):
        cfg = {'test': 'full', 'sharding': {'count': 2}, 'affected': {
            'changed': 'echo changed-only', 'ignore': ['*.md'], 'shared': ['package.json']}}
        selected = self.select(self.change('a.js'), cfg)
        self.assertEqual((selected['selection']['mode'], selected['test']), ('changed', 'echo changed-only'))
        self.assertNotIn('sharding', selected)
        self.git('checkout', '-q', self.base)
        selected = self.select(self.change('package.json'), cfg)
        self.assertEqual((selected['selection']['mode'], selected['test']), ('full', 'full'))
        print('PROOF changed mode: runner graph for code, full for shared config')

    def test_by_name_and_unmapped_skip(self):
        cfg = copy.deepcopy(self.cfg)
        cfg['affected'].update(by_name=True, self=True, unmapped='skip', rules=[])
        selected = self.select(self.change('a.js'), cfg)
        self.assertEqual(selected['selection']['tests'], ['a.test.mjs'])
        self.git('checkout', '-q', self.base)
        (self.d / 'orphan.js').write_text('x\n')
        selected = self.select(self.commit(), cfg)
        self.assertEqual((selected['selection']['mode'], selected['test']), ('skip', 'true'))
        print('PROOF by-name: a.js -> a.test.mjs; orphan.js -> nothing (nightly covers it)')

    def test_shared_config_and_unknown_run_full(self):
        for path in ['shared.js', 'package.json', 'unknown.js']:
            with self.subTest(path=path):
                self.git('checkout', '-q', self.base)
                selected = self.select(self.change(path))
                self.assertEqual(selected['test'], self.cfg['test'])
                self.assertEqual(selected['selection']['mode'], 'full')
                code, out, _ = ci.run_tests('fixture/repo', str(self.d), selected, self.base)
                self.assertEqual(code, 0, out)
                self.assertIn('# tests 2', out)
        print('PROOF shared/config/unknown: 2/2 test files, 2 tests passed each')

    def test_union_and_overlapping_rules(self):
        self.change('a.js')
        selected = self.select(self.change('b.js'))
        self.assertEqual(selected['selection']['selected'], 2)
        cfg = copy.deepcopy(self.cfg)
        cfg['affected']['rules'].append({'paths': ['a.js'], 'tests': ['b.test.mjs']})
        self.assertEqual(self.select(cfg=cfg)['selection']['selected'], 2)

    def test_renames_and_deletions_do_not_escape_mapping(self):
        self.git('mv', 'shared.js', 'a.js.new')
        self.assertEqual(self.select(self.commit())['selection']['mode'], 'full')
        self.git('checkout', '-q', self.base)
        (self.d / 'a.test.mjs').unlink()
        self.assertEqual(self.select(self.commit())['selection']['mode'], 'full')

    def test_merge_base_ignores_unrelated_base_advance(self):
        self.git('checkout', '-qb', 'pr')
        head = self.change('a.js')
        self.git('checkout', '-q', 'main')
        base = self.change('shared.js')
        self.git('checkout', '-q', 'pr')
        self.assertEqual(self.select(head=head, base=base)['selection']['mode'], 'subset')

    def test_missing_history_empty_diff_and_malformed_mapping_fall_back(self):
        self.assertEqual(self.select()['selection']['mode'], 'full')
        head = self.change('a.js')
        self.assertEqual(self.select(head, base='f' * 40)['selection']['mode'], 'full')
        for broken in [{}, {'rules': []}, {'test_globs': ['missing/*']}, {'command': None}, {'shared': 'x'},
                       {'rules': [{'paths': ['a.js'], 'tests': []}]}]:
            cfg = copy.deepcopy(self.cfg)
            cfg['affected'].update(broken)
            if not broken:
                cfg.pop('affected')
            self.assertEqual(self.select(cfg=cfg)['test'], self.cfg['test'])

    def test_branch_script_keeps_full_command(self):
        (self.d / '.siso-ci').write_text('node --test *.test.mjs\n')
        head = self.commit()
        cmds = ci.commands('fixture/repo', str(self.d), self.cfg)
        selected = affected.select(str(self.d), cmds, self.base, head)
        self.assertEqual(selected['test'], 'sh .siso-ci')
        self.assertEqual(selected['selection']['mode'], 'full')

    def test_main_runs_full_even_if_same_sha_passed_pr(self):
        head = self.change('a.js')
        st = {'done': {f'fixture/repo@{head}': {'state': 'success', 'selection': {'mode': 'subset'}}}}
        with patch.object(ci, 'gh_json', return_value={'sha': head}), patch.object(ci, 'run_commit') as run:
            ci.branch_runs('fixture/repo', {**self.cfg, 'branches': ['main']}, st)
            run.assert_called_once()
        with patch.object(ci, 'checkout', return_value=str(self.d)), patch.object(ci, 'post_status'), \
             patch.object(ci, 'state_save'), patch.object(ci, 'run_tests', wraps=ci.run_tests) as run:
            self.assertEqual(ci.run_commit('fixture/repo', self.cfg, 'main', head, {}), 'success')
            self.assertEqual(run.call_args.args[2]['test'], self.cfg['test'])
            self.assertNotIn('selection', run.call_args.args[2])

    def test_new_failure_retry_restores_head_after_base(self):
        head = self.change('a.js')
        cfg = {**self.cfg, 'mode': 'new-failures'}
        def checkout(repo, sha, ref=None):
            self.git('checkout', '-q', sha)
            return str(self.d)
        seen = []
        def run(repo, d, cmds, base):
            at = self.git('rev-parse', 'HEAD')
            seen.append(at)
            return (1, 'not ok 1 - new failure', 0.1) if at == head else (0, '', 0.1)
        with patch.object(ci, 'checkout', side_effect=checkout), patch.object(ci, 'run_tests', side_effect=run), \
             patch.object(ci, 'state_save'), patch.object(ci, 'post_status'), patch.object(ci, 'comment'):
            self.assertEqual(ci.run_pr('fixture/repo', cfg, {'headRefOid': head, 'baseRefOid': self.base, 'number': 1}, {}), 'failure')
        self.assertEqual(seen, [head, self.base, head])

    def test_job_cap_is_pending_runner_busy_and_not_requeued(self):
        head = self.change('a.js')
        posted = []
        def post(repo, sha, state, desc, url=None, context=None):
            posted.append((state, desc, context))
        with patch.object(ci, 'checkout', return_value=str(self.d)), patch.object(ci, 'state_save'), \
             patch.object(ci, 'post_status', side_effect=post), patch.object(ci, 'comment') as comment, \
             patch.object(ci, 'run_tests', return_value=(143, '[siso-ci] JOB CAP 300s: killing', 300.0)):
            self.assertEqual(ci.run_pr('fixture/repo', self.cfg, {'headRefOid': head, 'baseRefOid': self.base, 'number': 1}, {}), 'pending')
        comment.assert_not_called()
        state, desc, context = posted[-1]
        self.assertEqual((state, context), ('pending', 'siso-ci/pr'))
        self.assertTrue(desc.startswith('runner busy'), desc)
        self.assertNotIn(state, ('failure', 'error'))
        with patch.object(ci, 'gh_json', return_value=[{'context': 'siso-ci/pr', 'state': 'pending', 'description': desc}]):
            self.assertTrue(ci.has_status('fixture/repo', head, 'siso-ci/pr'))
        with patch.object(ci, 'gh_json', return_value=[{'context': 'siso-ci/pr', 'state': 'pending', 'description': 'PR affected/full checks: x'}]):
            self.assertFalse(ci.has_status('fixture/repo', head, 'siso-ci/pr'))


if __name__ == '__main__':
    unittest.main()
