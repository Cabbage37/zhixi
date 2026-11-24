"""Application definitions and versioned execution through the shared Agent."""
import io
import json
import re
import threading
import uuid
import zipfile
from datetime import datetime

from reader_tools import ROOT, read, save
import skill_workshop

BASE = ROOT / 'data/applications'
LOCK = threading.RLock()
TYPES = ('tool', 'dashboard', 'skill', 'workflow')


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def get(ident):
    if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
        raise ValueError('工具编号无效')
    path = BASE / (ident + '.json')
    if not path.is_file():
        raise ValueError('工具不存在')
    return read(path)


def listing():
    records = [read(p) for p in BASE.glob('*.json')]
    return sorted([item for item in records if item['status'] != 'deleted'],
                  key=lambda item: item['updated_at'], reverse=True)


def decode(value):
    value = value.strip()
    fence = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', value)
    if fence:
        value = fence[1].strip()
    return json.loads(value)


def definition(value):
    required = ('name', 'description', 'instructions', 'sample')
    for key in required:
        if not isinstance(value.get(key), str) or not 1 <= len(value[key].strip()) <= 16000:
            raise ValueError('生成的工具说明不完整')
    if value.get('type') not in TYPES:
        raise ValueError('生成的工具类型无效')
    for key in ('input_schema', 'output_schema', 'ui_config'):
        if not isinstance(value.get(key), dict):
            raise ValueError('生成的工具结构无效')
    formats = value['input_schema'].get('formats')
    allowed = ['text', '.docx', '.pdf', '.txt', '.md', '.xlsx', '.png', '.jpg', '.jpeg', '.webp']
    if not isinstance(formats, list) or not formats or any(f not in allowed for f in formats):
        raise ValueError('工具输入格式无效')
    columns = value['output_schema'].get('columns', [])
    if not isinstance(columns, list) or len(columns) > 30 or any(not isinstance(c, str) or not 1 <= len(c) <= 60 for c in columns):
        raise ValueError('结果表格字段无效')
    if len(set(columns)) != len(columns):
        raise ValueError('结果列名不能重复')
    if value['output_schema'].get('format') not in ('text', 'table', 'dashboard'):
        raise ValueError('结果格式无效')
    if value['output_schema']['format'] != 'text' and not columns:
        raise ValueError('表格或看板需要输出字段')
    for key, item in value['ui_config'].items():
        if key not in ('button_label', 'group_by', 'status_column', 'sort_column', 'sort_first', 'due_date_column') or not isinstance(item, str) or len(item)>100:
            raise ValueError('界面配置无效')
    for key in ('group_by', 'status_column', 'sort_column', 'due_date_column'):
        column = value['ui_config'].get(key, '')
        if column and column not in columns:
            raise ValueError('看板字段与结果表格不匹配')
    return {key: value[key] for key in (*required, 'type', 'input_schema', 'output_schema', 'ui_config')}


def store(value, parent=None, expected=None):
    value = definition(value)
    with LOCK:
        previous = get(parent) if parent else None
        if previous and (previous['status'] == 'deleted' or previous['version'] != expected):
            raise ValueError('工具已更新，请重新打开后调整')
        ident = previous['id'] if previous else uuid.uuid4().hex
        version = previous['version'] + 1 if previous else 1
        content = '---\nname: app-' + ident + '\ndescription: ' + json.dumps(value['description'], ensure_ascii=False) + '\n---\n\n' + value['instructions']
        skill = skill_workshop.save_version(content, '应用版本 ' + str(version), previous['skill_id'] if previous else None)
        timestamp = now()
        record = {**value, 'id': ident, 'skill_id': skill['id'], 'tools': ['file-reader', 'excel-reader', 'structured-output'],
                  'mcp': [], 'created_at': previous['created_at'] if previous else timestamp,
                  'updated_at': timestamp, 'version': version, 'status': previous['status'] if previous else 'draft'}
        archive = BASE / 'versions' / ident
        archive.mkdir(parents=True, exist_ok=True)
        save(archive / (str(version) + '.json'), record)
        save(BASE / (ident + '.json'), record)
        return record


def update(body):
    with LOCK:
        app = get(body.get('id'))
        action = body.get('action')
        if action in ('save', 'delete'):
            app['status'] = 'saved' if action == 'save' else 'deleted'
            app['updated_at'] = now()
            save(BASE / (app['id'] + '.json'), app)
            return app
        if action == 'copy':
            return store({**app, 'name': app['name'] + ' 副本'})
        if action == 'restore':
            number = body.get('version')
            if type(number) is not int or not 1 <= number <= app['version']:
                raise ValueError('版本无效')
            old = read(BASE / 'versions' / app['id'] / (str(number) + '.json'))
            return store(old, app['id'], app['version'])
        raise ValueError('未知操作')


def package(ident):
    app = get(ident)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('application.json', json.dumps(app, ensure_ascii=False, indent=2))
        archive.writestr('SKILL.md', skill_workshop.get(app['skill_id'])['content'])
        archive.writestr('README.txt', '在知析 AI 工坊的“我的工具”导入 application.json 可创建自己的副本。')
    return output.getvalue()


def prepare(body):
    action = body.get('action')
    if action not in ('recommend', 'create', 'revise', 'run'):
        raise ValueError('无效操作')
    options = {'action': action}
    for key in ('kind', 'input', 'goal', 'output', 'requirements', 'changes', 'text'):
        value = body.get(key, '')
        if not isinstance(value, str) or len(value) > 24000:
            raise ValueError('输入过长或格式无效')
        options[key] = value.strip()
    if action in ('recommend', 'create') and not options['goal']:
        raise ValueError('请描述你的想法')
    if action in ('revise', 'run'):
        options['application'] = get(body.get('id'))
        if options['application']['status'] == 'deleted':
            raise ValueError('工具已删除')
    if action == 'revise' and not options['changes']:
        raise ValueError('请填写想调整的内容')
    files = body.get('files', [])
    if not isinstance(files, list) or len(files) > 4:
        raise ValueError('最多上传四份文件')
    if len(set(files)) != len(files):
        raise ValueError('请勿重复提交同一文件')
    paths = []
    for fid in files:
        if not isinstance(fid, str) or not re.fullmatch('[a-f0-9]{32}', fid):
            raise ValueError('文件编号无效')
        found = list((ROOT / 'data/uploads' / fid).glob('*'))
        if len(found) != 1 or not found[0].is_file():
            raise ValueError('上传文件不存在')
        if found[0].suffix.lower() not in ('.docx', '.pdf', '.txt', '.md', '.xlsx', '.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('暂不支持此文件格式')
        if action == 'run' and found[0].suffix.lower() not in options['application']['input_schema']['formats']:
            raise ValueError('此工具尚未配置处理这种文件，可告诉 AI 增加相应输入格式')
        paths.append(found[0])
    if action == 'run' and not options['text'] and not paths:
        raise ValueError('请填写内容或上传材料')
    return options, paths


def material(workspace, options):
    from material_tools import extract
    from excel_tools import open_book, display
    texts = [options['text']] if options['text'] else []
    for path in sorted((workspace / 'inputs').glob('*/*')):
        if path.suffix.lower() == '.xlsx':
            book = open_book(path, data_only=True)
            try:
                sheets = []
                for sheet in book:
                    if sheet.max_row > 301 or sheet.max_column > 30:
                        raise ValueError('首版看板支持每页最多300行数据、30列，请缩小文件')
                    sheets.append({'name': sheet.title, 'rows': [[display(v) for v in row] for row in sheet.iter_rows(values_only=True)]})
                texts.append(path.name + '\n' + json.dumps(sheets, ensure_ascii=False))
            finally:
                book.close()
        elif path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            from reader_tools import import_source
            source = import_source({'fileId': path.parent.name})
            texts.append(path.name + '\n' + '\n'.join(b['text'] for b in source['blocks']))
        else:
            source = extract(path)
            if not source['blocks']:
                raise ValueError('文件没有可提取文字，请使用文字型材料')
            texts.append(path.name + '\n' + '\n'.join(b['text'] for b in source['blocks']))
    value = '\n\n'.join(texts)
    if len(value) > 40000:
        raise ValueError('材料超过40,000字，请拆分后运行')
    return value


def result(value, app):
    if not isinstance(value, dict) or not isinstance(value.get('text'), str):
        raise ValueError('工具未生成有效文字结果')
    rows = value.get('rows', [])
    columns = app['output_schema'].get('columns', [])
    if not isinstance(rows, list) or len(rows) > 300:
        raise ValueError('结果表格超出范围')
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(columns) or any(not isinstance(v, (str, int, float, bool, type(None))) for v in row.values()):
            raise ValueError('结果表格字段不匹配')
    if app['output_schema']['format'] != 'text' and not rows:
        raise ValueError('工具未生成表格数据')
    config = app['ui_config']
    if config.get('sort_column') and config.get('sort_first'):
        rows.sort(key=lambda row: str(row[config['sort_column']]) != str(config['sort_first']))
    output={'text': value['text'], 'rows': rows, 'columns': columns, 'ui_config': config}
    due=config.get('due_date_column')
    if not due and app['output_schema']['format']=='dashboard' and '本月到期' in app.get('description',''):
        due=next((c for c in columns if c in ('到期日期','到期日','截止日期')),None)
        if not due:raise ValueError('请为本月到期指标增加到期日期列，再运行看板。')
    if due:
        if due not in columns:raise ValueError('缺少到期日期列，请在工具中补充后重试。')
        today=datetime.now().astimezone().date()
        count=unknown=0
        for row in rows:
            try: day=datetime.fromisoformat(str(row[due])).date()
            except ValueError:
                unknown+=1
                continue
            count+=int((day.year,day.month)==(today.year,today.month))
        output['metrics']=[f'{today.year}年{today.month}月到期 {count} 项'+(f'（另有 {unknown} 项日期待确认）' if unknown else '')]
        output['text']='；'.join(output['metrics'])
    return output


def export_result(workspace, value):
    from openpyxl import Workbook
    from lxml import etree as ET
    output = workspace / 'outputs'
    output.mkdir(exist_ok=True)
    (output / '结果.txt').write_text(value['text'], encoding='utf-8')
    if value['columns']:
        book = Workbook()
        sheet = book.active
        sheet.append(value['columns'])
        for row in value['rows']:
            sheet.append([row[c] for c in value['columns']])
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str): cell.data_type = 's'
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns: sheet.column_dimensions[column[0].column_letter].width = 22
        book.save(output / '结果.xlsx')
    namespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    root = ET.Element('{'+namespace+'}document', nsmap={'w':namespace})
    body = ET.SubElement(root, '{'+namespace+'}body')
    lines = [value['text']]
    if value['columns']:
        lines += [' | '.join(value['columns'])]
        lines += [' | '.join('' if row[c] is None else str(row[c]) for c in value['columns']) for row in value['rows']]
    for line in '\n'.join(lines).splitlines():
        paragraph = ET.SubElement(body, '{'+namespace+'}p')
        run = ET.SubElement(paragraph, '{'+namespace+'}r')
        ET.SubElement(run, '{'+namespace+'}t').text = line
    with zipfile.ZipFile(output/'结果.docx', 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', ET.tostring(root, encoding='utf-8', xml_declaration=True))
