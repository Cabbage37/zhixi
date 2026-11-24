"""Extract located evidence, run the public consistency checker, validate audit output."""
import json, re, sys, zipfile, subprocess, html, hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.runtime/python'))
CHECKS=['错别字','编号跳跃','日期冲突','单位不一致','图文数字不一致','计算与勾稽关系','统计口径一致性','结论与数据一致性','名称与术语一致性','引用与资料来源','残留与遗漏']
EXTENSIONS={'.docx','.pdf','.txt','.md'}
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
C='{http://schemas.openxmlformats.org/drawingml/2006/chart}'

def extract(path):
    path=Path(path);blocks=[];limitations=[]
    def add(location,text):
        if text.strip():blocks.append({'id':f'b{len(blocks)+1:04d}','location':location,'text':text.strip()})
    if path.suffix.lower() not in EXTENSIONS:raise ValueError('支持 DOCX、PDF、TXT、MD；旧版 DOC 请先另存为 DOCX')
    if path.suffix.lower()=='.docx':
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist())>60*1024*1024:raise ValueError('文档解压后过大，请拆分')
            root=ET.fromstring(z.read('word/document.xml'));body=root.find(W+'body');para=0;table=0
            for element in body:
                if element.tag==W+'p':
                    para+=1;add(f'正文第{para}段',''.join(t.text or '' for t in element.iter(W+'t')))
                elif element.tag==W+'tbl':
                    table+=1
                    for r,row in enumerate(element.findall(W+'tr'),1):
                        add(f'表格{table}第{r}行',' | '.join(''.join(t.text or '' for t in cell.iter(W+'t')) for cell in row.findall(W+'tc')))
            for name in z.namelist():
                if re.fullmatch(r'word/(header\d+|footer\d+|footnotes|endnotes)\.xml',name):
                    r=ET.fromstring(z.read(name))
                    for i,p in enumerate(r.iter(W+'p'),1):add(f'{Path(name).stem} 第{i}段',''.join(t.text or '' for t in p.iter(W+'t')))
                if re.fullmatch(r'word/charts/chart\d+\.xml',name):
                    r=ET.fromstring(z.read(name))
                    for i,series in enumerate(r.iter(C+'ser'),1):
                        parts=[]
                        for field in ['tx','cat','val','xVal','yVal']:
                            node=series.find(C+field)
                            if node is not None:parts.append(field+': '+', '.join(t.text or '' for t in node.iter(C+'v')))
                        add(f'原生图表{Path(name).stem} 系列{i}','；'.join(parts))
            if root.find('.//'+W+'numPr') is not None:limitations.append('文档含 Word 自动编号：文本层不能完整还原显示编号，自动编号需人工复核。')
            images=sum(n.startswith('word/media/') for n in z.namelist())
            if images:limitations.append(f'文档含{images}个图片资源：图片内部文字及数字尚未核验；图文一致性仅覆盖可提取文字、表格和原生图表数据。')
            if root.find('.//'+W+'del') is not None or root.find('.//'+W+'ins') is not None:limitations.append('文档含修订痕迹，请结合 Word 修订视图复核。')
            limitations.append('DOCX 以段落/表格行定位，不推测页码。')
    elif path.suffix.lower()=='.pdf':
        import pymupdf
        with pymupdf.open(path) as doc:
            if doc.needs_pass:raise ValueError('PDF 已加密，请先提供可读取版本')
            if len(doc)>100:raise ValueError('首版单份PDF最多100页，请拆分')
            for page in doc:
                text=page.get_text(sort=True)
                for i,part in enumerate(re.split(r'\n\s*\n',text),1):add(f'第{page.number+1}页 文本块{i}',part)
                if not text.strip():limitations.append(f'第{page.number+1}页未提取到文字，需要OCR后重检。')
                elif page.get_images():limitations.append(f'第{page.number+1}页含图片，其内部文字和数字未核验。')
            limitations.append('PDF 按页定位；文本层阅读顺序可能与多栏页面不同，视觉布局和图形本身需复核。')
    else:
        raw=path.read_bytes()
        try:text=raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:text=raw.decode('gb18030')
            except UnicodeDecodeError:raise ValueError('文本编码无法读取，请另存为 UTF-8')
        for i,line in enumerate(text.splitlines(),1):add(f'第{i}行',line)
    if not blocks:raise ValueError('未提取到可检查文字，扫描件请先OCR后重传')
    if sum(len(b['text']) for b in blocks)>100000 or len(blocks)>1500:raise ValueError('材料超过10万字或1500个文本块，请拆分后检查')
    return {'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'blocks':blocks,'limitations':limitations}

def validate_options(options):
    if not isinstance(options,dict):raise ValueError('无效体检配置')
    checks=options.get('checks',CHECKS)
    if not isinstance(checks,list) or not checks or any(c not in CHECKS for c in checks):raise ValueError('请选择有效检查项')
    return {'checks':list(CHECKS),'rules':str(options.get('rules',''))[:4000],'glossary':str(options.get('glossary',''))[:4000]}

def prepare(source,folder,options):
    evidence=extract(source);folder=Path(folder);folder.mkdir(exist_ok=True)
    (folder/'source.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'options.json').write_text(json.dumps(options,ensure_ascii=False,indent=2),encoding='utf-8')
    # Public checker reads plain extraction for PDF; evidence IDs remain authoritative.
    checker_source=Path(source)
    if checker_source.suffix.lower()=='.pdf':
        checker_source=folder/'extracted.txt';checker_source.write_text('\n'.join(b['text'] for b in evidence['blocks']),encoding='utf-8')
    cmd=['node',str(ROOT/'skills/material-check/references/public-doc-consistency/scripts/check.mjs'),str(checker_source),'--json']
    if options['glossary']:
        (folder/'glossary.txt').write_text(options['glossary'],encoding='utf-8');cmd+=['--glossary',str(folder/'glossary.txt')]
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
        if proc.returncode:raise ValueError('公共检查器未完成')
        result=json.loads(proc.stdout)
    except (OSError,ValueError,subprocess.TimeoutExpired):
        result={'findings':[],'limitation':'公共一致性检查器未完成；本次仅AI检查，不能声称规则检查通过。'}
    (folder/'consistency.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return evidence

def finalize(folder):
    folder=Path(folder);source=json.loads((folder/'review/source.json').read_text(encoding='utf-8'))
    options=json.loads((folder/'review/options.json').read_text(encoding='utf-8'))
    raw=json.loads((folder/'review/draft.json').read_text(encoding='utf-8-sig'))
    lookup={b['id']:b for b in source['blocks']};issues=[];evidence_seen=set()
    if not isinstance(raw,dict) or not isinstance(raw.get('issues'),list) or len(raw['issues'])>200:raise ValueError('体检报告结构无效或问题超过200项')
    for n,item in enumerate(raw['issues'],1):
        if item.get('category') not in options['checks'] or item.get('severity') not in ['高','中','低']:raise ValueError('问题分类或级别无效')
        certainty=item.get('certainty','待核实')
        if certainty not in ['依据明确','待核实']:raise ValueError('无效判断依据状态')
        refs=[{'blockId':item.get('blockId'),'quote':item.get('quote')}]+item.get('related',[])
        for ref in refs:
            block=lookup.get(ref.get('blockId'));quote=ref.get('quote')
            if not block or not isinstance(quote,str) or not quote or quote not in block['text']:raise ValueError('报告引用与原文不匹配，不能交付')
            ref['location']=block['location']
        evidence_key=tuple(sorted((r['blockId'],r['quote']) for r in refs))
        if evidence_key in evidence_seen:raise ValueError('相同证据被重复列为多个问题，请合并为一条主要问题；不同问题应引用各自精确片段')
        evidence_seen.add(evidence_key)
        for key in ['reason','suggestion']:
            if not isinstance(item.get(key),str) or not item[key].strip():raise ValueError('缺少问题依据或建议')
        if certainty=='依据明确' and re.search(r'无法验证|无法确认|无法确定|操作数不足|缺乏.{0,15}(明细|计算|口径)|未列示.{0,15}(数据|金额)',item['reason']):
            raise ValueError('依据中表明数据不足或无法验证：必须改为待核实，并删除凭正常经营逻辑、缺失月份或非负假设推导的确定性结论，仅说明所缺依据')
        issues.append({'id':f'I{n:03d}','category':item['category'],'severity':item['severity'],'certainty':certainty,'reason':item['reason'][:3000],
            'replacement':item.get('replacement') if isinstance(item.get('replacement'),str) else None,'substantive':item.get('substantive',True) is not False,'suggestion':item['suggestion'][:3000],'evidence':refs,'status':'待复核'})
    reviewed=raw.get('reviewedBlockIds',[])
    if not isinstance(reviewed,list) or any(x not in lookup for x in reviewed):raise ValueError('无效检查覆盖记录')
    reviewed=set(reviewed);limits=list(source['limitations'])
    extra=raw.get('limitations',[])
    if not isinstance(extra,list) or any(not isinstance(x,str) for x in extra):raise ValueError('无效限制说明')
    limits+=extra
    if len(reviewed)<len(lookup):limits.append(f'本次仅覆盖{len(reviewed)}/{len(lookup)}个文本块，未覆盖部分不能视为检查通过。')
    checker=json.loads((folder/'review/consistency.json').read_text(encoding='utf-8'))
    if checker.get('limitation'):limits.append(checker['limitation'])
    report={'name':source['name'],'checks':options['checks'],'issues':issues,'limitations':list(dict.fromkeys(limits)),
        'coverage':{'reviewed':len(reviewed),'total':len(lookup)},'blocks':source['blocks'],'sourceHash':source['sha256']}
    original=next((p for p in (folder/'inputs').glob('*.docx')),None)
    if original:
        from review_document import enrich_report
        enrich_report(report,original)
    out=folder/'outputs';out.mkdir(exist_ok=True)
    (out/'材料体检.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=['# 材料体检报告',f'材料：{source["name"]}',f'发现 {len(issues)} 项待复核问题；检查覆盖 {len(reviewed)}/{len(lookup)} 个文本块。','原文件未修改；无问题不代表所有内容正确。']
    for issue in issues:
        rows += [f'## {issue["id"]} · {issue["category"]} · {issue["severity"]}优先级 · {issue["certainty"]}']
        rows += [r['location']+'：'+r['quote'] for r in issue['evidence']]
        rows += ['依据：'+issue['reason'],'建议：'+issue['suggestion']]
    rows+=['## 覆盖限制']+report['limitations']
    (out/'材料体检报告.md').write_text('\n\n'.join(rows),encoding='utf-8')
    (out/'材料体检报告.html').write_text('<!doctype html><meta charset="utf-8"><title>材料体检报告</title><style>body{max-width:960px;margin:40px auto;padding:20px;font:16px/1.8 system-ui;color:#292929}pre{white-space:pre-wrap}</style><pre>'+html.escape('\n\n'.join(rows))+'</pre>',encoding='utf-8')
    return report

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    report=finalize(sys.argv[1]);print(f'已生成体检报告：{len(report["issues"])}项待复核问题。')
