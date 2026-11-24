"""Unpack the complete supplied distribution to a fresh local installation."""
from pathlib import Path, PureWindowsPath
import shutil
import zipfile
from fix_database_canvas import apply

root = Path(__file__).resolve().parents[1]
destination = root/'integrations/full'
destination.mkdir(exist_ok=False)
with zipfile.ZipFile(root/'数据库项目.zip') as archive:
    entries = archive.infolist()
    # Extract the application, data and interpreter packages first.
    def order(entry):
        return any(x in entry.filename for x in ('/node_modules/', '/.git/'))

    for info in sorted(entries, key=order):
        relative = PureWindowsPath(info.filename)
        if relative.anchor or '..' in relative.parts or ':' in info.filename:
            raise ValueError('压缩包中出现非法路径')
        target = destination / relative
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
apply(destination/'数据库项目/data-formulator')
print(f'已解包 {len(entries)} 项并应用画布修复。')
