import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from comparison_vision import normalize_lines
from comparison_tools import compare

class VisionNormalizationTest(unittest.TestCase):
 def test_numeric_strings(self):
  c=normalize_lines({'lines':[{'text':'120万元','bbox':['10','20','300','50']}]},600,800,0)
  self.assertFalse(c[0]['unlocated']);self.assertEqual(c[0]['box'],[6,16,180,40])
 def test_invalid_coordinates_keep_text_not_highlight(self):
  a=normalize_lines({'lines':[{'text':'100万元','bbox':None}]},600,800,0)
  b=normalize_lines({'lines':[{'text':'120万元','bbox':[0,0,9999,10]}]},600,800,0)
  changes,_=compare(a,b)
  self.assertTrue(changes);self.assertEqual(changes[0]['left'],[]);self.assertEqual(changes[0]['right'],[])
 def test_blank_lines_ignored(self):
  c=normalize_lines({'lines':[{'text':' '},{'text':'正文'}]},600,800,1)
  self.assertEqual(''.join(x['c'] for x in c),'正文')
 def test_missing_text_rejected(self):
  with self.assertRaises(ValueError):normalize_lines({'lines':[{'bbox':[]}]},600,800,0)

if __name__=='__main__':unittest.main()
