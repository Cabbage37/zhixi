"""Local source-page comparison; document-diff workflow adaptation."""
import sys, json, difflib, re, subprocess, shutil, os
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.runtime/python'))
import fitz

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')

def render(source,folder,side):
    pdf=folder/(side+'.pdf')
    if source.suffix.lower()=='.pdf':shutil.copy2(source,pdf)
    elif source.suffix.lower() in ['.doc','.docx']:
        env=os.environ.copy();env['COMPARE_SOURCE']=str(source.resolve());env['COMPARE_DESTINATION']=str(pdf.resolve())
        script=(ROOT/'scripts/compare-word.ps1').read_text(encoding='utf-8').replace('param([string]$Source,[string]$Destination)', '$Source=$env:COMPARE_SOURCE; $Destination=$env:COMPARE_DESTINATION')
        subprocess.run(['powershell','-NoProfile','-Command',script],env=env,check=True,capture_output=True,timeout=120)
    else:raise ValueError('版本对比支持 PDF、DOC 和 DOCX')
    pages=[];chars=[]
    with fitz.open(pdf) as doc:
        if doc.needs_pass or not 0<len(doc)<=100:raise ValueError('请使用未加密且不超过100页的材料')
        for n,page in enumerate(doc):
            if max(page.rect.width,page.rect.height)>3000:raise ValueError('页面尺寸过大')
            image=f'{side}-{n+1}.png';page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(folder/image)
            start=len(chars)
            for block in page.get_text('rawdict',sort=True)['blocks']:
                for line in block.get('lines',[]):
                    for span in line['spans']:
                        for c in span['chars']:
                            if not c['c'].isspace():chars.append({'c':c['c'],'page':n,'box':list(c['bbox'])})
            scanned=len(chars)==start
            if scanned:
                from comparison_vision import transcribe
                chars.extend(transcribe(folder/image,page.rect.width,page.rect.height,n))
            dump(folder/'progress.json',{'message':f'{side}：已处理 {n+1}/{len(doc)} 页'+('（多模态识别）' if scanned else '')})
            pages.append({'unlocated':any(c.get('unlocated') for c in chars[start:]),'ocr':scanned,'image':image,'width':page.rect.width,'height':page.rect.height})
    if not chars:raise ValueError('文档未提取到可对比文字')
    if len(chars)>120000:raise ValueError('单份材料最多12万字')
    return {'name':source.name,'pages':pages},chars

def compare(a,b):
    old=''.join(c['c'] for c in a);new=''.join(c['c'] for c in b)
    changes=[];votes={}
    def lines(chars):
        groups=[];starts=[]
        for n,c in enumerate(chars):
            if not groups or c['page']!=chars[n-1]['page'] or c.get('ocrLine')!=chars[n-1].get('ocrLine') or abs(c['box'][1]-chars[n-1]['box'][1])>3:
                groups.append('');starts.append(n)
            groups[-1]+=c['c']
        return groups,starts+[len(chars)]
    al,ai=lines(a);bl,bi=lines(b);ops=[]
    for tag,i,j,k,l in difflib.SequenceMatcher(None,al,bl,autojunk=False).get_opcodes():
        x,y,u,v=ai[i],ai[j],bi[k],bi[l]
        if tag=='replace' and max(j-i,l-k)<=200:
            # Align similar lines before character comparison; an inserted line must
            # not borrow the matching suffix of its neighbouring paragraph.
            cursor=k
            for row in range(i,j):
                scores=[(difflib.SequenceMatcher(None,al[row],bl[col],autojunk=False).ratio(),col) for col in range(cursor,l)]
                best=max(scores,default=(0,cursor),key=lambda z:(z[0],-z[1]))
                if best[0]<0.55:
                    ops.append(('delete',ai[row],ai[row+1],bi[cursor],bi[cursor]));continue
                col=best[1]
                if col>cursor:ops.append(('insert',ai[row],ai[row],bi[cursor],bi[col]))
                left,right=ai[row],bi[col]
                ops.extend((t,left+h,left+z,right+m,right+n) for t,h,z,m,n in difflib.SequenceMatcher(None,al[row],bl[col],autojunk=False).get_opcodes())
                cursor=col+1
            if cursor<l:ops.append(('insert',ai[j],ai[j],bi[cursor],bi[l]))
        else:ops.append((tag,x,y,u,v))
    for tag,i,j,k,l in ops:
        if tag=='equal':
            for x,y in zip(a[i:j],b[k:l]):
                pair=(x['page'],y['page']);votes[pair]=votes.get(pair,0)+1
            continue
        def marks(chars):
            boxes=[]
            for c in chars:
                if c.get('unlocated'):continue
                x0,y0,x1,y1=c['box'];p=c['page']
                if boxes and boxes[-1]=={'page':p,'box':[x0,y0,x1,y1]}:continue
                if boxes and boxes[-1]['page']==p and abs(boxes[-1]['box'][1]-y0)<2 and abs(boxes[-1]['box'][3]-y1)<2 and 0<=x0-boxes[-1]['box'][2]<5:boxes[-1]['box'][2]=x1
                else:boxes.append({'page':p,'box':[x0,y0,x1,y1]})
            return boxes
        changes.append({'id':len(changes)+1,'kind':{'replace':'修改','insert':'新增','delete':'删除'}[tag],'old':old[i:j],'new':new[k:l],'oldContext':old[max(0,i-50):min(len(old),j+50)],'newContext':new[max(0,k-50):min(len(new),l+50)],'numeric':bool(re.search(r'\d',old[i:j]+new[k:l])),'left':marks(a[i:j]),'right':marks(b[k:l]),'anchorLeft':a[min(i,len(a)-1)]['page'],'anchorRight':b[min(k,len(b)-1)]['page']})
    mapping={}
    for p,q in votes:
        if p not in mapping or votes[p,q]>votes[p,mapping[p]]:mapping[p]=q
    return changes,mapping

def prepare(folder):
    job=json.loads((folder/'task.json').read_text(encoding='utf-8'))
    preview=folder/'comparison';preview.mkdir(exist_ok=True)
    docs=[];letters=[]
    for side,fid in zip(['old','new'],job['comparison']['files']):
        found=list((folder/'inputs').glob(fid[:6]+'_*'))
        if len(found)!=1:raise ValueError('无法确定旧版或新版文件')
        doc,chars=render(found[0],preview,side);docs.append(doc);letters.append(chars)
    changes,mapping=compare(*letters)
    result={'documents':docs,'changes':changes,'pageMap':mapping,'scope':'文字页直接读取，扫描页默认使用已配置多模态模型识别。扫描页高亮为模型估计的行级位置，坐标不可用时仅定位到页，不绘制虚假高亮。OCR可能存在错漏，差异需对照原图复核；忽略空白，不比较纯版式和非文字图形。'}
    dump(preview/'result.json',result)
    dump(folder/'outputs/版本差异.json',result)
    (folder/'outputs/版本差异.md').write_text('# 版本差异\n\n'+result['scope']+'\n\n'+'\n\n'.join(f"## {c['id']} · {c['kind']}\n旧版：{c['old']}\n新版：{c['new']}" for c in changes),encoding='utf-8')
    return result

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    folder=Path(sys.argv[1]).resolve()
    try: print(json.dumps({'changes':len(prepare(folder)['changes'])},ensure_ascii=False))
    except Exception as e:
        (folder/'comparison').mkdir(exist_ok=True);dump(folder/'comparison/error.json',{'error':str(e)});raise
