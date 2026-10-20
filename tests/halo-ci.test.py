import importlib.machinery, importlib.util, sys, unittest, tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ci'))
loader=importlib.machinery.SourceFileLoader('halo_ci',str(ROOT/'ci/siso-ci'))
spec=importlib.util.spec_from_loader(loader.name,loader);ci=importlib.util.module_from_spec(spec);sys.modules[loader.name]=ci;loader.exec_module(ci)
class HaloCI(unittest.TestCase):
 def test_pr_head_uses_affected_status_and_merge_base(self):
  cfg={'test':'sh .siso-ci','pr_mode':'affected','pr_status':'siso-ci/affected'}
  pr={'headRefOid':'head','baseRefOid':'base','number':1}
  with patch.object(ci,'checkout',return_value='/fixture') as checkout, patch.object(ci,'commands',return_value={'test':'sh .siso-ci'}), patch.object(ci,'sh') as sh, patch.object(ci.affected,'select',side_effect=lambda d,c,b,h:{**c,'selection':{'mode':'full','total':None,'reason':'fixture'}}), patch.object(ci,'run_tests',return_value=(0,'',1)) as run, patch.object(ci,'post_status') as status, patch.object(ci,'state_save'):
   sh.return_value.stdout='mergebase\n';st={}
   self.assertEqual(ci.run_pr('fixture/repo',cfg,pr,st),'success')
   checkout.assert_called_once_with('fixture/repo','head','pull/1/head')
   self.assertEqual(run.call_args.args[2]['ci_mode'],'affected');self.assertEqual(run.call_args.args[3],'mergebase')
   self.assertEqual(status.call_args.kwargs['context'],'siso-ci/affected')
   self.assertIn('fixture/repo@head:siso-ci/affected',st['done'])
 def test_full_is_default(self):
  with tempfile.TemporaryDirectory() as d:
   code,out,_=ci.run_tests('fixture/repo',d,{'test':'test "$SISO_CI_MODE" = full'},'base')
   self.assertEqual(code,0,out)
if __name__=='__main__':unittest.main()
