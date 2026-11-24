import sys, tempfile, hashlib, zipfile, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook,load_workbook
from excel_tools import inspect_book,generate,validate_plan

with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp);source=folder/'sample.xlsx';out=folder/'out.xlsx'
    wb=Workbook();ws=wb.active;ws.title='数据'
    for row in [['年份','收入','利润'],[2024,100,20],[2025,120,25],[2026,140,None]]:ws.append(row)
    transpose=wb.create_sheet('横表')
    for row in [['指标',2024,2025],['收入',100,120],['利润',20,25]]:transpose.append(row)
    wb.create_sheet('空表');wb.save(source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    info=inspect_book(source);assert len(info['sheets'])==3 and info['sheets'][2]['empty']
    base={'sheet':'数据','range':'A1:C4','table':'时间序列','orientation':'columns','order':'原始顺序','series':'C,B','title':'测试','unit':'万元','source':'测试数据'}
    for kind in ['折线图','柱状图','条形图','堆积柱状图','散点图','柱线组合图','仅整理表格','饼图']:
        p={**base,'chart':kind}
        if kind=='饼图':p['series']='B'
        result=generate(source,[p],out)
        v=load_workbook(out);sheet=v.worksheets[1]
        assert len(sheet._charts)==(0 if kind=='仅整理表格' else 1)
        assert sheet['B4'].value==('收入' if kind=='饼图' else '利润')
        assert sheet['A4'].fill.fgColor.rgb.endswith('D6DCE5')
        assert sheet['A5'].fill.fgColor.rgb.endswith('FFFFFF')
        if kind=='折线图':
            ch=sheet._charts[0];assert ch.series[0].graphicalProperties.line.solidFill.srgbClr=='C4621A'
            assert ch.series[0].graphicalProperties.line.width==25400
            assert ch.y_axis.majorGridlines is None
            assert ch.series[0].marker.symbol=='diamond'
        v.close()
    generate(source,[{**base,'sheet':'横表','range':'A1:C3','orientation':'rows','series':'3,2','chart':'柱状图'}],out)
    v=load_workbook(out);assert v.worksheets[1]['B5'].value==20;v.close()
    for area in ['A1:XFD1048576','A1','A1:D4']:
        try:validate_plan(source,[{**base,'range':area}]);raise AssertionError('invalid range accepted')
        except ValueError:pass
    transpose['D3']='=B3+C3';wb.save(folder/'unselected-formula.xlsx')
    generate(folder/'unselected-formula.xlsx',[{**base,'chart':'折线图'}],out)
    v=load_workbook(out);assert v['横表']['D3'].value=='=B3+C3' and '空表' in v.sheetnames;v.close()
    ws['B2']='=1+1';wb.save(folder/'formula.xlsx')
    try:generate(folder/'formula.xlsx',[{**base,'chart':'柱状图'}],out);raise AssertionError('missing cached formula accepted')
    except ValueError as e:assert '计算值' in str(e)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
    print('PASS: 8 chart/table types, Sheet orientation, series order, native chart styles, formula-cache guard, bounds, original unchanged')
