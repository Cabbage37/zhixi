"""Apply the company template's page settings and documented paragraph styles."""
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt


source, reference, destination = sys.argv[1:]
document = Document(source)
template = Document(reference)
for section in document.sections:
    for field in ('orientation', 'page_width', 'page_height', 'top_margin',
                  'bottom_margin', 'left_margin', 'right_margin', 'header_distance',
                  'footer_distance'):
        setattr(section, field, getattr(template.sections[0], field))

first = True
for paragraph in document.paragraphs:
    line = paragraph.text.strip()
    if not line:
        continue
    font = '仿宋'
    size = 16
    if first:
        font, size = '方正小标宋简体', 22
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif re.match(r'^[一二三四五六七八九十]+、', line):
        font = '黑体'
    elif re.match(r'^[（(][一二三四五六七八九十]+[）)]|^【内容摘要】', line):
        font = '楷体'
    first = False
    paragraph.paragraph_format.line_spacing = Pt(30)
    for run in paragraph.runs:
        run.font.name = 'Times New Roman'
        run.font.size = Pt(size)
        run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), font)
        if font in ('黑体', '楷体'):
            run.bold = False
document.save(destination)
