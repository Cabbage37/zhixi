import unittest,tempfile,json,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from comparison_tools import prepare,fitz

class ComparisonTest(unittest.TestCase):
 def run_pair(self,old,new):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);folder=Path(temp.name)
  (folder/'inputs').mkdir();(folder/'outputs').mkdir()
  hashes={}
  for name,pages in [('aaaaaa_old.pdf',old),('bbbbbb_new.pdf',new)]:
   path=folder/'inputs'/name
   with fitz.open() as doc:
    for text in pages:doc.new_page().insert_text((60,70),text)
    doc.save(path)
   hashes[path]=hashlib.sha256(path.read_bytes()).hexdigest()
  (folder/'task.json').write_text(json.dumps({'comparison':{'files':['aaaaaa','bbbbbb']}}))
  result=prepare(folder)
  for path,digest in hashes.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
  self.assertTrue((folder/'comparison/old-1.png').is_file())
  return result
 def test_inserted_page_alignment(self):
  r=self.run_pair(['Alpha introduction','Beta financial conclusion'],['Alpha introduction','Extra newly inserted chapter','Beta financial conclusion'])
  self.assertEqual(r['pageMap'][1],2)
  self.assertTrue(any(c['kind']=='新增' for c in r['changes']))
 def test_numeric_source_coordinates(self):
  r=self.run_pair(['Revenue 100 million'],['Revenue 120 million'])
  c=r['changes'][0];self.assertTrue(c['numeric']);self.assertTrue(c['left']);self.assertTrue(c['right'])
  self.assertEqual(c['old'],'0');self.assertEqual(c['new'],'2')
 def test_identical(self):self.assertEqual(self.run_pair(['same'],['same'])['changes'],[])
 def test_insert_between_modified_lines(self):
  r=self.run_pair(['Revenue 100 million','Operating profit 20 million'],['Revenue 120 million','New business section','Operating profit 25 million'])
  self.assertEqual([c['new'] for c in r['changes'] if c['kind']=='新增'],['Newbusinesssection'])
 def test_deletion(self):self.assertTrue(any(c['kind']=='删除' for c in self.run_pair(['Start removed End'],['Start End'])['changes']))

if __name__=='__main__':unittest.main()
