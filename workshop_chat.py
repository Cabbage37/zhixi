"""Co-creation turns on the existing local Harness, exposed as AG-UI events."""
import json
import logging
from workshop_stream import model_stream, ReplyStream
import threading
import uuid
from pathlib import Path
from application_tools import decode
from model_settings import model_settings


ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data/workshop-threads'
BUSY_THREADS = set()
ACTIVE = {}
ACTIVE_LOCK = threading.Lock()

def stop_run(run_id):
    with ACTIVE_LOCK:
        stop = ACTIVE.get(run_id)
    if stop:
        stop()
    return {'stopped': bool(stop)}


def library_item(ident, base=None):
    folder=(base or BASE)/uuid.UUID(ident).hex
    path=folder/'state.json'
    if not path.is_file():raise ValueError('找不到这个工坊方案')
    state=json.loads(path.read_text('utf8'))
    state['workshopThread']=folder.name
    state['saved']=(folder/'saved').exists()
    return state

SECTIONS = ('每次提供什么', '请怎么做', '把结果给我')

def decode_plan(text):
    try:
        return decode(text)
    except json.JSONDecodeError:
        import re
        fenced = re.search(r"```json\s*(.*?)\s*```", text, re.I | re.S)
        if fenced:
            return json.loads(fenced[1])
        raw = text.strip()
        result, end = json.JSONDecoder().raw_decode(raw)
        if set(raw[end:].strip()) != {'}'}:
            raise
        return result

def plan_update(value, fields=SECTIONS):
    sections = value.get('sections')
    if isinstance(sections,list) and all(isinstance(section,dict) for section in sections):
        sections = {section.get('title'):section.get('markdown',section.get('content')) for section in sections}
    if not isinstance(sections, dict) or not isinstance(value.get('ready'), bool):
        raise ValueError('本轮方案格式不完整，请重试。')
    sections = dict(sections)
    for heading in fields:
        parts = heading.split('、')
        if heading not in sections and len(parts)>1 and all(isinstance(sections.get(k),str) for k in parts):
            sections[heading] = '\n\n'.join(k+'：'+sections.pop(k) for k in parts)
    if any(not isinstance(sections.get(k), str) for k in fields):
        raise ValueError('方案章节缺失，请重试。')
    title = value.get('title')
    if not isinstance(title, str) or not title.strip():
        raise ValueError('方案缺少标题，请重试。')
    ready = value['ready'] and all(sections[k].strip() for k in fields)
    plan = '# ' + title.strip() + '\n\n' + '\n\n'.join(
        '## ' + k + '\n\n' + (sections[k].strip() or '待讨论') for k in fields)
    return dict(title=title.strip(), plan=plan, ready=ready, sections=sections)

def list_drafts(base=None):
    entries = []
    for path in sorted((base or BASE).glob('*/state.json'), key=lambda p:p.stat().st_mtime, reverse=True):
        state = json.loads(path.read_text('utf8'))
        if state.get('plan'):
            entries.append(dict(id=path.parent.name, title=state.get('title') or state['plan'].splitlines()[0][:64]))
    return entries

def run(handler, raw, research=False):
    from planning_turn import run as planning_run
    return planning_run(handler, raw, research=research)
