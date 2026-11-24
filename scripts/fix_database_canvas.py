"""Apply the attachment-only chart fix to the supplied database distribution."""
from pathlib import Path
import os
import sys


def apply(project):
    bundle = project / 'py-src/data_formulator/dist/DataFormulator.js'
    old = 'let WB=generateFreshChart(Du[0].id,"Auto");WB.source="trigger",f0.derive&&(f0.derive.trigger.chart=WB);'
    new = 'if(Du[0]&&f0.derive){let WB=generateFreshChart(Du[0].id,"Auto");WB.source="trigger",f0.derive.trigger.chart=WB;}'
    original = bundle.read_bytes()
    patched = original
    patches = [
        (old, new),
        ('generatedReports:a.generatedReports||[]',
         'generatedReports:(a.generatedReports||[]).map(report=>report.status==="generating"?{...report,status:"error"}:report)'),
    ]
    for before, after in patches:
        if after.encode() in patched:
            continue
        if patched.count(before.encode()) != 1:
            raise ValueError('互动数据库前端版本不匹配，请核对补丁')
        patched = patched.replace(before.encode(), after.encode(), 1)
    if patched == original:
        return
    pending = bundle.with_suffix('.js.pending')
    pending.write_bytes(patched)
    os.replace(pending, bundle)


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
