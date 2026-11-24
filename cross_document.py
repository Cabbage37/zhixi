"""Prepare local material excerpts for a comparative answer."""
from material_tools import extract


def collect(question, paths):
    sources, failures, notes, readable = [], [], [], 0
    for material_id,path in enumerate(paths,1):
        try:
            if path.suffix.lower()=='.pdf':
                import pymupdf
                blocks=[]
                with pymupdf.open(path) as pdf:
                    length=0
                    for page in pdf:
                        content=page.get_text(sort=True).strip()
                        if content:
                            blocks.append(dict(text=content,location=f'第{page.number+1}页'))
                            length+=len(content)
                        if length>=6000:break
                document=dict(blocks=blocks)
            else:
                document = extract(path)
            blocks = document['blocks']
            if not blocks:
                raise ValueError('没有可提取的文字')
            readable += 1
            remaining = 6000
            for block in blocks:
                value = ' '.join(block['text'].split())
                if not remaining:
                    break
                sources.append({'id': len(sources)+1, 'title': path.name, 'materialId': material_id,
                                'location': block['location'], 'text': value[:remaining]})
                remaining -= min(remaining, len(value))
            if not remaining:
                notes.append({'file': path.name, 'text': '仅纳入正文前 6,000 字符'})
            for limitation in document.get('limitations', []):
                notes.append({'file': path.name, 'text': limitation})
        except Exception:
            failures.append({'url': path.name, 'error': '未能读取可用文字，请检查文件格式或扫描情况'})
    if readable < 2:
        failures.append({'url': '', 'error': '至少需要两份可提取正文的材料'})
        sources = []
    return {'theme': question, 'sources': sources, 'failures': failures, 'notes': notes}
