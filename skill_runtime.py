"""Resolve built-in business instructions and their shared review methods."""
from pathlib import Path

SKILLS = Path(__file__).resolve().parent / 'skills'
METHODS = {
    'financial-quick-research': ('evidence', 'finance'),
    'macro-analysis': ('finance',),
    'public-opinion-monitor': ('evidence',),
    'sentiment-observation': ('evidence',),
    'reading-assistant': ('evidence',),
    'cross-document': ('evidence',),
    'content-repurpose': ('quality',),
    'document-compare': ('quality',),
    'material-check': ('quality',),
}

def shared_rules(name):
    return '\n'.join((SKILLS / '_shared' / (key + '.md')).read_text(encoding='utf-8')
                     for key in METHODS.get(name, ()))

# Only load the part used by this business action. The host owns files and export.
UPSTREAM = {
    'skill-workshop': ('skill-workshop/references/openai-skill-creator/SKILL.md', '## Core Principles', '## Anatomy'),
    'app-builder': ('skill-workshop/references/openai-skill-creator/SKILL.md', '### Validate and Iterate', '## Independent'),
    'material-check': ('material-check/references/public-proofreader/SKILL.md', '#### Grammar', '### ❌'),
    'content-repurpose': ('content-repurpose/references/public-content-repurposer/SKILL.md', '- **One insight', '- **No emoji'),
    'learning-coach': ('learning-coach/references/upstream/teach.md', '## Philosophy', '\n## '),
    'document-standardize': ('_shared/deepseek-office/office-docx/SKILL.md', '## Create and edit', '## Check'),
    'excel-chart': ('_shared/deepseek-office/office-xlsx/SKILL.md', '## Read and modify', '## Check'),
}

def upstream_rules(name, folder=None, section=None):
    import hashlib
    import json
    if name not in UPSTREAM:
        return ''
    path, start, end = section or UPSTREAM[name]
    raw=(SKILLS/path).read_bytes()
    content=raw.decode('utf-8-sig')
    offset=content.index(start)
    excerpt=content[offset:content.index(end,offset+len(start))]
    if folder:
        record={'file':path,'sha256':hashlib.sha256(raw).hexdigest(),'section':start}
        import uuid
        target=folder/(name+'-upstream.json')
        temp=target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        temp.write_text(json.dumps(record,ensure_ascii=False),encoding='utf8')
        temp.replace(target)
    return excerpt

def instructions(name, folder=None):
    local=(SKILLS / name / 'SKILL.md').read_text(encoding='utf-8-sig')
    return local+'\n'+shared_rules(name)+'\n'+upstream_rules(name,folder)+'\n以上上游方法按知析当前任务、输入输出和可用工具执行。'

def contextual_skill(job):
    if job.get('standardization'):
        return 'document-standardize'
    if job.get('workshop'):
        return 'skill-workshop'
    if job.get('reader'):
        return 'learning-coach' if job.get('learning') else 'reading-assistant'
    for key, name in [('comparison', 'document-compare'), ('repurpose', 'content-repurpose'),
                      ('excel', 'excel-chart'), ('material', 'material-check'), ('screenshot', 'screenshot-table')]:
        if job.get(key):
            return name
    return None
