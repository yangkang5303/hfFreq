"""Embed tools/i18n/zh_names.json into public/index.html as <script id="zhnames"> and list untranslated names.

usage: python3 -I tools/build_i18n.py public/index.html [tools/i18n/zh_names.json]

Run after any data import (import_txt / import_drm / import_eibi): new languages, countries,
broadcasters or sites show up in the report; add them to zh_names.json and run again.
Names without an entry are shown in their original (English) form in the Chinese UI.
"""
import json, re, sys
from pathlib import Path

index_path = sys.argv[1]
names_path = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent / 'i18n' / 'zh_names.json')
html = open(index_path, encoding='utf-8').read()
zh = json.load(open(names_path, encoding='utf-8'))

def block(i):
    m = re.search(rf'<script type="application/json" id="{i}">(.*?)</script>', html, re.S)
    return json.loads(m.group(1).replace('<\\/', '</'))

# collect the names the page will show (same fields as the page's DATA records)
hf, drm, eibi = block('hfdata'), block('drmdata'), block('eibidata')
seen = {'lang': {}, 'country': {}, 'brc': {}, 'site': {}}
def add(kind, name):
    if name: seen[kind][name] = seen[kind].get(name, 0) + 1
for a in hf['rows']:
    r = dict(zip(hf['cols'], a))
    add('lang', hf['lang'].get(r['lang'])); add('country', hf['adm'].get(r['adm']))
    add('brc', hf['brc'].get(r['brc'])); add('site', hf['loc'][r['loc']][0])
for r in drm['extra']:
    add('lang', r['langname']); add('country', r['admname']); add('brc', r['brcname']); add('site', r['site'])
for a in eibi['rows']:
    r = {c: (eibi['dicts'][c][a[i]] if c in eibi['dicts'] else a[i]) for i, c in enumerate(eibi['cols'])}
    add('lang', r['langname']); add('country', r['admname']); add('brc', r['brcname']); add('site', r['site'])

payload = {k: {n: z for n, z in zh[k].items() if n in seen[k]} for k in seen}   # only names in use
txt = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/').replace('<!--', '<\\!--')
blk = f'<script type="application/json" id="zhnames">{txt}</script>\n'
if 'id="zhnames"' in html:
    html = re.sub(r'<script type="application/json" id="zhnames">.*?</script>\n', lambda _: blk, html, count=1, flags=re.S)
else:
    i = html.index('<script type="application/json" id="hfland">')
    html = html[:i] + blk + html[i:]
open(index_path, 'w', encoding='utf-8').write(html)

for k, names in seen.items():
    total = sum(names.values()); missing = {n: c for n, c in names.items() if n not in zh[k]}
    cov = 100 * (total - sum(missing.values())) / total
    print(f'{k:8} {len(names) - len(missing)}/{len(names)} names translated, {cov:.0f}% of records')
    if missing:
        print('   untranslated:', ', '.join(f'{n} ({c})' for n, c in sorted(missing.items(), key=lambda x: -x[1])[:30])
              + (' …' if len(missing) > 30 else ''))
print(f'#zhnames {len(txt) // 1024} KB')
