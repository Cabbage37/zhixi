"""Read-only adapter for the existing financial databases."""
import csv
import datetime
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.runtime/python'))
import duckdb

BASE = ROOT / 'data/research-assets'


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def connect(database):
    if not isinstance(database, str) or database not in [p.stem for p in BASE.glob('*.duckdb')]:
        raise ValueError('数据库不存在')
    return duckdb.connect(str(BASE / (database + '.duckdb')), read_only=True)


def safe(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def rows(cursor):
    columns = [c[0] for c in cursor.description]
    return [{column: safe(value) for column, value in zip(columns, row)} for row in cursor.fetchall()]


def catalog():
    result = []
    for path in sorted(BASE.glob('*.duckdb')):
        with connect(path.stem) as connection:
            tables = rows(connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"))
            result.append({'name': path.stem, 'tables': [r['table_name'] for r in tables]})
    return result


def metadata(database, table):
    with connect(database) as connection:
        valid = connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()
        if (table,) not in valid:
            raise ValueError('数据表不存在')
        columns = rows(connection.execute('DESCRIBE ' + quote(table)))
        count = connection.execute('SELECT count(*) FROM ' + quote(table)).fetchone()[0]
        return {'columns': columns, 'count': count}


def preview(body):
    database, table = body.get('database'), body.get('table')
    info = metadata(database, table)
    names = [c['column_name'] for c in info['columns']]
    where, parameters = [], []
    filters = body.get('filters', [])
    if not isinstance(filters, list) or len(filters)>10 or any(not isinstance(f,dict) for f in filters):
        raise ValueError('筛选条件无效')
    for condition in filters:
        column, value = condition.get('column'), condition.get('value')
        if column not in names or not isinstance(value, str) or len(value) > 300:
            raise ValueError('筛选字段或值无效')
        where.append(quote(column) + ' = ?')
        parameters.append(value)
    date_column = body.get('dateColumn')
    if date_column:
        if date_column not in names:
            raise ValueError('日期字段无效')
        for key, op in [('start', '>='), ('end', '<=')]:
            if body.get(key):
                try:
                    date = datetime.date.fromisoformat(body[key])
                except (ValueError, TypeError):
                    raise ValueError('日期格式无效') from None
                where.append('TRY_CAST(' + quote(date_column) + ' AS DATE) ' + op + ' ?')
                parameters.append(date)
    search = body.get('search', '')
    if not isinstance(search, str) or len(search) > 200:
        raise ValueError('搜索内容过长')
    if search:
        where.append('(' + ' OR '.join('contains(lower(CAST(' + quote(c) + ' AS VARCHAR)), lower(?))' for c in names) + ')')
        parameters.extend([search] * len(names))
    clause = ' WHERE ' + ' AND '.join(where) if where else ''
    order = ' ORDER BY ' + quote(date_column) if date_column else ''
    with connect(database) as connection:
        count = connection.execute('SELECT count(*) FROM ' + quote(table) + clause, parameters).fetchone()[0]
        values = rows(connection.execute('SELECT * FROM ' + quote(table) + clause + order + ' LIMIT 3001', parameters))
    return {'database': database, 'table': table, 'columns': names, 'rows': values[:3000],
            'count': count, 'truncated': len(values) > 3000}


def chart(body):
    data = preview(body)
    x, y = body.get('x'), body.get('y')
    if x not in data['columns'] or y not in data['columns'] or x == y:
        raise ValueError('请选择有效的横轴和数值列')
    for code_column in ('指标代码', '序列代码'):
        if code_column in data['columns'] and len({row[code_column] for row in data['rows']})>1:
            raise ValueError('当前包含多个指标，请按指标代码筛选一个序列后制图')
    values = []
    for row in data['rows']:
        value = row[y]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError('数值列包含非数值内容')
        values.append({'x': row[x], 'y': value})
    kind = body.get('kind', 'line')
    if kind not in ('line', 'bar'):
        raise ValueError('图表类型无效')
    return {**data, 'chart': {'x': x, 'y': y, 'kind': kind, 'values': values}}


def export(workspace, data):
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, Reference
    output = workspace / 'outputs'
    output.mkdir(exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = '数据'
    sheet.append(data['columns'])
    for row in data['rows']:
        sheet.append([row[c] for c in data['columns']])
    for line in sheet:
        for cell in line:
            if isinstance(cell.value, str):
                cell.data_type = 's'
    sheet.freeze_panes = 'A2'
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 22
    if data.get('chart') and data['rows']:
        config = data['chart']
        graph = LineChart() if config['kind'] == 'line' else BarChart()
        graph.title = data['table'] + ' · ' + config['y']
        graph.add_data(Reference(sheet, min_col=data['columns'].index(config['y'])+1, min_row=1, max_row=len(data['rows'])+1), titles_from_data=True)
        graph.set_categories(Reference(sheet, min_col=data['columns'].index(config['x'])+1, min_row=2, max_row=len(data['rows'])+1))
        sheet.add_chart(graph, 'A'+str(len(data['rows'])+4))
    book.save(output / '研究数据.xlsx')
    (output / '数据与图表.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    with (output/'研究数据.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.writer(file);writer.writerow(data['columns'])
        for row in data['rows']:
            writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in (row[c] for c in data['columns'])])
