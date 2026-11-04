"""Import the DRM broadcast schedule from drm.org into public/index.html.

usage:
  curl -sL -o /tmp/drm/page.html https://www.drm.org/drm-in-the-world/broadcast-schedule/
  python3 -I tools/import_drm.py /tmp/drm/page.html public/index.html

The page embeds the shortwave schedule as JSON (<script id="drm-sw-data">) and lists
the Indian DRM mediumwave transmitters in a table (id="table2", no broadcast times).
The result is written to <script type="application/json" id="drmdata"> in index.html;
the HFCC block (#hfdata) is left untouched, so the import can simply be rerun.

  - marks: HFCC rows (key f|s|loc) that a drm.org entry confirms -> get the drm.org status
  - extra: drm.org entries with no matching HFCC row -> added as new records
"""
import html, json, re, sys
from datetime import date

src_page, index_path = sys.argv[1], sys.argv[2]
page = open(src_page, encoding='utf-8', errors='replace').read()
index = open(index_path, encoding='utf-8').read()

m = re.search(r'<script[^>]*\bid="drm-sw-data"[^>]*>(.*?)</script>', page, re.S)
assert m, 'drm-sw-data block not found -- page layout changed?'
sw = json.loads(m.group(1))

hf = json.loads(re.search(r'<script type="application/json" id="hfdata">(.*?)</script>',
                          index, re.S).group(1).replace('<\\/', '</'))
rows = [dict(zip(hf['cols'], r)) for r in hf['rows']]

# ---- lookups ----
SITE_ALIAS = {'Qihar': 'Qiqihar', 'Donfang': 'Dongfang'}            # drm.org spelling -> HFCC
EXTRA_SITES = {'Pyongyang': (39.03, 125.75)}                       # not in HFCC site table
ADM = {'Germany': 'Germany', 'Romania': 'Romania', 'France': 'France', 'New Zealand': 'New Zealand',
       'China': 'China', 'United Kingdom': 'United Kingdom', 'DPR Korea': 'Korea (D.P.R.)', 'India': 'India'}
LANG = {'Multi': 'Multiple languages', 'Various': 'Multiple languages', 'Not specified': ''}
DAYS = {'Daily': '1234567', 'Tue & Thu': '24', 'Sun-Fri': '123457'}  # 1=Mon … 7=Sun
STATUS = {'confirmed': '已确认', 'likely': '较可能', 'uncertain': '待核实'}
site_by_name = {v[0].lower(): (k, v[0], v[1], v[2]) for k, v in hf['loc'].items()}

def ddmmyy(iso):  # '2026-10-25' -> '251026' (HFCC fd/td format)
    y, mth, d = iso.split('-'); return d + mth + y[2:]

def mins(t): return int(t[:2]) * 60 + int(t[2:])

def overlaps(s1, e1, s2, e2):
    def spans(s, e):
        a, b = mins(s), mins(e)
        return [(a, b)] if b > a else [(a, 1440), (0, b)]
    return any(x0 < y1 and y0 < x1 for x0, x1 in spans(s1, e1) for y0, y1 in spans(s2, e2))

marks, extra, unmatched_sites = [], [], set()
for rec in sw['records']:
    time, brc, freq, days, lang, target, site, power, az = rec['values']
    country, _, town = (s.strip() for s in site.partition(','))
    town = SITE_ALIAS.get(town, town)
    hit = site_by_name.get(town.lower())
    if hit: loc, site_name, lat, lon = hit
    elif town in EXTRA_SITES: loc, site_name, (lat, lon) = '', town, EXTRA_SITES[town]
    else: loc, site_name, lat, lon = '', site, None, None; unmatched_sites.add(site)
    freq = re.match(r'\d+', freq).group(0)
    status = {'drmStatus': STATUS.get(rec['confidence'], rec['confidence']), 'drmLabel': rec.get('label', '')}
    for span in time.split():                       # '1759-1858 1859-1958' -> two records
        s, e = span.split('-')
        same = [r for r in rows if str(r['f']) == freq and loc and r['loc'] == loc and overlaps(s, e, r['s'], r['e'])]
        if same:
            marks += [{'key': f"{r['f']}|{r['s']}|{r['loc']}", **status} for r in same]
            continue
        extra.append({
            'f': int(freq), 's': s, 'e': e, 'days': DAYS.get(days, ''), 'ciraf': '', 'loc': loc,
            'site': site_name, 'lat': lat, 'lon': lon,
            'pow': power.replace(',', '.'), 'az': az if az.isdigit() else '0',
            'fd': ddmmyy(sw['validFrom']), 'td': ddmmyy(sw['validTo']), 'mod': 'N',
            'lang': LANG.get(lang, lang), 'langname': LANG.get(lang, lang),
            'adm': ADM.get(country, country), 'admname': ADM.get(country, country),
            'brc': brc, 'brcname': brc, 'fmo': '', 'alt': '',
            'notes': '目标区：' + target + ('' if days in DAYS else '；' + days)
                     + ('' if az.isdigit() or az == 'Non Directional' else '；方位未确认'),
            **status, 'src': 'drm.org'})

# ---- Indian DRM mediumwave (table2): city, frequency, max AM power; no times published ----
CITY = {  # city centre coordinates (transmitter sites are nearby; good enough at map scale)
    'Mumbai': (19.08, 72.88), 'Ranchi': (23.34, 85.31), 'Dibrugarh': (27.48, 94.91), 'Ajmer': (26.45, 74.64),
    'Bengaluru': (12.97, 77.59), 'Patna': (25.59, 85.14), 'Kolkata': (22.57, 88.36), 'Itanagar': (27.08, 93.61),
    'Siliguri': (26.73, 88.40), 'Chennai': (13.08, 80.27), 'Hyderabad': (17.39, 78.49), 'Lucknow': (26.85, 80.95),
    'Dharwad': (15.46, 75.01), 'Pune': (18.52, 73.86), 'Jabalpur': (23.18, 79.99), 'Rajkot': (22.30, 70.80),
    'New Delhi': (28.61, 77.21), 'Vijayawada': (16.51, 80.65), 'Ahmedabad': (23.02, 72.57), 'Jalandhar': (31.33, 75.58),
    'Suratgarh': (29.32, 73.90), 'Visakhapatnam': (17.69, 83.22), 'Tiruchirappalli': (10.79, 78.70),
    'Jammu': (32.73, 74.86), 'Guwahati': (26.14, 91.74), 'Pasighat': (28.07, 95.33), 'Varanasi': (25.32, 82.97),
    'Panaji': (15.50, 73.83), 'Bikaner': (28.02, 73.31), 'Barmer': (25.75, 71.39), 'Tawang': (27.59, 91.87),
}
mw = 0
t = re.search(r'<table[^>]*\bid="table2".*?</table>', page, re.S)
if t:
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', t.group(0), re.S):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(cells) < 3: continue
        parts = [html.unescape(p).strip() for p in re.split(r'<[^>]+>', cells[0]) if p.strip()]
        name, state = parts[0], (parts[1] if len(parts) > 1 else '')
        city = re.sub(r'\s+[A-C]$', '', name)
        f = re.search(r'\d+', html.unescape(re.sub(r'<[^>]+>', '', cells[1]))).group(0)
        p = re.search(r'[\d.]+', html.unescape(re.sub(r'<[^>]+>', '', cells[2]))).group(0)
        lat, lon = CITY.get(city, (None, None))
        if lat is None: unmatched_sites.add(name)
        extra.append({
            'f': int(f), 's': '', 'e': '', 'days': '', 'ciraf': '', 'loc': '', 'site': name, 'lat': lat, 'lon': lon,
            'pow': p, 'az': '0', 'fd': ddmmyy(sw['validFrom']), 'td': ddmmyy(sw['validTo']), 'mod': 'N',
            'lang': '', 'langname': '', 'adm': 'India', 'admname': 'India',
            'brc': 'All India Radio', 'brcname': 'All India Radio', 'fmo': '', 'alt': '',
            'notes': f'DRM 中波（{state}）；播出时间未公布；功率为最大 AM 额定功率',
            'drmStatus': '已确认', 'drmLabel': 'drm.org India MW list', 'src': 'drm.org'})
        mw += 1

out = {'source': {'url': 'https://www.drm.org/drm-in-the-world/broadcast-schedule/', 'season': sw['season'],
                  'validFrom': sw['validFrom'], 'validTo': sw['validTo'], 'updatedAt': sw['updatedAt'],
                  'importedAt': date.today().isoformat()},
       'marks': marks, 'extra': extra}
txt = json.dumps(out, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/').replace('<!--', '<\\!--')
block = f'<script type="application/json" id="drmdata">{txt}</script>\n'
if 'id="drmdata"' in index:
    index = re.sub(r'<script type="application/json" id="drmdata">.*?</script>\n', lambda _: block, index, count=1, flags=re.S)
else:
    i = index.index('<script type="application/json" id="hfland">')
    index = index[:i] + block + index[i:]
open(index_path, 'w', encoding='utf-8').write(index)

print(f"drm.org {sw['season']} (updated {sw['updatedAt']}): {len(sw['records'])} SW entries -> "
      f"{len(marks)} HFCC rows confirmed, {len(extra) - mw} SW records added; {mw} India MW added")
if unmatched_sites: print('no coordinates (list only, not on map):', sorted(unmatched_sites))
