"""Add EiBi broadcasts that HFCC does not have to public/index.html.

usage:
  curl -s -o /tmp/eibi/sked-b26.csv http://www.eibispace.de/dx/sked-b26.csv
  curl -s -o /tmp/eibi/README.TXT   http://www.eibispace.de/dx/README.TXT
  python3 -I tools/import_eibi.py /tmp/eibi/sked-b26.csv /tmp/eibi/README.TXT public/index.html [--stats]

EiBi (http://www.eibispace.de/dx/, Eike Bierwirth) is free to use and redistribute.
Only shortwave broadcasts (2300-26100 kHz) are taken; utility stations, inactive entries,
harmonics/intermod/alternate frequencies are skipped. An EiBi entry is dropped as a duplicate
when HFCC (or drm.org) already has the same frequency, an overlapping time and a transmitter
within DUP_KM. The rest is written to <script type="application/json" id="eibidata">;
#hfdata and #drmdata are left untouched, so the import can be rerun after either changes.
EiBi has no power or antenna azimuth: pow is left empty, az = 0 (drawn as omnidirectional).
"""
import csv, io, json, math, re, sys
from datetime import date

csv_path, readme_path, index_path = sys.argv[1:4]
stats_only = '--stats' in sys.argv[4:]
LO, HI, DUP_KM = 2300, 26100, 600

readme = open(readme_path, encoding='latin-1').read()
rows = list(csv.reader(io.StringIO(open(csv_path, encoding='latin-1').read()), delimiter=';'))[1:]
season = re.search(r'sked-([ab]\d\d)', csv_path, re.I).group(1).upper()

def section(title, nxt):
    a = readme.index(title, readme.index('D) Codes used.') + 40)
    return readme[a:readme.index(nxt, a + len(title))]

# ---- code tables from README ----
LANG = {}
for m in re.finditer(r'^   (-?[A-Z0-9]{1,3})\s{2,}(.+?)(?:\s+\[[a-z]{3}\])?\s*$', section('I) Language codes.', 'II) Country codes.'), re.M):
    name = re.sub(r'\s*\([\d.,]+\s*[mk]?\)', '', m.group(2))      # drop speaker counts "(300m)"
    LANG[m.group(1)] = re.split(r':', name)[0].strip()               # drop ": Georgia-Abkhazia"
COUNTRY = {m.group(1): m.group(2).strip() for m in re.finditer(
    r'^   ([A-Z]{1,3})\*?\s+(\S.*)$', section('II) Country codes.', 'III) Target-area codes.'), re.M)}
TARGET = {m.group(1): m.group(2).strip() for m in re.finditer(
    r'^   (\S+)\s+-\s+(.+)$', section('III) Target-area codes.', 'IV) Transmitter site codes.'), re.M)}

def coord(t):  # '26S07\'40"' / '69E20' -> decimal degrees
    m = re.match(r'(\d+)([NSEW])(\d+)(?:\'(\d+)")?', t)
    v = int(m.group(1)) + int(m.group(3)) / 60 + int(m.group(4) or 0) / 3600
    return round(-v if m.group(2) in 'SW' else v, 3)

SITES, DEFAULT = {}, {}   # SITES[(country, code)] = (name, lat, lon); DEFAULT[country] = (name, lat, lon)
cur = None
for line in readme[readme.index('IV) Transmitter site codes.'):].splitlines():
    m = re.match(r'^   ([A-Z]{1,3}):\s*(.*)$', line) or re.match(r'^        ()(\S.*)$', line)
    if not m: continue
    if m.group(1): cur = m.group(1)
    body = m.group(2)
    c = re.search(r'(\d+[NS][\d\'"]*)\s*-\s*(\d+[EW][\d\'"]*)', body)
    if not cur or not c: continue
    lat, lon = coord(c.group(1)), coord(c.group(2))
    code = re.match(r'^([a-z0-9]{1,3})-(.*)', body)
    if code:
        SITES[(cur, code.group(1))] = (code.group(2)[:c.start() - len(code.group(1)) - 1].strip(' ,'), lat, lon)
    else:
        DEFAULT.setdefault(cur, (body[:c.start()].strip(' ,'), lat, lon))

def site_of(country, field):
    """EiBi #8: ''=home default, 'k'=site k at home, '/ROU'=host default, '/ROU-t'=site t in ROU."""
    host, code = country, field.strip()
    if code.startswith('/'):
        host, _, code = code[1:].partition('-')
    if code: return SITES.get((host, code)), host
    return DEFAULT.get(host), host

# ---- existing data (HFCC + drm.org) for de-duplication ----
html = open(index_path, encoding='utf-8').read()
def block(i):
    return json.loads(re.search(rf'<script type="application/json" id="{i}">(.*?)</script>', html, re.S).group(1).replace('<\\/', '</'))
hf, drm = block('hfdata'), block('drmdata')
known = []
for a in hf['rows']:
    r = dict(zip(hf['cols'], a)); _, lat, lon = hf['loc'][r['loc']]
    known.append((r['f'], r['s'], r['e'], lat, lon))
known += [(r['f'], r['s'], r['e'], r['lat'], r['lon']) for r in drm['extra'] if r['s']]
by_f = {}
for k in known: by_f.setdefault(round(k[0]), []).append(k)

def mins(t): return int(t[:2]) * 60 + int(t[2:])
def spans(s, e):
    a, b = mins(s), mins(e)
    return [(a, b)] if b > a else [(a, 1440), (0, b)]
def overlaps(s1, e1, s2, e2):
    return any(x0 < y1 and y0 < x1 for x0, x1 in spans(s1, e1) for y0, y1 in spans(s2, e2))
def km(a, b, c, d):
    p1, p2, dl = math.radians(a), math.radians(c), math.radians(d - b)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(min(1, h)))

DAYNUM = {'Mo': '1', 'Tu': '2', 'We': '3', 'Th': '4', 'Fr': '5', 'Sa': '6', 'Su': '7'}
def days_of(d):
    """'Mo-Fr' -> '12345', 'SaSu' -> '67', '1245' -> '1245'; special values -> ('', note)."""
    if not d: return '1234567', ''
    d = d.replace(',', '')   # 'Tu,Fr' -> 'TuFr'
    if re.fullmatch(r'[1-7]+', d): return d, ''
    m = re.fullmatch(r'(Mo|Tu|We|Th|Fr|Sa|Su)-(Mo|Tu|We|Th|Fr|Sa|Su)', d)
    if m:
        a, b = int(DAYNUM[m.group(1)]), int(DAYNUM[m.group(2)])
        return ''.join(str((a - 1 + i) % 7 + 1) for i in range((b - a) % 7 + 1)), ''
    parts = re.findall(r'Mo|Tu|We|Th|Fr|Sa|Su', d)
    if parts and ''.join(parts) == d: return ''.join(DAYNUM[p] for p in parts), ''
    return '1234567', d   # irr / tent / test / 1.Sa ... : keep, show as note

# Language names follow HFCC's spelling so the language dropdown has no duplicates:
# "Spanish/Castellano" -> "Spanish", "Cantonese / Yue" -> "Cantonese", plus a few aliases.
HFCC_LANG = set(hf['lang'].values())
LANG_ALIAS = {'Mandarin': 'Mandarin Chinese', 'Hakka': 'Hakka Chinese', 'Amoy': 'Min Nan Chinese',
              'Farsi': 'Persian', 'Pashto': 'Pushto', 'Kyrgyz': 'Kirghiz', 'Khmer': 'Central Khmer', 'Creole': 'Haitian'}
def lang_name(code):
    n = LANG.get(code, code)
    if n in HFCC_LANG: return n
    short = re.split(r' \(|/| / ', n)[0].strip()
    short = LANG_ALIAS.get(short, short)
    return short if short in HFCC_LANG or short in LANG_ALIAS.values() else n

SKIP_DAYS = {'alt', 'harm', 'imod'}
# EiBi mixes utility stations into the broadcast list without the "90+" persistence flag it documents,
# so they are recognised by name: fax/meteo/maritime/coast guard/navy, numbers stations, jammers, beacons,
# and coast stations named "<callsign> <place> Radio" (e.g. "VCS Halifax Radio", "TAH Turk Radio Istanbul").
UTILITY = re.compile(r'Numbers|Fax|Meteo|\bMet\b|Volmet|USCG|Maritime|Coast|Navy|Naval|Jammer|Firedrake|\bWx\b|LDOC'
                     r'|NAVTEX|Air Force|Channel Marker|Squeaky Wheel|Buzzer|HF Trading|Military|STANAG|\bATC\b', re.I)
COAST = re.compile(r'^([A-Z]{1,3}\d?[A-Z0-9]{0,3}) \S.*\b(Radio|R\.)(\s+\w+)?$')
BROADCASTER_ABBR = {'CNR', 'CNR5', 'FEBC', 'KBS', 'MWV'}   # look like callsigns but are broadcasters
# Aeronautical / coast / meteo stations whose names look like broadcasters ("Hue Radio", "Shannon Aeradio").
# Checked by hand against the B26 list; prefix match. Revisit when importing a new season.
UTILITY_NAMES = (
    'Armor French Ny', 'Auckland Radio', 'Bangkok Meterolog', 'Ben Thuy Radio', 'Bodo Radio', 'Brisbane Radio',
    'Ca Mau Radio', 'Can Tho Radio', 'Central Weather Bureau', 'Chennai Radio', 'Colombo Radio', 'DWD ',
    'Da Nang Radio', 'Dakar Radio', 'Delhi Radio', 'Duyen Hai Information', 'Ejercito del Aire', 'Filler music',
    'Gander Radio', 'Hai Phong Radio', 'Ho Chi Minh City R.', 'Hon Gai Radio', 'Hue Radio', 'Iceland Radio',
    'KFS Rio Vista', 'KLB Seattle', 'KPH Rio Vista', 'Kien Giang Radio', 'Kolkata Radio', 'Las Palmas Radio',
    'Lyngby Radio', 'Mogadishu Radio', 'Mong Cai Radio', 'Mumbai Radio', 'Nadi Radio', 'Naha Radio',
    'New York Radio', 'Nha Trang Radio', 'Olimpia Radio', 'Phan Rang Radio', 'Phan Tiet Radio', 'Phu Yen Radio',
    'Piarco Radio', 'Quy Nhon Radio', 'RFID devices', 'Reykjavik Radio', 'Romaradio', 'San Francisco Radio',
    'Santa Maria Radio', 'Search and Rescue', 'Seychelles Control', 'Shannon Aeradio', 'Tahiti Radio',
    'Telenor Kystradio', 'Tokyo Radio', 'VCF ', 'VCP ', 'VOJ ', 'VMC ', 'VMW ', 'Vung Tau Radio', 'ZBM ')
# Broadcasters deliberately left out of the site (prefix match).
EXCLUDE_STATIONS = ('Sound of Hope',)

def is_utility(name):
    m = COAST.match(name)
    return bool(UTILITY.search(name) or (m and m.group(1) not in BROADCASTER_ABBR)
                or name.startswith(UTILITY_NAMES))
stats = {'total': len(rows), 'not HF': 0, 'utility/inactive/alt': 0, 'excluded by name': 0, 'duplicate of HFCC/drm.org': 0,
         'no site coordinates': 0, 'added': 0}
out = []
for r in rows:
    if len(r) < 11 or not r[0]: continue
    f = float(r[0]); t = r[1]; d = r[2]; ctry = r[3]; stn = r[4]; lng = r[5]; tgt = r[6]; site = r[7]
    pers = int(r[8] or 1)
    if not (LO <= f <= HI) or not re.fullmatch(r'\d{4}-\d{4}', t):
        stats['not HF'] += 1; continue
    if pers >= 90 or pers == 8 or lng.startswith('-') or d in SKIP_DAYS or is_utility(stn):
        stats['utility/inactive/alt'] += 1; continue
    if stn.startswith(EXCLUDE_STATIONS):
        stats['excluded by name'] += 1; continue
    s, e = t.split('-')
    loc, host = site_of(ctry, site)
    lat, lon = (loc[1], loc[2]) if loc else (None, None)
    dup = any(overlaps(s, e, ks, ke) and (lat is None or klat is None or km(lat, lon, klat, klon) <= DUP_KM)
              for kf, ks, ke, klat, klon in by_f.get(round(f), []) if abs(kf - f) < 1)
    if dup:
        stats['duplicate of HFCC/drm.org'] += 1; continue
    if not loc: stats['no site coordinates'] += 1
    days, dnote = days_of(d)
    langs = [lang_name(x) for x in lng.split(',') if x]
    notes = ['目标区：' + TARGET.get(tgt, tgt)] if tgt else []
    if dnote: notes.append(dnote)
    if not loc: notes.append('发射地不详' + (f'（{COUNTRY.get(host, host)}）' if host else ''))
    out.append({
        'f': int(f) if f == int(f) else f, 's': s, 'e': e, 'days': days, 'ciraf': '', 'loc': '',
        'site': loc[0] if loc else COUNTRY.get(host, host), 'lat': lat, 'lon': lon,
        'pow': '', 'az': '0', 'fd': '', 'td': '', 'mod': 'N' if re.search(r'\bDRM\b', stn) else 'D',
        'lang': lng, 'langname': ' / '.join(langs) if len(langs) > 1 else (langs[0] if langs else ''),
        'adm': ctry, 'admname': hf['adm'].get(ctry) or COUNTRY.get(ctry, ctry),
        'brc': stn, 'brcname': stn, 'fmo': '', 'alt': '', 'notes': '；'.join(notes), 'src': 'EiBi'})
stats['added'] = len(out)

for k, v in stats.items(): print(f'{k:28} {v}')
if stats_only: sys.exit()

# compact like #hfdata: column arrays + dictionaries for the repeated strings (decoded in index.html)
DICT = ('site', 'langname', 'admname', 'brcname', 'notes')
COLS = ('f', 's', 'e', 'days', 'mod', 'site', 'langname', 'admname', 'brcname', 'notes')
dicts = {k: [] for k in DICT}; index_of = {k: {} for k in DICT}
sites = {}   # site name -> [lat, lon]
def ref(k, v):
    if v not in index_of[k]: index_of[k][v] = len(dicts[k]); dicts[k].append(v)
    return index_of[k][v]
packed = []
for r in out:
    sites.setdefault(r['site'], [r['lat'], r['lon']])
    packed.append([ref(c, r[c]) if c in DICT else r[c] for c in COLS])
payload = {'source': {'url': 'http://www.eibispace.de/dx/', 'season': season, 'importedAt': date.today().isoformat()},
           'cols': COLS, 'dicts': dicts, 'sites': sites, 'rows': packed}
txt = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/').replace('<!--', '<\\!--')
blk = f'<script type="application/json" id="eibidata">{txt}</script>\n'
if 'id="eibidata"' in html:
    html = re.sub(r'<script type="application/json" id="eibidata">.*?</script>\n', lambda _: blk, html, count=1, flags=re.S)
else:
    i = html.index('<script type="application/json" id="hfland">')
    html = html[:i] + blk + html[i:]
open(index_path, 'w', encoding='utf-8').write(html)
print(f'written #eibidata ({len(txt)//1024} KB)')
