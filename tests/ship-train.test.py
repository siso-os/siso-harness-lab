import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'ci'))
import worker_pool

class Workers(unittest.TestCase):
    def test_parallel_slots_are_warm_and_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'worker.py'
            script.write_text('''import json,os,sys,time
from pathlib import Path
j=json.load(sys.stdin)
p=Path(os.environ['SISO_CI_WORK']); p.mkdir(parents=True,exist_ok=True)
with (p/'events').open('a') as f: f.write(str(time.time())+' start\\n')
(p/'warm').touch()
time.sleep(.3)
with (p/'events').open('a') as f: f.write(str(time.time())+' end\\n')
''')
            hosts = [{'name':'local','slot':str(n)} for n in range(2)]
            jobs = [{'repo':'a/b','kind':'pr'} for _ in range(4)]
            start=time.time()
            results=worker_pool.dispatch(jobs,hosts,script,tmp)
            self.assertEqual([r['exit'] for r in results], [0]*4)
            intervals=[]
            for n in range(2):
                events=(Path(tmp)/'workers'/str(n)/'events').read_text().splitlines()
                intervals.append((float(events[0].split()[0]),float(events[1].split()[0])))
            self.assertLess(max(a for a,b in intervals),min(b for a,b in intervals))
            for n in range(2):
                p=Path(tmp)/'workers'/str(n)
                self.assertTrue((p/'warm').exists())
                self.assertEqual([l.split()[1] for l in (p/'events').read_text().splitlines()], ['start','end']*2)

    def test_failed_checkout_receipt_is_sanitized(self):
        result = subprocess.CompletedProcess([], 1, 'private stdout secret',
            'private stderr secret\nRuntimeError: owned CI clone has tracked changes; retained for inspection')
        with patch('worker_pool.subprocess.run', return_value=result):
            receipt = worker_pool.dispatch([{'repo':'a/b','kind':'pr'}], [{'slot':'fixture'}], 'unused', '/tmp')[0]
        self.assertEqual(receipt['receipt'], {'state':'error','category':'clone-tracked-changes'})
        self.assertNotIn('secret', json.dumps(receipt))

    def test_worker_receipts_do_not_forward_arbitrary_json_or_stderr(self):
        receipt = worker_pool.worker_receipt('{"state":"failure","category":"secret","token":"secret"}', 'secret', 1)
        self.assertEqual(receipt, {'state':'failure'})
        self.assertEqual(worker_pool.worker_receipt('', 'Error: ENOSPC private', 1)['category'], 'disk-full')

    def test_guard_archives_only_ignored_owned_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); repo=root/'clones/a/b'; repo.mkdir(parents=True)
            subprocess.run(['git','init','-q',str(repo)],check=True)
            (repo/'.gitignore').write_text('.cache/\n')
            cache=repo/'.cache'; cache.mkdir(); (cache/'saved').write_text('recover me')
            operator=repo/'operator.txt'; operator.write_text('preserve')
            usage=type('U',(),{'free':0})()
            with patch('worker_pool.shutil.disk_usage',return_value=usage):
                with self.assertRaisesRegex(RuntimeError,'disk guard'):
                    worker_pool.disk_guard(root,1)
            self.assertFalse(cache.exists())
            self.assertTrue(list((root/'_archive').glob('*.tar.gz')))
            self.assertEqual(operator.read_text(),'preserve')

    def test_slot_lock_excludes_second_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            with worker_pool.lock(Path(tmp)/'lock'):
                with self.assertRaises(BlockingIOError):
                    with worker_pool.lock(Path(tmp)/'lock'): pass

class Coordinator(unittest.TestCase):
    def test_discovery_continues_without_duplicate_busy_heads(self):
        import threading
        release=threading.Event()
        def job(*args):
            release.wait(5)
            return []
        hosts=[{'name':'local','slot':str(n)} for n in range(2)]
        jobs=[{'repo':'a/b','kind':'pr','pr':{'headRefOid':str(n)}} for n in range(3)]
        controller=worker_pool.Controller(hosts,'unused','unused')
        try:
            with patch('worker_pool.dispatch',side_effect=job):
                controller.tick(jobs)
                self.assertEqual(len(controller.active),2)
                controller.tick(jobs)
                self.assertEqual(len(controller.active),2)
                self.assertEqual(len(controller.pending),1)
        finally:
            release.set();controller.pool.shutdown(wait=True)

class Affected(unittest.TestCase):
    def test_transitive_dependents_and_unknown_full(self):
        import affected
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            def git(*a):
                return subprocess.check_output(['git',*a],cwd=d,stderr=subprocess.DEVNULL).decode().strip()
            git('init','-q'); git('config','user.name','fixture');git('config','user.email','fixture@example.test')
            (d/'a').mkdir(); (d/'a/src').write_text('before')
            git('add','.');git('commit','-qm','base');base=git('rev-parse','HEAD')
            git('remote','add','origin',tmp)
            (d/'a/src').write_text('after');git('commit','-qam','change');head=git('rev-parse','HEAD')
            cfg={'test':'full', 'packages':[
                {'name':'a','path':'a','test':'true'},
                {'name':'b','path':'b','test':'true','dependencies':['a']},
                {'name':'c','path':'c','test':'true','dependencies':['b']},
                {'name':'other','path':'other','test':'true'}]}
            got=affected.select(tmp,cfg,base,head)
            self.assertEqual(got['selection']['packages'],['a','b','c'])
            (d/'unknown').write_text('unknown');git('add','.');git('commit','-qm','unknown')
            self.assertEqual(affected.select(tmp,cfg,base,git('rev-parse','HEAD'))['test'],'full')

    def test_shards_all_run_and_failure_is_red(self):
        import runpy
        ci=runpy.run_path(str(Path(__file__).resolve().parents[1]/'ci/siso-ci'))
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp,'a.test.ts').touch()
            seen=[]
            def step(command,*args):
                seen.append(command)
                return (1,'failed') if '--shard=2/2' in command else (0,'passed')
            ci['run_tests'].__globals__['run_step']=step
            code,_,_=ci['run_tests']('a/b',tmp,{'test':'vitest run','sharding':{'count':2,'min_files':1}},'base')
            self.assertEqual(code,1)
            self.assertTrue(any('--shard=1/2' in c for c in seen))
            self.assertTrue(any('--shard=2/2' in c for c in seen))

class Train(unittest.TestCase):
    def setUp(self):
        import runpy
        self.m=runpy.run_path(str(Path(__file__).resolve().parents[1]/'ci/ship-train'))
        self.ci=self.m['ci']
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.repo=self.root/'repo';self.repo.mkdir()
        def git(*a):
            return subprocess.check_output(['git',*a],cwd=self.repo,stderr=subprocess.DEVNULL).decode().strip()
        self.git=git
        git('init','-q','-b','halo/v2');git('config','user.name','fixture');git('config','user.email','fixture@example.test')
        (self.repo/'check.sh').write_text('test "$(cat value)" = green\n')
        (self.repo/'value').write_text('green')
        git('add','.');git('commit','-qm','green');self.good=git('rev-parse','HEAD')
        git('remote','add','origin',str(self.repo));git('fetch','-q','origin','halo/v2')
        self.ci.WORK=str(self.root/'work')
        self.statuses={};self.prs=[];self.merges=[]
        self.cfg={'test':'sh check.sh','mode':'all','train':{'branches':['halo/v2'],'minimum_free_mb':0,
                  'deploy':'test "$(git rev-parse HEAD)" = "$SISO_CI_SHA" && echo "$SISO_CI_SHA" >> deployed'}}
        def gh(*a):
            if a[:2]==('pr','list'): return self.prs
            if a[0]=='api' and a[1].endswith('/statuses'):
                sha=a[1].split('/')[-2]
                return [{'context':c,'state':v} for (s,c),v in self.statuses.items() if s==sha]
            if a[0]=='api' and '/compare/' in a[1]: return {'ahead_by':0}
            if a[0]=='api' and '/commits/' in a[1]: return {'sha':git('rev-parse','halo/v2')}
            raise AssertionError(a)
        def checkout(repo,sha,ref=None):
            git('fetch','-q','origin','halo/v2');git('checkout','-q','--detach',sha);return str(self.repo)
        self.patchers=[patch.object(self.ci,'gh_json',side_effect=gh),
                       patch.object(self.ci,'checkout',side_effect=checkout),
                       patch.object(self.ci,'post_status',side_effect=lambda r,s,state,d,url=None,context=None:self.statuses.update({(s,context or 'siso-ci'):state}))]
        for p in self.patchers:p.start()

    def tearDown(self):
        for p in reversed(self.patchers):p.stop()
        self.temp.cleanup()

    def run_train(self):
        code=self.m['train']('fixture/repo','halo/v2',self.cfg)
        record=json.loads((self.root/'work/trains/fixture/repo/halo/v2/minutes-lost.jsonl').read_text().splitlines()[-1])
        return code,record

    def test_one_full_run_records_green_and_exact_sha_deploy(self):
        code,r=self.run_train()
        self.assertEqual(code,0);self.assertEqual(r['test_runs'],1)
        self.assertEqual(r['last_green'],self.good)
        self.assertEqual((self.repo/'deployed').read_text().strip(),self.good)
        code,r=self.run_train()
        self.assertEqual(code,0);self.assertEqual(r['test_runs'],0)
        self.assertEqual(r['deploy_state'],'already-deployed')

    def test_disk_exhaustion_is_unknown_and_never_bisected(self):
        with patch.object(self.ci,'run_tests',return_value=(1,'Error: ENOSPC',.01)), patch('red_main.recover') as bot:
            code,r=self.run_train()
        self.assertEqual(code,1);self.assertEqual(r['test_exit'],125)
        self.assertTrue(r['infrastructure_failure']);bot.assert_not_called()

    def test_latest_gate_draft_and_unknown_mergeability(self):
        self.prs=[{'number':i,'headRefOid':str(i),'isDraft':False,'mergeable':'MERGEABLE','labels':[]} for i in range(1,5)]
        self.statuses.update({(str(i),'siso-ci/pr'):'success' for i in range(1,5)})
        self.prs[1]['isDraft']=True;self.prs[2]['mergeable']='UNKNOWN'
        self.statuses[('4','siso-ci/pr')]='pending'
        ready,dropped=self.m['ready']('fixture/repo','halo/v2')
        self.assertEqual([p['number'] for p in ready],[1]);self.assertEqual(len(dropped),3)

    def test_red_never_replaces_green_or_deploys_head(self):
        self.run_train()
        self.git('checkout','-q','halo/v2')
        (self.repo/'value').write_text('red');self.git('add','value');self.git('commit','-qm','bad')
        bad=self.git('rev-parse','HEAD')
        # A recovery cannot run without an unambiguous diagnosis. Retain last green.
        with patch('red_main.recover',side_effect=RuntimeError('unknown')):
            code,r=self.run_train()
        self.assertEqual(code,1);self.assertEqual(r['state'],'red')
        self.assertEqual(r['last_green'],self.good)
        self.assertNotIn(bad,(self.repo/'deployed').read_text())

    def test_two_prs_merge_with_one_full_suite(self):
        self.git('checkout','-qb','feature-one')
        (self.repo/'one').write_text('one');self.git('add','one');self.git('commit','-qm','one');one=self.git('rev-parse','HEAD')
        self.git('checkout','-qb','feature-two',self.good)
        (self.repo/'two').write_text('two');self.git('add','two');self.git('commit','-qm','two');two=self.git('rev-parse','HEAD')
        self.git('checkout','-q','halo/v2')
        self.prs=[{'number':n,'headRefOid':sha,'isDraft':False,'mergeable':'MERGEABLE','labels':[]} for n,sha in [(1,one),(2,two)]]
        self.statuses.update({(sha,'siso-ci/pr'):'success' for sha in (one,two)})
        original=self.ci.sh
        def sh(command,**kw):
            if command[:3]==['gh','pr','merge']:
                sha=command[-1]
                self.git('merge','--no-ff','-qm','train',sha)
                return subprocess.CompletedProcess(command,0,'','')
            return original(command,**kw)
        with patch.object(self.ci,'sh',side_effect=sh):
            code,r=self.run_train()
        self.assertEqual(code,0);self.assertEqual(len(r['prs_in']),2);self.assertEqual(r['test_runs'],1)
        self.assertTrue((self.repo/'one').exists());self.assertTrue((self.repo/'two').exists())

    def bad_head(self):
        self.run_train()
        self.git('checkout','-q','halo/v2')
        (self.repo/'value').write_text('red');self.git('add','value');self.git('commit','-qm','bad')
        return self.git('rev-parse','HEAD')

    def test_a_failure_that_passes_on_the_second_run_is_green_and_ships(self):
        self.run_train()
        self.git('checkout','-q','halo/v2')
        (self.repo/'other').write_text('x');self.git('add','other');self.git('commit','-qm','next')
        head=self.git('rev-parse','HEAD')
        runs=[(1,'flaky',.01),(0,'ok',.01)]
        with patch.object(self.ci,'run_tests',side_effect=lambda *a:runs.pop(0)), patch('red_main.recover') as bot:
            code,r=self.run_train()
        self.assertEqual(code,0);self.assertEqual(r['state'],'green');self.assertTrue(r['flaky'])
        self.assertEqual(r['last_green'],head);bot.assert_not_called()
        self.assertIn(head,(self.repo/'deployed').read_text())

    def test_recovery_that_finds_the_head_green_promotes_it(self):
        self.run_train()
        self.git('checkout','-q','halo/v2')
        (self.repo/'other').write_text('x');self.git('add','other');self.git('commit','-qm','next')
        head=self.git('rev-parse','HEAD')
        runs=[(1,'a',.01),(1,'b',.01),(0,'c',.01)]
        blocked=self.m['red_main'].RecoveryBlocked('main is already green; no revert needed')
        with patch.object(self.ci,'run_tests',side_effect=lambda *a:runs.pop(0)), patch('red_main.recover',side_effect=blocked):
            code,r=self.run_train()
        self.assertEqual(code,0);self.assertEqual(r['state'],'green');self.assertEqual(r['last_green'],head)

    def test_a_head_that_failed_twice_is_not_retested_until_it_changes(self):
        bad=self.bad_head()
        blocked=self.m['red_main'].RecoveryBlocked('bisect failed or skipped candidates are ambiguous')
        with patch.object(self.ci,'run_tests',return_value=(1,'fail',.01)) as t, patch('red_main.recover',side_effect=blocked):
            self.run_train();self.run_train()
            self.assertEqual(t.call_count,4)
            code,r=self.run_train()
        self.assertEqual(t.call_count,4);self.assertEqual(r['test_runs'],0)
        self.assertEqual(r['state'],'red');self.assertEqual(r['known_red']['tries'],2);self.assertEqual(r['head'],bad)
        self.assertEqual(r['last_green'],self.good)

    def test_a_retryable_recovery_step_is_not_given_up_on(self):
        self.bad_head()
        blocked=self.m['red_main'].RecoveryBlocked('land failed; tested revert retained for retry',retry=True)
        with patch.object(self.ci,'run_tests',return_value=(1,'fail',.01)) as t, patch('red_main.recover',side_effect=blocked):
            self.run_train();self.run_train();code,r=self.run_train()
        self.assertEqual(t.call_count,6);self.assertNotIn('known_red',r)

    def test_a_train_that_finds_the_branch_locked_leaves_no_record(self):
        root=self.root/'work/trains/fixture/repo/halo/v2';root.mkdir(parents=True)
        with worker_pool.lock(root/'train.lock'):
            code=self.m['train']('fixture/repo','halo/v2',self.cfg)
        self.assertEqual(code,0);self.assertFalse((root/'latest.json').exists())

    def test_hold_stops_merge_suite_and_deploy_until_lifted(self):
        root=self.root/'work/trains/fixture/repo/halo/v2';root.mkdir(parents=True)
        (root/'HOLD').write_text('night is streaming')
        self.prs=[{'number':1,'headRefOid':'h','isDraft':False,'mergeable':'MERGEABLE','labels':[]}]
        self.statuses[('h','siso-ci/pr')]='success'
        with patch.object(self.ci,'run_tests') as tests, patch.object(self.ci,'sh') as shell:
            code=self.m['train']('fixture/repo','halo/v2',self.cfg)
        self.assertEqual(code,0);tests.assert_not_called();shell.assert_not_called()
        self.assertFalse((self.repo/'deployed').exists());self.assertFalse((root/'latest.json').exists())
        (root/'HOLD').unlink()
        self.prs=[]
        code,r=self.run_train()
        self.assertEqual(r['state'],'green');self.assertTrue((self.repo/'deployed').exists())

    def test_hold_set_mid_train_still_blocks_the_deploy(self):
        root=self.root/'work/trains/fixture/repo/halo/v2'
        real=self.ci.run_tests
        def tests(*a):
            (root/'HOLD').write_text('now');return real(*a)
        with patch.object(self.ci,'run_tests',side_effect=tests):
            code,r=self.run_train()
        self.assertEqual(r['state'],'green');self.assertEqual(r['deploy_state'],'held')
        self.assertFalse((self.repo/'deployed').exists())

    def test_nightly_suite_ships_on_green_pr_gates_without_running_it(self):
        (self.repo/'value').write_text('red');self.git('commit','-qam','a change whose full suite would fail')
        head=self.git('rev-parse','HEAD')
        self.cfg['train']['suite']='nightly'
        code,r=self.run_train()
        self.assertEqual(code,0);self.assertEqual(r['test_runs'],0);self.assertEqual(r['suite'],'nightly')
        self.assertEqual((self.repo/'deployed').read_text().strip(),head)
        self.assertEqual(self.statuses[(head,'siso-ci/train')],'success')
        self.assertEqual(self.statuses[(head,'siso-ci')],'success')

    def test_nightly_run_is_report_only_and_once_per_head(self):
        self.cfg['train']['suite']='nightly'
        (self.repo/'value').write_text('red');self.git('commit','-qam','red');head=self.git('rev-parse','HEAD')
        self.assertEqual(self.m['nightly']('fixture/repo','halo/v2',self.cfg,now=1000),0)
        self.assertEqual(self.statuses[(head,'siso-ci/nightly')],'failure')
        self.assertFalse((self.repo/'deployed').exists())  # report-only: never ships, merges or reverts
        self.statuses.clear()
        self.m['nightly']('fixture/repo','halo/v2',self.cfg,now=1100)
        self.assertEqual(self.statuses,{})  # same head: not run again
        (self.repo/'value').write_text('green');self.git('commit','-qam','fixed');self.git('branch','-f','halo/v2','HEAD');head=self.git('rev-parse','HEAD')
        self.m['nightly']('fixture/repo','halo/v2',self.cfg,now=1200)
        self.assertEqual(self.statuses,{})  # new head but not yet due (a day, or 40 commits)
        self.m['nightly']('fixture/repo','halo/v2',self.cfg,now=1000+86400)
        self.assertEqual(self.statuses[(head,'siso-ci/nightly')],'success')

    def test_merge_race_drops_only_that_pr(self):
        self.prs=[{'number':1,'headRefOid':'h','isDraft':False,'mergeable':'MERGEABLE','labels':[]}]
        self.statuses[('h','siso-ci/pr')]='success'
        with patch.object(self.ci,'sh',side_effect=RuntimeError('moved')):
            code,r=self.run_train()
        self.assertEqual(r['prs_in'],[])
        self.assertEqual(r['prs_dropped'][0]['reason'],'merge-race-or-refusal')

class Coordinator(unittest.TestCase):
    """The workers coordinator runs each configured train as a child and logs its record."""
    def test_trains_run_as_children_one_per_branch_and_are_paced(self):
        import runpy
        ci=runpy.run_path(str(Path(__file__).resolve().parents[1]/'ci/siso-ci'))
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/'fake-train'
            script.write_text('import json,sys\nprint("noise")\nprint(json.dumps({"repo":sys.argv[1],"branch":sys.argv[2],"state":"green","head":"abc"}))\n')
            cfg={'o/r':{'train':{'branches':['halo/v2'],'every':100}},'o/none':{}}
            trains=ci['Trains'](str(script))
            trains.tick.__globals__['config']=lambda:cfg
            self.assertEqual(trains.tick(now=1000),[]);self.assertTrue(trains.active)
            for _ in range(100):
                done=trains.tick(now=1000)
                if done: break
                time.sleep(.05)
            self.assertEqual(done,[{'kind':'train','repo':'o/r','branch':'halo/v2','state':'green','head':'abc'}])
            self.assertFalse(trains.active)
            self.assertEqual(trains.tick(now=1050),[]);self.assertFalse(trains.active)  # paced: next one after `every`
            trains.tick(now=1101);self.assertTrue(trains.active)
            for _ in range(100):
                if trains.tick(now=1101): break
                time.sleep(.05)

    def test_nightly_children_run_beside_the_train_and_not_due_is_silent(self):
        import runpy
        ci=runpy.run_path(str(Path(__file__).resolve().parents[1]/'ci/siso-ci'))
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/'fake-train'
            script.write_text('import json,sys\nnight="--nightly" in sys.argv\nprint(json.dumps({"repo":sys.argv[1],"branch":sys.argv[2],"state":"not-due" if night else "green"}))\n')
            cfg={'o/r':{'train':{'branches':['halo/v2'],'every':100,'suite':'nightly'}}}
            trains=ci['Trains'](str(script))
            trains.tick.__globals__['config']=lambda:cfg
            trains.tick(now=1000)
            self.assertEqual(len(trains.running),2)
            for _ in range(100):
                done=trains.tick(now=1000)
                if done: break
                time.sleep(.05)
            time.sleep(.3);done+=trains.tick(now=1000)
            self.assertEqual([d['kind'] for d in done],['train'])  # the not-due nightly says nothing

if __name__=='__main__': unittest.main()
