import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import application_tools as apps
import skill_workshop
from material_tools import extract
from openpyxl import load_workbook


class ApplicationsTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app_base = patch.object(apps, 'BASE', self.root / 'applications')
        self.skill_base = patch.object(skill_workshop, 'BASE', self.root / 'skills')
        self.app_base.start()
        self.skill_base.start()
        self.definition = dict(
            name='项目看板', description='查看项目状态', instructions='按输入整理项目，不补造信息',
            sample='甲项目正常，乙项目延期', type='dashboard',
            input_schema={'formats': ['text', '.xlsx']},
            output_schema={'format': 'dashboard', 'columns': ['名称', '进度', '负责人']},
            ui_config={'button_label': '生成看板', 'status_column': '进度', 'group_by': '负责人',
                       'sort_column': '进度', 'sort_first': '延期'}
        )

    def tearDown(self):
        self.app_base.stop()
        self.skill_base.stop()
        self.temp.cleanup()

    def test_versions_reject_stale_writes_and_restore_without_erasing_history(self):
        original = apps.store(self.definition)
        apps.update({'id': original['id'], 'action': 'save'})
        revised = apps.store({**self.definition, 'name': '新版'}, original['id'], 1)
        self.assertEqual(revised['status'], 'saved')
        with self.assertRaises(ValueError):
            apps.store(self.definition, original['id'], 1)
        restored = apps.update({'id': original['id'], 'action': 'restore', 'version': 1})
        self.assertEqual((restored['version'], restored['name']), (3, '项目看板'))
        self.assertEqual(len(list((apps.BASE / 'versions' / original['id']).glob('*.json'))), 3)

    def test_import_rejects_unconfigured_code_and_invalid_columns(self):
        with self.assertRaises(ValueError):
            apps.definition({**self.definition, 'ui_config': {'javascript': 'alert(1)'}})
        with self.assertRaises(ValueError):
            apps.definition({**self.definition, 'ui_config': {'group_by': '不存在'}})

    def test_results_sort_and_export_preserve_zero_and_literal_formula(self):
        definition = {**self.definition, 'output_schema': {'format': 'table', 'columns': ['进度', '金额', '文本']},
                      'ui_config': {'sort_column': '进度', 'sort_first': '延期'}}
        value = apps.result({'text': '处理完成', 'rows': [
            {'进度': '正常', '金额': 2, '文本': '甲'},
            {'进度': '延期', '金额': 0, '文本': '=1+1'}
        ]}, definition)
        self.assertEqual(value['rows'][0]['进度'], '延期')
        apps.export_result(self.root, value)
        book = load_workbook(self.root / 'outputs/结果.xlsx')
        self.assertEqual(book.active['B2'].value, 0)
        self.assertEqual(book.active['C2'].data_type, 's')
        book.close()
        text = ' '.join(block['text'] for block in extract(self.root / 'outputs/结果.docx')['blocks'])
        self.assertIn('0', text)
        self.assertIn('=1+1', text)


if __name__ == '__main__':
    unittest.main()
