"""DOCX review anchors and guarded OOXML revisions; never edit the source."""
import hashlib,json,re,zipfile,io
from pathlib import Path
import sys,os
if os.name=='nt':sys.path.insert(0,str(Path(__file__).resolve().parent/'.runtime/python'))
if os.name=='nt':
    from lxml import etree as ET
else:
    import xml.etree.ElementTree as ET
W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
XML='{http://www.w3.org/XML/1998/namespace}'

def paragraphs(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if sum(i.file_size for i in z.infolist())>60*1024*1024:raise ValueError('DOCX解压体积过大')
        root=ET.fromstring(z.read('word/document.xml'),ET.XMLParser(resolve_entities=False,no_network=True)) if os.name=='nt' else ET.fromstring(z.read('word/document.xml'))
    return root,list(root.iter(W+'p'))

def locate(data,quote):
    _,ps=paragraphs(data);matches=[]
    for index,p in enumerate(ps):
        value=''.join(t.text or '' for t in p.iter(W+'t'))
        start=0
        while quote and (start:=value.find(quote,start))>=0:
            matches.append({'part':'word/document.xml','paragraphIndex':index,'paragraphText':value,'paragraphHash':hashlib.sha256(value.encode()).hexdigest(),'start':start,'end':start+len(quote),'quote':quote});start+=len(quote)
    return matches

def enrich_report(report,source):
    if source.suffix.lower()!='.docx':return report
    data=source.read_bytes()
    for issue in report['issues']:
        quote=issue['evidence'][0]['quote'];matches=locate(data,quote)
        # Repeated source text must never silently target the first occurrence.
        issue['anchor']=matches[0] if len(matches)==1 else None
        issue['editable']=len(matches)==1 and isinstance(issue.get('replacement'),str)
        issue['locationStatus']='准确定位' if len(matches)==1 else '引用跨段或存在多处匹配，需手动定位'
    return report

def check_locks(before,after,terms,lock_numbers=True):
    if lock_numbers and re.findall(r'\d+(?:[.,]\d+)*(?:%|％)?',before)!=re.findall(r'\d+(?:[.,]\d+)*(?:%|％)?',after):raise ValueError('数字已锁定，请先明确解除数字保护')
    for term in terms:
        if term and before.count(term)!=after.count(term):raise ValueError('受保护术语发生变化：'+term)

def replace_range(data,anchor,replacement,terms=(),lock_numbers=True):
    root,ps=paragraphs(data)
    if not isinstance(replacement,str) or len(replacement)>10000 or '\n' in replacement:raise ValueError('此修订只支持单段文字替换')
    index=anchor['paragraphIndex']
    if not isinstance(index,int) or not 0<=index<len(ps):raise ValueError('段落锚点失效')
    p=ps[index];nodes=list(p.iter(W+'t'));before=''.join(t.text or '' for t in nodes)
    a,b=anchor['start'],anchor['end']
    if hashlib.sha256(before.encode()).hexdigest()!=anchor['paragraphHash'] or not 0<=a<b<=len(before) or before[a:b]!=anchor['quote']:raise ValueError('原文已变化，拒绝替换；请重新定位或重新体检')
    after=before[:a]+replacement+before[b:];check_locks(before,after,terms,lock_numbers)
    pos=0;inserted=False
    for node in nodes:
        value=node.text or '';end=pos+len(value)
        if pos<b and end>a:
            left=value[:max(0,a-pos)];right=value[max(0,b-pos):]
            node.text=left+(replacement if not inserted else '')+right;node.set(XML+'space','preserve');inserted=True
        pos=end
    output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src,zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():dst.writestr(item,ET.tostring(root,encoding='utf-8',xml_declaration=True) if item.filename=='word/document.xml' else src.read(item.filename))
    return output.getvalue()
