"""Replace the #hfdata block of index.html with records from an HFCC B??all00.TXT file.
usage: python3 -I import_txt.py <B26all00.TXT> <index.html> [--check]
--check: only compare the parsed rows with the current #hfdata rows, don't write."""
import json, re, sys

txt, html_path = sys.argv[1], sys.argv[2]
check = '--check' in sys.argv[3:]

lines = open(txt, encoding='ascii').read().splitlines()
ruler = next(l for l in lines if l.startswith(';----+'))
cuts = [0] + [i for i, c in enumerate(ruler) if c == '+'] + [None]
NAMES = ['FREQ', 'STRT', 'STOP', 'CIRAF', 'LOC', 'POWR', 'AZIMUTH', 'SLW', 'ANT', 'DAYS', 'FDATE', 'TDATE',
         'MOD', 'AFRQ', 'LANGUAGE', 'ADM', 'BRC', 'FMO', 'REQ', 'OLD', 'ALT1', 'ALT2', 'ALT3', 'NOTES']
assert len(cuts) - 1 == len(NAMES)

def parse(l):
    v = dict(zip(NAMES, (l[a:b].strip() for a, b in zip(cuts, cuts[1:]))))
    return {'f': int(v['FREQ']), 's': v['STRT'], 'e': v['STOP'], 'ciraf': v['CIRAF'], 'loc': v['LOC'],
            'pow': v['POWR'], 'az': v['AZIMUTH'], 'days': v['DAYS'], 'fd': v['FDATE'], 'td': v['TDATE'],
            'mod': v['MOD'], 'lang': v['LANGUAGE'], 'adm': v['ADM'], 'brc': v['BRC'], 'fmo': v['FMO'],
            'alt': v['ALT1'], 'notes': v['NOTES']}

recs = [parse(l) for l in lines if l.strip() and not l.startswith(';')]

html = open(html_path, encoding='utf-8').read()
m = re.search(r'(<script type="application/json" id="hfdata">)(.*?)(</script>)', html, re.S)
P = json.loads(m.group(2).replace('<\\/', '</'))
rows = [[r[c] for c in P['cols']] for r in recs]

if check:
    print('identical' if rows == P['rows'] else 'DIFFERENT', len(rows), len(P['rows']))
    sys.exit(rows != P['rows'])

# 名称字典沿用现有的；新代码需要人工补充名称/经纬度
missing = {k: sorted({r[k] for r in recs} - P[k].keys()) for k in ('loc', 'lang', 'adm', 'brc')}
if any(missing.values()):
    sys.exit(f'unknown codes, add them to the dictionaries first: {missing}')
used = {k: {r[k] for r in recs} for k in ('loc', 'lang', 'adm', 'brc')}
P['rows'] = rows
for k in used:
    P[k] = {c: n for c, n in P[k].items() if c in used[k]}

body = json.dumps(P, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/').replace('<!--', '<\\!--')
open(html_path, 'w', encoding='utf-8').write(html[:m.start(2)] + body + html[m.end(2):])
print(f'{len(rows)} records written')
