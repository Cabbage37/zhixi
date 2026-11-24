"""Exercise real application generation and execution on synthetic inputs."""
import json
from concurrent.futures import ThreadPoolExecutor
import sys
import threading
import time
import uuid
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import application_tools as apps
from openpyxl import Workbook


def main():
    reports = []
    result_path = server.DATA / 'application-acceptance/results.json'
    if result_path.is_file():
        reports = json.loads(result_path.read_text(encoding='utf-8'))
    with server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler) as http:
        threading.Thread(target=http.serve_forever, daemon=True).start()

        def call(route, body=None):
            connection = HTTPConnection('127.0.0.1', http.server_port, timeout=15)
            try:
                connection.request('GET' if body is None else 'POST', route,
                                   None if body is None else json.dumps(body).encode(),
                                   {'Host': '127.0.0.1:8765', 'Content-Type': 'application/json'})
                response = connection.getresponse()
                value = json.load(response)
                assert response.status in (200, 201), value
                return value
            finally:
                connection.close()

        def job(**body):
            task = call('/api/applications/job', body)
            for _ in range(600):
                state = call('/api/tasks/' + task['id'])
                if state['status'] not in ('queued', 'running'):
                    assert state['status'] == 'completed', state.get('result')
                    print(body['action'], task['id'], 'completed', flush=True)
                    return state['applicationResult'], task['id']
                time.sleep(1)
            raise AssertionError('Task timed out')

        def upload(path):
            folder = server.DATA / 'uploads' / uuid.uuid4().hex
            folder.mkdir()
            (folder / path.name).write_bytes(path.read_bytes())
            return folder.name

        scenarios = [
            ('tool', '一段文字', '我想做一个会议纪要整理器，输入会议记录，输出会议结论、待办事项、责任人和截止时间。', '一张表格'),
            ('tool', 'Word / PDF', '上传 Word/PDF，提取项目名称、金额、负责人、进度和下一步安排。', '一张表格'),
            ('dashboard', 'Excel', '上传 Excel，做项目进度看板，展示项目总数、正常/延期数量、负责人分布和项目清单。', '一个看板'),
            ('skill', '一段文字', '以后每周把输入的工作事项整理成周报，分为本周进展、重点事项、问题和下周计划。', '一段文字')
        ]
        sample = '项目甲金额100万元，负责人张三，进度正常，下一步验收。项目乙金额200万元，负责人李四，进度延期，下一步补齐材料。'
        assets = server.DATA / 'application-acceptance'
        assets.mkdir(exist_ok=True)
        apps.export_result(assets, {'text': sample, 'columns': [], 'rows': []})
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['项目名称', '金额', '负责人', '进度', '下一步安排'])
        sheet.append(['项目甲', 100, '张三', '正常', '验收'])
        sheet.append(['项目乙', 200, '李四', '延期', '补齐材料'])
        workbook.save(assets / '项目.xlsx')
        report_lock = threading.Lock()
        def exercise(pair):
            index, (kind, input_kind, goal, output) = pair
            if any(report['scenario'] == index+1 for report in reports):
                return
            app = None
            if '--resume' in sys.argv:
                for option_path in server.DATA.glob('tasks/*/application-options.json'):
                    options = apps.read(option_path)
                    generated = option_path.parent / 'application-result.json'
                    if options['action'] == 'create' and options['goal'] == goal and generated.is_file():
                        create_id = option_path.parent.name
                        app = apps.get(apps.read(generated)['id'])
                        break
            if app is None:
                suggestion, _ = job(action='recommend', kind=kind, input=input_kind, goal=goal)
                assert suggestion['recommendations']
                app, create_id = job(action='create', kind=kind, input=input_kind, goal=goal, output=output)
            files = [upload(assets / 'outputs/结果.docx')] if index == 1 else [upload(assets / '项目.xlsx')] if index == 2 else []
            value, run_id = job(action='run', id=app['id'], text='' if files else app['sample'], files=files)
            if index in (1, 2):
                assert len(value['rows']) == 2, value
            if index in (0, 2):
                change = '增加一个风险提示字段。' if index == 0 else '把延期项目放最上面。'
                app, _ = job(action='revise', id=app['id'], changes=change)
                value, run_id = job(action='run', id=app['id'], text='' if files else app['sample'], files=files)
                if index == 2:
                    assert app['ui_config']['sort_first'] == '延期'
                    assert value['rows'][0][app['ui_config']['sort_column']] == '延期'
            saved = call('/api/applications/update', {'action': 'save', 'id': app['id']})
            assert saved['status'] == 'saved'
            with report_lock:
                reports.append({'scenario': index+1, 'application': app['id'], 'type': app['type'],
                                'version': app['version'], 'createTask': create_id, 'runTask': run_id})
                apps.save(assets / 'results.json', reports)
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(exercise, enumerate(scenarios)))
        finally:
            http.shutdown()
    print(json.dumps(reports, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
