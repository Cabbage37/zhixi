import sys,tempfile,json,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from material_tools import extract,prepare,finalize,validate_options,CHECKS

assert len(validate_options({})['checks'])==11
assert validate_options({'checks':['错别字']})['checks']==CHECKS

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);source=root/'sample.txt';source.write_text('一、经营情况\n本期收入为100万元。\n三、经营展望\n同口径收入为120万元。',encoding='utf-8')
    before=source.read_bytes();opts=validate_options({'checks':['编号跳跃','图文数字不一致']})
    evidence=prepare(source,root/'review',opts)
    assert evidence['blocks'][0]['location']=='第1行'
    public=json.loads((root/'review/consistency.json').read_text(encoding='utf-8'));assert 'findings' in public and not public.get('limitation')
    draft={'reviewedBlockIds':[b['id'] for b in evidence['blocks']],'limitations':[],
           'issues':[{'category':'图文数字不一致','severity':'高','blockId':'b0002','quote':'100万元','related':[{'blockId':'b0004','quote':'120万元'}],'reason':'同口径数字不同','suggestion':'核对原始收入数据'}]}
    (root/'review/draft.json').write_text(json.dumps(draft,ensure_ascii=False),encoding='utf-8')
    report=finalize(root);assert len(report['issues'])==1 and report['coverage']['reviewed']==4
    assert report['issues'][0]['evidence'][1]['location']=='第4行'
    assert report['issues'][0]['certainty']=='待核实'
    for category in CHECKS[5:]:
        draft['issues'][0]['category']=category
        draft['issues'][0]['certainty']='依据明确'
        (root/'review/draft.json').write_text(json.dumps(draft,ensure_ascii=False),encoding='utf-8')
        expanded=finalize(root)
        assert expanded['issues'][0]['category']==category
        assert expanded['issues'][0]['certainty']=='依据明确'
    draft['issues'].append(dict(draft['issues'][0]))
    (root/'review/draft.json').write_text(json.dumps(draft,ensure_ascii=False),encoding='utf-8')
    try:finalize(root);raise AssertionError('duplicate evidence accepted')
    except ValueError as e:assert '重复' in str(e)
    draft['issues'].pop()
    original_reason=draft['issues'][0]['reason']
    draft['issues'][0]['reason']='操作数不足，无法验证结论'
    (root/'review/draft.json').write_text(json.dumps(draft,ensure_ascii=False),encoding='utf-8')
    try:finalize(root);raise AssertionError('uncertain reasoning accepted as definite')
    except ValueError as e:assert '待核实' in str(e)
    draft['issues'][0]['certainty']='待核实'
    (root/'review/draft.json').write_text(json.dumps(draft,ensure_ascii=False),encoding='utf-8')
    assert finalize(root)['issues'][0]['certainty']=='待核实'
    draft['issues'][0]['reason']=original_reason
    assert source.read_bytes()==before
    draft['issues'][0]['quote']='编造引文'
    (root/'review/draft.json').write_text(json.dumps(draft),encoding='utf-8')
    try:finalize(root);raise AssertionError('invented evidence accepted')
    except ValueError:pass
    doc=root/'sample.docx'
    with zipfile.ZipFile(doc,'w') as z:
        z.writestr('word/document.xml','''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>正文收入100万元</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>表格收入</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>120万元</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>''')
    parsed=extract(doc);assert parsed['blocks'][1]['location']=='表格1第1行'
    assert parsed['blocks'][1]['text']=='表格收入 | 120万元'
    import pymupdf
    pdf=pymupdf.open();page=pdf.new_page();page.insert_text((72,72),'Revenue 100 million');pdf.save(root/'sample.pdf');pdf.close()
    parsed=extract(root/'sample.pdf');assert '第1页' in parsed['blocks'][0]['location']
    print('PASS: public checker execution, TXT/DOCX/PDF locations, exact evidence validation, reports, source preservation')
