import unittest,tempfile,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from repurpose_tools import prepare,finalize,save,validate_options,KINDS

class RepurposeTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  (self.root/'outputs').mkdir();self.source=self.root/'source.txt'
  self.source.write_text('项目预算120万元，拟于2026年12月启动，目前尚未审批。',encoding='utf-8')
  prepare(self.source,self.root/'repurpose',{'kinds':KINDS,'limit':300})
  save(self.root/'repurpose/fidelity-review.json',{'reviewed':True,'removedUnsupportedClaims':[],'remainingUncertainties':[]})
  self.draft={'variants':[{'kind':k,'title':k,'paragraphs':[{'text':'项目预算120万元，拟于2026年12月启动，目前尚未审批。','evidence':[{'blockId':'b0001','quote':'项目预算120万元，拟于2026年12月启动，目前尚未审批。'}]}]} for k in KINDS]}
 def run_draft(self):save(self.root/'repurpose/draft.json',self.draft);return finalize(self.root)
 def test_selected_exports_and_evidence(self):
  result=self.run_draft();self.assertEqual(len(result['variants']),4)
  self.assertTrue(all(not v['warnings'] for v in result['variants']))
  with zipfile.ZipFile(self.root/'outputs/一稿多用合集.zip') as z:self.assertEqual(len(z.namelist()),8)
  self.assertIn('尚未审批',(self.root/'outputs/邮件正文.txt').read_text(encoding='utf-8-sig'))
 def test_fabricated_quote_rejected_atomically(self):
  self.draft['variants'][-1]['paragraphs'][0]['evidence'][0]['quote']='已经批准'
  with self.assertRaisesRegex(ValueError,'引用'):self.run_draft()
  self.assertFalse(list((self.root/'outputs').iterdir()))
 def test_missing_version_rejected(self):
  self.draft['variants'].pop()
  with self.assertRaisesRegex(ValueError,'数量'):self.run_draft()
 def test_length_enforced(self):
  self.draft['variants'][0]['paragraphs'][0]['text']='长'*301
  with self.assertRaisesRegex(ValueError,'超过'):self.run_draft()
 def test_unmatched_number_flagged(self):
  self.draft['variants'][0]['paragraphs'][0]['text']='预算999万元。'
  self.assertIn('999',self.run_draft()['variants'][0]['warnings'][0])
 def test_invalid_options(self):
  for value in [{'kinds':[]},{'kinds':['发送邮件']},{'kinds':KINDS,'limit':True},{'kinds':KINDS,'tone':'编造'}]:
   with self.assertRaises(ValueError):validate_options(value)
 def test_unsupported_commitment_warns(self):
  self.draft['variants'][0]['paragraphs'].append({'text':'后续会及时通报。','evidence':[]})
  self.assertTrue(any('承诺' in w for w in self.run_draft()['variants'][0]['warnings']))

if __name__=='__main__':unittest.main()
