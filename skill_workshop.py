"""Validate, import and version portable Skill bundles without extracting ZIPs."""
import base64
import io
import json
import re
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

import yaml

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/skill-workshop'
MAX_BYTES = 8 * 1024 * 1024
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')


def validate(content):
    if not isinstance(content, str) or len(content) > 50000:
        raise ValueError('SKILL.md 须为不超过5万字符的文本')
    match = re.fullmatch(r'---\s*\n(.*?)\n---[ \t]*\n(.*)', content.lstrip('\ufeff').replace('\r\n', '\n'), re.S)
    if not match or not match[2].strip():
        raise ValueError('SKILL.md 需要 YAML 头部和非空工作说明')
    try:
        metadata = yaml.safe_load(match[1])
    except yaml.YAMLError:
        raise ValueError('SKILL.md 的 YAML 头部格式无效') from None
    if not isinstance(metadata, dict):
        raise ValueError('YAML 头部必须包含 name 和 description')
    name, description = metadata.get('name'), metadata.get('description')
    if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name):
        raise ValueError('name 使用最多64位小写字母、数字及单个连字符')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError('description 须说明技能用途和使用场景，最多1024字')
    return {'name':name, 'description':description, 'lines':len(content.splitlines())}


def safe_path(name):
    parts = name.split('/')
    if len(name)>240 or any(not p or p in ('.','..') or p.startswith('.') or p.endswith((' ','.')) or re.search(r'[\\:*?"<>|\x00-\x1f]',p) or PurePosixPath(p).stem.upper() in {'CON','PRN','AUX','NUL',*(f'{x}{n}' for x in ('COM','LPT') for n in range(10))} for p in parts):
        raise ValueError('压缩包含无效路径或隐藏文件')
    return parts


def import_bundle(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('技能包最大8 MB')
    if path.suffix.lower()=='.md':
        content=path.read_text(encoding='utf-8-sig')
        validate(content)
        return content, {}
    if path.suffix.lower()!='.zip':
        raise ValueError('请选择 SKILL.md 或 ZIP 技能包')
    try:
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist()
            if len(entries)>100 or sum(e.file_size for e in entries)>MAX_BYTES:
                raise ValueError('技能包解压后最多8 MB、100个条目')
            files={}
            seen=set()
            for entry in entries:
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError('技能包包含链接或加密条目')
                safe_path(entry.filename.rstrip('/'))
                if entry.is_dir():continue
                key=entry.filename.casefold()
                if key in seen:raise ValueError('技能包含重复路径')
                seen.add(key)
                files[entry.filename]=archive.read(entry)
            if any('/'.join(parts[:i]).casefold() in seen
                   for name in files for parts in [name.split('/')] for i in range(1,len(parts))):
                raise ValueError('技能包内文件和目录路径冲突')
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError):
        raise ValueError('无法读取 ZIP 技能包') from None
    mains=[name for name in files if PurePosixPath(name).name=='SKILL.md' and name.count('/')<=1]
    if len(mains)!=1:raise ValueError('技能包需要一个根目录 SKILL.md')
    main=mains[0]
    prefix=main[:-len('SKILL.md')]
    content=files.pop(main).decode('utf-8-sig')
    validate(content)
    if any(not name.startswith(prefix) for name in files):raise ValueError('技能包只能包含一个技能目录')
    return content,{name[len(prefix):]:base64.b64encode(data).decode('ascii') for name,data in files.items()}


def get(ident):
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('无效版本')
    path=BASE/(ident+'.json')
    if not path.is_file():raise ValueError('版本不存在')
    return json.loads(path.read_text(encoding='utf-8'))


def save_version(content, label, parent=None, assets=None):
    metadata=validate(content)
    if not isinstance(label,str) or not label.strip() or len(label)>60:raise ValueError('请输入60字以内的版本标识')
    previous=get(parent) if parent else None
    if previous and previous['name']!=metadata['name']:raise ValueError('同一技能的版本需保留 YAML name')
    if assets is None:assets=previous['assets'] if previous else {}
    ident=uuid.uuid4().hex
    item={'id':ident,'parent':parent,'bundle':previous['bundle'] if previous else ident,'label':label.strip(),**metadata,'content':content,'assets':assets}
    BASE.mkdir(parents=True,exist_ok=True)
    from reader_tools import save
    save(BASE/(ident+'.json'),item)
    return public(item)


def public(item):
    return {**{k:v for k,v in item.items() if k!='assets'},'files':list(item['assets'])}


def versions():
    paths=sorted(BASE.glob('*.json'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
    return [{k:v for k,v in get(p.stem).items() if k not in ('assets','content')} for p in paths]


def package(item):
    output=io.BytesIO()
    root=item['name']+'/'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(root+'SKILL.md',item['content'].encode('utf-8'))
        for name,data in item['assets'].items():
            archive.writestr(root+name,base64.b64decode(data))
    return output.getvalue()


def job_options(body, reference=None):
    action=body.get('action')
    fields={'create':['name','goal','inputs','outputs','steps','dependencies'], 'revise':['content','changes'], 'test':['content','sample','expected'], 'run':['content','sample']}
    if action not in fields:raise ValueError('无效技能操作')
    data={}
    for key in fields[action]:
        value=body.get(key,'')
        if not isinstance(value,str) or len(value)>(50000 if key=='content' else 12000):raise ValueError('输入内容过长或格式错误')
        data[key]=value.strip()
    required={'create':['name','goal','inputs','outputs'],'revise':['content','changes'],'test':['content','sample','expected'],'run':['content','sample']}
    if any(not data[k] for k in required[action]):raise ValueError('请填写必填项')
    if action=='create' and (len(data['name'])>64 or not NAME.fullmatch(data['name'])):raise ValueError('技能标识请使用小写英文、数字和连字符')
    if action!='create':validate(data['content'])
    if reference:data['reference']=reference
    return {'action':action,**data}


def finish(options, response):
    if not isinstance(response,str) or not response.strip():raise ValueError('模型没有返回结果，请重试')
    if options['action'] in ('test','run'):
        if len(response)>36000:raise ValueError('模型输出超过结果长度限制')
        return {'output':response}
    content=response.strip()
    if not content.startswith('---'):
        candidates=re.findall(r'^```(?:markdown|md|text)?[ \t]*\r?\n(---\r?\n.*?)(?=\r?\n```[ \t]*(?:\r?\n|$))',content,re.M|re.S)
        if len(candidates)==1:content=candidates[0].strip()
    metadata=validate(content)
    expected=options['name'] if options['action']=='create' else validate(options['content'])['name']
    if metadata['name']!=expected:raise ValueError('模型返回的技能标识不一致，请重试')
    return {'content':content,**metadata}
