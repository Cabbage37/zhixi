"""Research-planning workspace, upstream skill selection and document delivery."""
from pathlib import Path
import io
import json
import zipfile

def handoff(state):
    """Portable confirmed input for a chapter-oriented deep-research executor."""
    from planning_engine import validate_research_plan
    if not state.get('confirmed') or state.get('confirmedVersion') != state.get('version'):
        raise ValueError('请先确认最新方案版本，再导出执行交接包')
    plan = validate_research_plan(state.get('research_plan'))
    output = io.BytesIO()
    manifest = {'schema':'zhixi.research-handoff.v1','version':state['version'],
                'planHash':state['confirmedHash'],'threadId':state['workshopThread'],
                'status':'confirmed','chapters':[str(c['id']) for c in plan['chapters']]}
    instructions = '# 深度研究执行交接\n\n先阅读方案.md，再按 research_plan.json 的章节任务、数据口径、图表和验收条件执行。\n\n每章先获取原始资料并记录链接、页码、期间、单位及获取日期；搜索摘要不能充当已核实数据。无法获得的指标明确留空并采用方案中的替代路径。禁止将规划假设写成研究结论。按 dependencies 排序，缺少关键决策时停止并询问用户。\n\n输出各章正文、证据索引、图表源数据及验收记录，最后做跨章节口径与论证一致性检查。来源和审查记录见 evidence.json 与 review.json。该交接包不代表研究已执行。\n'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('README.md',instructions)
        archive.writestr('方案.md',state['plan'])
        for name,value in [('manifest',manifest),('research_plan',plan),('evidence',state.get('evidence',[])),('review',state.get('review',{})),('decisions',state.get('decisions',[]))]:
            archive.writestr(name+'.json',json.dumps(value,ensure_ascii=False,indent=2))
    return output.getvalue()

ROOT = Path(__file__).resolve().parent
BASE = ROOT/'data/research-plans'
FIELDS = ('研究目标','核心问题','关键假设','研究范围','研究方法','数据与资料需求','拟使用来源','图表计划','正式研报提纲','交付形式')

def methods(topic):
    refs = ROOT/'skills/research-planning/references'
    paths = [refs/'consulting-analysis.md']
    if any(k in topic for k in ('公司','个股','上市','股票','估值','证券','银行','保险')):
        paths.append(refs/'company-tearsheet.md')
    if any(k in topic.lower() for k in ('估值','价值','dcf','折现','定价')):
        paths.append(refs/'damodaran-valuation.md')
    suites = ROOT/'.runtime/finance-upstream/FinClaw/skillsChoice'
    for terms, suite, skill in [(('银行','净息差'),'bank','bank-financial-analyzer'),(('保险','寿险','财险'),'insurance','insurance-company-analyzer'),(('证券公司','券商','投行'),'securities','securities-financial-analyzer')]:
        if any(term in topic for term in terms):
            paths.append(suites/(suite+'-suite')/skill/'SKILL.md')
    return [(p.parent.name if p.name=='SKILL.md' else p.stem,p.read_text('utf8')) for p in paths]

def export(state, kind):
    if kind=='docx':
        from scripts.reader_fixture import docx
        return docx([state['title'],*(line for k,v in state['sections'].items() for line in [k,*v.splitlines()])])
    if kind=='pdf':
        import pymupdf
        from markdown_it import MarkdownIt
        story=pymupdf.Story(html=MarkdownIt('commonmark',{'html':False}).render(state['plan']),user_css='body{font-family:sans-serif;line-height:1.5}')
        out=io.BytesIO()
        writer=pymupdf.DocumentWriter(out)
        page=pymupdf.paper_rect('a4')
        more=True
        while more:
            device=writer.begin_page(page)
            more,_=story.place(page+(48,48,-48,-48))
            story.draw(device)
            writer.end_page()
        writer.close()
        return out.getvalue()
    raise ValueError('未知格式')
