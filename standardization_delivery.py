"""Verify native Skill evidence and the requested deliverable before publishing."""

def verify(job,workspace,result):
    from zipfile import ZipFile
    calls={event['data']['callId']:event['data'] for event in result.events if event.get('type')=='tool/call'}
    loaded=False
    for event in result.events:
        if event.get('type')!='tool/result':
            continue
        message=event['data']['message']
        call=calls.get(message.get('toolCallId'),{})
        if call.get('name')=='skill' and any('<skill_content name="office-docx">' in part.get('text','')
                                             for part in message.get('content',[]) if isinstance(part,dict)):
            loaded=True
            break
    if not loaded:
        raise ValueError('当前任务未加载 Word Skill，不能交付标准化文稿')
    fmt=job['standardization']['format']
    artifact=workspace/'outputs'/('规范文稿.'+fmt)
    manuscript=artifact if fmt=='docx' else workspace/'排版底稿.docx'
    if fmt=='pdf' and not manuscript.is_file():
        manuscript=workspace/'outputs/排版底稿.docx'
    if not manuscript.is_file():
        raise ValueError('未生成可打开的排版文稿')
    with ZipFile(manuscript) as package:
        if package.testzip() or 'word/document.xml' not in package.namelist():
            raise ValueError('生成的 Word 文档无法打开')
        from xml.etree import ElementTree as ET
        def body_text(doc):
            tree=ET.fromstring(doc.read('word/document.xml'))
            texts=tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')
            return ''.join(''.join(node.text or '' for node in texts).split())
        source_name=job['standardization'].get('source')
        original=([workspace/'inputs'/source_name] if source_name else list((workspace/'inputs').glob('*.docx')))
        if len(original)==1 and original[0].suffix.lower()=='.docx' and (source_name or job['standardization'].get('templateId')!='custom'):
            with ZipFile(original[0]) as source:
                if body_text(source)!=body_text(package):
                    raise ValueError('正文一致性校验未通过，请核对生成结果')
    if fmt=='pdf':
        from deepseek_harness.office import convert
        import json
        from deepseek_harness.errors import HarnessError
        try:
            conversion=convert(manuscript,artifact)
        except (HarnessError,OSError) as error:
            raise ValueError('Office PDF 转换失败：'+str(error)) from error
        with artifact.open('rb') as f:
            if f.read(5)!=b'%PDF-':
                raise ValueError('未生成有效 PDF')
        trace={'tool':'deepseek_harness.office.convert','backend':conversion.backend,
               'output':artifact.name,'missingFonts':conversion.missing_fonts}
        (workspace/'office-export.json').write_text(json.dumps(trace,ensure_ascii=False),encoding='utf8')
        print('PDF 已导出。' + ('本机缺少以下字体，版式可能采用替代字体：'+ '、'.join(conversion.missing_fonts) if conversion.missing_fonts else ''))
