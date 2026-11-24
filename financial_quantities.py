"""Match explicit financial quantities in claims against their cited passages."""
import re
from decimal import Decimal

# Preserve scale and currency. Only equivalences with an unambiguous unit are allowed.
ALIASES = {'％': '%', 'percent': '%', 'percentage points': '个百分点',
           'percentage point': '个百分点', 'basis points': '基点', 'basis point': '基点',
           'bps': '基点', 'bp': '基点'}
UNITS = sorted(set(ALIASES) | set(ALIASES.values()) |
               {scale + currency for scale in ('', '万', '亿') for currency in
                ('元', '美元', '港元', '人民币', '港币', '欧元')}, key=len, reverse=True)
PATTERN = re.compile(r'(?<![0-9.,])([+−-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)\s*('
                     + '|'.join(map(re.escape, UNITS)) + ')', re.I)

def quantities(text):
    for match in PATTERN.finditer(text):
        number, unit = match.groups()
        value = Decimal(number.replace(',', '').replace('−', '-'))
        yield match.group().strip(), (value, ALIASES.get(unit.lower(), unit))

def unsupported_quantities(claim, citations):
    supported = {key for quote in citations for _, key in quantities(quote)}
    return list(dict.fromkeys(label for label, key in quantities(claim) if key not in supported))
