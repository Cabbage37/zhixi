import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import learning_tools as learning

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.source={'learning':{'mode':'grill','level':'入门','selection':None},'blocks':[{'id':'b0001','location':'第一段','text':'收入120万元不代表净利润。'}]}
        self.draft={'lesson':'','feedback':'','nextQuestion':'收入是否等于净利润？','assessment':'未作答','difficulty':'入门','mastered':[],'gaps':[],'citations':[{'blockId':'b0001','quote':'收入120万元不代表净利润。'}]}
    def test_start_without_giving_answer(self):
        o=learning.prepare(self.source,{'action':'start'},[])
        self.assertEqual(learning.validate(self.source,o,self.draft)['coaching']['assessment'],'未作答')
        self.draft['lesson']='不等于';self.assertRaises(ValueError,learning.validate,self.source,o,self.draft)
    def test_no_fake_mastery(self):
        self.draft['mastered']=['利润概念'];self.assertRaises(ValueError,learning.validate,self.source,{'action':'start'},self.draft)
    def test_quote_must_match_source(self):
        self.draft['citations'][0]['quote']='净利润为120万元'
        self.assertRaises(ValueError,learning.validate,self.source,{'action':'start'},self.draft)
    def test_topic_has_no_fake_citations(self):
        self.source['blocks']=[]
        self.assertRaises(ValueError,learning.validate,self.source,{'action':'start'},self.draft)
        self.draft['citations']=[];self.assertTrue(learning.validate(self.source,{'action':'start'},self.draft))
    def test_stale_answer_rejected(self):
        history=[{'taskId':'latest','coaching':{'nextQuestion':'q'}}]
        self.assertRaises(ValueError,learning.prepare,self.source,{'action':'answer','question':'a','previousTask':'old'},history)
        self.assertRaises(ValueError,learning.prepare,self.source,{'action':'answer','question':'','previousTask':'latest'},history)
    def test_hint_keeps_current_question(self):
        o={'action':'hint','history':[{'coaching':{'nextQuestion':self.draft['nextQuestion']}}]}
        self.assertTrue(learning.validate(self.source,o,self.draft))
        self.draft['nextQuestion']='another';self.assertRaises(ValueError,learning.validate,self.source,o,self.draft)
    def test_recap_no_new_question(self):
        self.assertRaises(ValueError,learning.validate,self.source,{'action':'recap'},self.draft)
        self.draft.update(nextQuestion='',feedback='尚未回答，无法评估。')
        self.assertTrue(learning.validate(self.source,{'action':'recap'},self.draft))
    def test_recap_cannot_count_as_new_answer(self):
        self.draft.update(nextQuestion='',feedback='之前的回答尚需巩固。',assessment='需要巩固')
        self.assertEqual(learning.validate(self.source,{'action':'recap'},self.draft)['coaching']['assessment'],'未评估')

if __name__=='__main__':unittest.main()
