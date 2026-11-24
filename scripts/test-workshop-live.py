"""Exercise the local workshop with synthetic work notes."""
import io
import json
import time
import zipfile
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8765'


def request(path, body=None):
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    with urlopen(Request(BASE + path, data=payload, headers={'Content-Type':'application/json'}), timeout=25) as response:
        return json.load(response)


def run(action, **options):
    job = request('/api/workshop/job', {'action':action, **options})
    print(f'{action} {job["id"]}', flush=True)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        result = request('/api/tasks/' + job['id'])
        if result['status'] not in ('queued', 'running'):
            assert result['status'] == 'completed', result['result']
            return result['workshopResult']
        time.sleep(2)
    raise RuntimeError('任务超时')


draft = run('create', name='weekly-demo', goal='按工作记录整理周报', inputs='工作记录和风险清单', outputs='进展、风险、下一步三段，不编造日期', steps='按类别归纳')
assert draft['name'] == 'weekly-demo'
version = request('/api/workshop/save', {'content':draft['content'], 'label':'验收 v0.1'})
assert request('/api/workshop/version/' + version['id'])['content'] == draft['content']
with urlopen(BASE + '/api/workshop/zip/' + version['id'], timeout=25) as response:
    with zipfile.ZipFile(io.BytesIO(response.read())) as bundle:
        assert bundle.read('weekly-demo/SKILL.md').decode() == draft['content']
print('Verified create, local version, and ZIP', flush=True)
test = run('test', content=draft['content'], sample='完成模板检查。风险：缺少财务确认。下一步：联系财务。', expected='三段，并准确保留财务确认风险')
assert '财务' in test['output']
print('PASS create → save → ZIP → live test', flush=True)
