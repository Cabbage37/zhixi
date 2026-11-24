import sys,json,tempfile,os,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import screenshot_tools as tool
from openpyxl import load_workbook
import pymupdf

def cell(text,uncertain=False):return {'text':text,'uncertain':uncertain,'reviewed':False,'reason':'字符模糊' if uncertain else ''}
sample={'tables':[{'name':'测试/表','rows':[[cell('项目'),cell('数值')],[cell('0012'),cell('-0.15%',True)],[cell('=1+1'),cell('2026-01-02')]],'merges':[]}]}
with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp);(p/'inputs').mkdir();(p/'recognition').mkdir()
    doc=pymupdf.open();page=doc.new_page(width=100,height=80);page.insert_text((10,20),'Test');page.get_pixmap().save(p/'inputs/test.png');doc.close()
    assert tool.inspect_image(p/'inputs/test.png')['width']==100
    normalized=tool.validate_tables(sample);assert normalized[0]['rows'][1][1]['uncertain']
    assert not normalized[0]['rows'][1][1]['reviewed']
    try:tool.export_tables(p,sample);raise AssertionError('unreviewed uncertainty accepted')
    except ValueError:pass
    reviewed=copy.deepcopy(sample);reviewed['tables'][0]['rows'][1][1]['reviewed']=True
    name=tool.export_tables(p,reviewed);book=load_workbook(p/'outputs'/name);ws=book.active
    assert ws['A2'].value=='0012' and ws['B2'].value=='-0.15%' and ws['B3'].value=='2026-01-02'
    assert ws['A3'].value=='=1+1' and ws['A3'].data_type=='s';book.close()
    reviewed['format']='csv';name=tool.export_tables(p,reviewed);assert "'=1+1" in (p/'outputs'/name).read_text(encoding='utf-8-sig')
    merged={'tables':[{'name':'合并','rows':[[cell('标题'),cell('')],[cell('A'),cell('B')]],'merges':[{'r':0,'c':0,'rowspan':1,'colspan':2}]}]}
    name=tool.export_tables(p,merged);book=load_workbook(p/'outputs'/name);assert 'A1:B1' in book.active.merged_cells;book.close()
    merged['tables'][0]['rows'][0][1]['text']='不能丢失'
    try:tool.validate_tables(merged);raise AssertionError('merge data loss accepted')
    except ValueError:pass
    assert tool.glm_markdown('| A | B |\n|---|---|\n|001|2|')['tables'][0]['rows'][1][0]['text']=='001'
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(sample)}}]}).encode()
    with patch.dict(os.environ,{'TABLE_RECOGNITION_MODE':'vision','TABLE_VISION_API_KEY':'fixture-only','TABLE_VISION_BASE_URL':'https://example.invalid/v1','TABLE_VISION_MODEL':'fixture-model'}):
        with patch.object(tool,'urlopen',return_value=Response()) as request:
            result=tool.recognize(p);assert len(result['tables'])==1
            req=request.call_args.args[0];body=json.loads(req.data)
            assert body['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
            assert not result['tables'][0]['rows'][1][1]['reviewed']
        with patch.dict(os.environ,{'TABLE_VISION_API_KEY':''}):
            try:tool.recognize(p);raise AssertionError('missing key accepted')
            except ValueError:pass
    print('PASS: image validation, multimodal request/response fixture, uncertainty guard, merged cells, exact text, CSV formula protection, missing key')
