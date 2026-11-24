"""Local workbook inspection and chart tool, invoked by the unified Agent."""
import json, re, zipfile, datetime, math
from pathlib import Path
from openpyxl import load_workbook, Workbook
from openpyxl.chart import BarChart, LineChart, ScatterChart, PieChart, Reference, Series
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.marker import DataPoint
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.comments import Comment
from openpyxl.chart.text import RichText
from openpyxl.drawing.text import Paragraph, ParagraphProperties, CharacterProperties, Font as DrawingFont
from openpyxl.utils.cell import range_boundaries, get_column_letter

ROOT = Path(__file__).resolve().parent
STYLE = json.loads((ROOT/'skills/excel-chart/references/style.json').read_text(encoding='utf-8'))
KINDS = ['自动推荐','折线图','柱状图','条形图','堆积柱状图','散点图','饼图','柱线组合图','仅整理表格']
TABLES = ['时间序列','分类对比','占比结构','指标关系','明细表']

def chart_font():
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties(
        latin=DrawingFont(typeface=STYLE['latinFont']),ea=DrawingFont(typeface=STYLE['chineseFont']),
        sz=1100,solidFill='000000')))])

def open_book(path, data_only=False):
    path = Path(path)
    if path.suffix.lower() != '.xlsx': raise ValueError('请上传 XLSX 工作簿')
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > 80*1024*1024:
            raise ValueError('工作簿解压后过大，请拆分后上传')
    book = load_workbook(path, read_only=False, data_only=data_only, keep_links=not data_only)
    if len(book.worksheets) > 40 or any(s.max_row*s.max_column > 200000 for s in book):
        book.close(); raise ValueError('首版支持最多40个Sheet，每个Sheet不超过20万个单元格，请拆分文件')
    return book

def display(v):
    if isinstance(v, (datetime.date, datetime.datetime)): return v.isoformat()
    if isinstance(v, float) and not math.isfinite(v): return None
    return v if isinstance(v,(str,int,float,bool)) or v is None else str(v)

def inspect_book(path):
    book = open_book(path)
    sheets=[]
    try:
        for ws in book:
            populated=[(c.row,c.column) for row in ws for c in row if c.value is not None]
            if not populated:
                sheets.append({'name':ws.title,'empty':True,'preview':[]}); continue
            r0,c0=min(r for r,c in populated), min(c for r,c in populated)
            r1,c1=max(r for r,c in populated), max(c for r,c in populated)
            warnings=[]
            if ws.merged_cells.ranges: warnings.append('存在合并单元格，请确认表头与数据范围')
            if any(c.data_type=='f' for row in ws for c in row): warnings.append('包含公式：制图读取已保存的计算值；请先在 Excel 中计算并保存')
            if ws.sheet_state!='visible': warnings.append('隐藏工作表，默认不选中')
            sheets.append({'name':ws.title,'empty':False,'hidden':ws.sheet_state!='visible',
                'range':f'{get_column_letter(c0)}{r0}:{get_column_letter(c1)}{r1}',
                'rows':r1-r0+1,'columns':c1-c0+1,'warnings':warnings,
                'preview':[{'row':r,'cells':[{'address':f'{get_column_letter(c)}{r}','value':display(ws.cell(r,c).value)} for c in range(c0,min(c1,c0+7)+1)]} for r in range(r0,min(r1,r0+5)+1)]})
        return {'sheets':sheets,'style':STYLE}
    finally: book.close()

def validate_plan(path, plan):
    if not isinstance(plan,list) or not plan or len(plan)>40: raise ValueError('请至少选择一个 Sheet')
    book=open_book(path)
    result=[]; seen=set()
    try:
        for item in plan:
            if not isinstance(item,dict): raise ValueError('无效制图配置')
            name=item.get('sheet'); area=str(item.get('range','')).upper().strip()
            if name not in book.sheetnames or name in seen: raise ValueError('Sheet 不存在或重复')
            seen.add(name)
            if not re.fullmatch(r'[A-Z]{1,3}[1-9]\d*:[A-Z]{1,3}[1-9]\d*',area): raise ValueError('数据范围请填写 A1:E20 形式')
            c0,r0,c1,r1=range_boundaries(area); ws=book[name]
            if not (1<=c0<c1<=ws.max_column and 1<=r0<r1<=ws.max_row): raise ValueError('数据范围需要包含表头、分类和数值，且不得超出工作表')
            if (c1-c0+1)*(r1-r0+1)>100000: raise ValueError('单次制图范围不得超过10万个单元格')
            if any(not (m.max_row<r0 or m.min_row>r1 or m.max_col<c0 or m.min_col>c1) for m in ws.merged_cells.ranges): raise ValueError('选区含合并单元格，请选择未合并的单行表头和数据区域')
            kind=item.get('chart','自动推荐'); table=item.get('table','分类对比')
            orientation=item.get('orientation','columns')
            order=item.get('order','原始顺序')
            if kind not in KINDS or table not in TABLES or orientation not in ['columns','rows'] or order not in ['原始顺序','分类升序','分类降序']: raise ValueError('无效图表参数')
            clean={k:str(item.get(k,''))[:300] for k in ['title','unit','source','series']}
            clean.update(sheet=name,range=area,chart=kind,table=table,orientation=orientation,order=order)
            result.append(clean)
        return result
    finally: book.close()

def chart_type(plan):
    return plan['chart'] if plan['chart']!='自动推荐' else {'时间序列':'折线图','分类对比':'柱状图','占比结构':'饼图','指标关系':'散点图','明细表':'仅整理表格'}[plan['table']]

def safe_text(cell, value):
    cell.value=value
    if isinstance(value,str): cell.data_type='s'

def generate(path, plan, output):
    """Produce explicit data snapshots and editable Excel-native charts. Never save input."""
    plan=validate_plan(path,plan); book=open_book(path,True); formulas=open_book(path)
    out=formulas; original_names=list(out.sheetnames); guide=out.create_sheet('制图说明',0); out.active=guide; report=[]
    safe_text(guide['A1'],'金控 Excel 智能制图')
    safe_text(guide['A2'],'原始工作表保留在图表页之后。制图数据使用源文件已保存的计算值。')
    safe_text(guide['A3'],'修改输出数据表可更新原生图表。未转换单位；缺失值保留为空，不补零。')
    safe_text(guide['A4'],'样式依据：'+STYLE['source']+'；不采用PPT页面、母版或字号要求。')
    try:
        for index,p in enumerate(plan,1):
            src=book[p['sheet']]; form=formulas[p['sheet']]
            c0,r0,c1,r1=range_boundaries(p['range'])
            matrix=[[src.cell(r,c) for c in range(c0,c1+1)] for r in range(r0,r1+1)]
            if p['orientation']=='rows': matrix=list(map(list,zip(*matrix)))
            requested=[s.strip().upper() for s in re.split('[,，]',p['series']) if s.strip()]
            indices=[]
            for j in range(1,len(matrix[0])):
                key=get_column_letter(matrix[0][j].column) if p['orientation']=='columns' else str(matrix[0][j].row)
                if not requested or key in requested: indices.append(j)
            keys=[get_column_letter(matrix[0][j].column) if p['orientation']=='columns' else str(matrix[0][j].row) for j in indices]
            if not indices or (requested and set(requested)!=set(keys)): raise ValueError(p['sheet']+'：数据系列不在选区内，或包含了分类列/行')
            if requested:
                if len(requested)!=len(set(requested)): raise ValueError('数据系列不能重复')
                mapping=dict(zip(keys,indices));indices=[mapping[k] for k in requested]
            kind=chart_type(p)
            if kind!='仅整理表格' and len(indices)>6: raise ValueError(p['sheet']+'：请选择不超过6个数据系列')
            rows=[row for row in matrix[1:] if any(c.value is not None for c in row)]
            if not rows: raise ValueError(p['sheet']+'：选区没有数据')
            for row in rows:
                for j in [0]+indices:
                    cell=row[j]
                    if form[cell.coordinate].data_type=='f' and cell.value is None: raise ValueError(p['sheet']+'!'+cell.coordinate+' 公式尚无计算值，请在 Excel 中计算并保存后重传')
                    if cell.data_type=='e': raise ValueError(p['sheet']+'!'+cell.coordinate+' 含公式错误')
                if row[0].value is None: raise ValueError(p['sheet']+'：分类标签存在空值，请调整范围')
                if kind!='仅整理表格':
                    for j in indices:
                        v=row[j].value
                        if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)):
                            raise ValueError(p['sheet']+'!'+row[j].coordinate+' 不是数值，请确认数据范围和系列')
            if kind!='仅整理表格' and any(not any(isinstance(row[j].value,(int,float)) for row in rows) for j in indices): raise ValueError('所选系列没有有效数值')
            if p['order']!='原始顺序':
                try: rows.sort(key=lambda row:row[0].value,reverse=p['order']=='分类降序')
                except TypeError: raise ValueError('分类值类型不一致，无法排序')
            if kind=='饼图' and (len(indices)!=1 or any(row[indices[0]].value is not None and row[indices[0]].value<0 for row in rows) or sum(row[indices[0]].value or 0 for row in rows)<=0): raise ValueError('饼图需要单个非负数值系列，且合计大于零')
            if kind=='饼图' and len(rows)>6: raise ValueError('饼图类别超过6个，请改用条形图或缩小范围')
            if kind=='散点图' and any(not isinstance(row[0].value,(int,float)) or isinstance(row[0].value,bool) for row in rows): raise ValueError('散点图的第一列/行必须是数值型 X 轴')
            if kind=='柱线组合图' and len(indices)<2: raise ValueError('柱线组合图至少需要两个系列，最后一个系列绘为折线')
            title=p['title'] or p['sheet']; target=out.create_sheet(f'{index:02d}_{p["sheet"]}'[:31],index)
            safe_text(target['A1'],title);safe_text(target.cell(2,len(indices)+1),'单位：'+(p['unit'] or '沿用原始口径'))
            selected=[0]+indices
            for rownum,row in enumerate([matrix[0]]+rows,4):
                for colnum,j in enumerate(selected,1):
                    origin=row[j];cell=target.cell(rownum,colnum);safe_text(cell,origin.value)
                    cell.number_format=origin.number_format
                    cell.comment=Comment(f'来源：{p["sheet"]}!{origin.coordinate}','知析')
                    cell.font=Font(name=STYLE['chineseFont'] if isinstance(cell.value,str) and re.search('[\u4e00-\u9fff]',cell.value) else STYLE['latinFont'],size=11,color='000000',bold=rownum==4)
                    cell.fill=PatternFill('solid',fgColor=STYLE['tableHeader'] if rownum==4 else 'FFFFFF')
                    cell.border=Border(bottom=Side(style='thin',color='D6DCE5'))
                    cell.alignment=Alignment(horizontal='left' if colnum==1 else 'right',vertical='center',wrap_text=True)
                    target.column_dimensions[get_column_letter(colnum)].width=24 if colnum==1 else 18
            target.freeze_panes='B5';target.sheet_view.showGridLines=False
            end=len(rows)+4; target.auto_filter.ref=f'A4:{get_column_letter(len(selected))}{end}'
            safe_text(target.cell(end+2,1),'资料来源：'+(p['source'] or Path(path).name)+'；'+p['sheet']+'!'+p['range'])
            if kind!='仅整理表格':
                chart=LineChart() if kind=='折线图' else ScatterChart() if kind=='散点图' else PieChart() if kind=='饼图' else BarChart()
                if isinstance(chart,BarChart):
                    chart.type='bar' if kind=='条形图' else 'col'
                    chart.grouping='stacked' if kind=='堆积柱状图' else 'clustered'
                    if kind=='堆积柱状图': chart.overlap=100
                for col in range(2,len(selected)+1):
                    ref=Reference(target,min_col=col,min_row=4,max_row=end)
                    if kind=='散点图':chart.series.append(Series(ref,Reference(target,min_col=1,min_row=5,max_row=end),title_from_data=True))
                    else:chart.add_data(ref,titles_from_data=True)
                if kind!='散点图':chart.set_categories(Reference(target,min_col=1,min_row=5,max_row=end))
                if kind=='柱线组合图':
                    line=LineChart();line.series.append(chart.series.pop());line.y_axis.axId=chart.y_axis.axId
                    chart+=line
                charts=chart._charts
                offset=0
                for part in charts:
                    for j,series in enumerate(part.series):
                        color=STYLE['series'][(offset+j)%6]
                        if kind=='柱线组合图' and isinstance(part,LineChart): color=STYLE['palette'][3]
                        series.graphicalProperties=GraphicalProperties(solidFill=color,ln=GraphicalProperties(solidFill=color).ln)
                        series.graphicalProperties.line.solidFill=color
                        series.graphicalProperties.line.width=25400
                        if isinstance(part,(LineChart,ScatterChart)):
                            series.marker.symbol='diamond';series.marker.size=8
                            series.marker.graphicalProperties.solidFill=color;series.marker.graphicalProperties.line.solidFill=color
                    offset+=len(part.series)
                    if not isinstance(part,PieChart):
                        for axis in [part.x_axis,part.y_axis]:
                            axis.delete=False;axis.majorGridlines=None
                            axis.txPr=chart_font()
                            axis.spPr=GraphicalProperties();axis.spPr.line.solidFill='000000'
                        part.y_axis.title=p['unit'] or None
                if kind=='饼图':
                    chart.series[0].data_points=[DataPoint(idx=j,spPr=GraphicalProperties(solidFill=STYLE['series'][j])) for j in range(len(rows))]
                chart.title=title;chart.width=23;chart.height=12;chart.legend.position='b';chart.display_blanks='gap'
                chart.txPr=chart_font();chart.legend.txPr=chart_font();chart.title.txPr=chart_font()
                target.add_chart(chart,f'{get_column_letter(len(selected)+3)}4')
            report.append({'sheet':p['sheet'],'outputSheet':target.title,'chart':kind,'rows':len(rows),'series':len(indices)})
            safe_text(guide.cell(index+6,1),f'{p["sheet"]} → {target.title} / {kind} / {len(rows)}行 / {p["range"]}')
        guide.column_dimensions['A'].width=110
        for row in guide:
            for cell in row:cell.font=Font(name=STYLE['chineseFont'],size=11,color='000000');cell.alignment=Alignment(wrap_text=True)
        output=Path(output)
        if output.resolve()==Path(path).resolve(): raise ValueError('不得覆盖原工作簿')
        output.parent.mkdir(parents=True,exist_ok=True);out.save(output)
        verify=load_workbook(output, data_only=False)
        try:
            if verify.sheetnames[len(plan)+1:] != original_names:
                raise ValueError('导出后原工作表未完整保留')
            for entry in report:
                charts=verify[entry['outputSheet']]._charts
                if len(charts) != int(entry['chart'] != '仅整理表格'):
                    raise ValueError('导出后原生图表数量不符')
        finally:
            verify.close()
        return report
    finally:book.close();out.close()

if __name__=='__main__':
    import argparse,sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('plan');parser.add_argument('output')
    args=parser.parse_args()
    print(json.dumps(generate(args.source,json.loads(Path(args.plan).read_text(encoding='utf-8')),args.output),ensure_ascii=False))
