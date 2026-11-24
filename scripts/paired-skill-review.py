"""Paired replay of two public-source tasks on the configured writing model."""
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'.runtime/python')]
import evidence_writing as writing
from financial_quantities import unsupported_quantities

out = ROOT/'测试回放/Skill盲评'
out.mkdir(exist_ok=True)
def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))
def save(name, value):
    (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=',1)
        os.environ[key.strip()] = value.strip()
fed = read('data/tasks/054a823a01974d26b85e2c09e1f42d39/research-evidence.json')[0]['text'][:1500]
blocks = read('data/tasks/0f50cdb8cbeb4464af3a3e628e92114d/repurpose/source.json')['blocks']
bank = next(b['text'] for b in blocks if '5000亿元' in b['text'])
i = bank.index('5000亿元')
sources = [fed, bank[max(0,i-155):i+330]]
questions = ['此次日程调整能否说明十月降息？说明调整内容及其局限。','给领导写一段速览：5000亿元如何影响分档？能否据此认定所有小银行资本要求下调？']
skills = ['financial-quick-research','content-repurpose']
order = []
for k in range(2):
    pair = ['旧','新']
    random.SystemRandom().shuffle(pair)
    order.extend((k,arm) for arm in pair)
save('分组密钥.json',order)
original = writing.instructions
# Set each arm sequentially to isolate the prompt change.
for arm in ['旧','新']:
    writing.instructions = original if arm=='新' else lambda name:(ROOT/'skills'/name/'SKILL.md').read_text(encoding='utf8')
    writing.shared_rules = (__import__('skill_runtime').shared_rules if arm=='新' else lambda name:'保持来源事实、数字和不确定性，不增加承诺。')
    def run(entry):
        idx,(k,group) = entry
        if group != arm:return
        data={'资料':sources[k]}
        try:
            result=writing.ask(out,skills[k],questions[k]+'仅返回 {"判断":"中文快评或速览，最多130字","引文":["连续原文片段"]}。',data)
            save(str(idx)+'.json',result)
        except Exception as exc:
            save(str(idx)+'.json',{'error':str(exc)})
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run,enumerate(order)))
save('题目与原文.json',list(zip(questions,sources)))
