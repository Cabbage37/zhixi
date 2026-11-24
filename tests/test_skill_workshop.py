import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.runtime/python')]
import skill_workshop as workshop

CONTENT = '---\nname: weekly-brief\ndescription: 按原记录生成周报。\n---\n\n按进展、风险和下一步整理。\n'


class WorkshopTests(unittest.TestCase):
    def test_import_edit_export_keeps_original_and_resources(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(workshop, 'BASE', Path(tmp) / 'versions'):
            archive = Path(tmp) / 'skill.zip'
            sample = b'progress,owner\nreview,team\n'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('weekly-brief/SKILL.md', CONTENT)
                bundle.writestr('weekly-brief/assets/example.csv', sample)
            content, assets = workshop.import_bundle(archive)
            original = workshop.save_version(content, '原始导入', assets=assets)
            edited = workshop.save_version(content + '\n缺少日期时留空。', 'v0.2.0', parent=original['id'])
            self.assertEqual(workshop.get(original['id'])['content'], content)
            self.assertEqual(edited['bundle'], original['bundle'])
            with zipfile.ZipFile(io.BytesIO(workshop.package(workshop.get(edited['id'])))) as exported:
                self.assertEqual(exported.read('weekly-brief/assets/example.csv'), sample)
                self.assertIn('缺少日期', exported.read('weekly-brief/SKILL.md').decode())

    def test_zip_path_traversal_and_duplicate_case_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'skill.zip'
            for paths in [['../escape.txt'], ['assets/file.txt', 'assets/FILE.TXT']]:
                with zipfile.ZipFile(archive, 'w') as bundle:
                    bundle.writestr('SKILL.md', CONTENT)
                    for path in paths:bundle.writestr(path, 'test')
                with self.assertRaises(ValueError):workshop.import_bundle(archive)

    def test_model_cannot_rename_revision(self):
        options = workshop.job_options({'action':'revise','content':CONTENT,'changes':'修改输出'})
        with self.assertRaises(ValueError):workshop.finish(options,CONTENT.replace('weekly-brief','different'))


if __name__ == '__main__':unittest.main()
