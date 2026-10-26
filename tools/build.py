"""Build an optimized index.html from the live one.  usage: python3 -I build.py <in.html> <out.html>"""
import json, re, sys

src, dst = sys.argv[1], sys.argv[2]
html = open(src, encoding='utf-8').read()

m = re.search(r'(<script(?![^>]*\bsrc=)[^>]*>)(.*?)(</script>)', html, re.S)
lines = m.group(2).split('\n')
assert lines[1].startswith('const DATA = ') and lines[2].startswith('const LAND = ')
DATA = json.loads(lines[1][len('const DATA = '):-1])
LAND = json.loads(lines[2][len('const LAND = '):-1])

# ---- compact data: drop unused fields, dictionary-encode names ----
DROP = {'ant', 'afrq', 'req', 'old'}
DERIVED = {'site', 'lat', 'lon', 'langname', 'admname', 'brcname'}
cols = [k for k in DATA[0] if k not in DROP | DERIVED]
packed = {
    'cols': cols,
    'rows': [[r[c] for c in cols] for r in DATA],
    'loc': {r['loc']: [r['site'], r['lat'], r['lon']] for r in DATA},
    'lang': {r['lang']: r['langname'] for r in DATA},
    'adm': {r['adm']: r['admname'] for r in DATA},
    'brc': {r['brc']: r['brcname'] for r in DATA},
}

# ---- compact land: geometry only, 2-decimal coordinates (~1 km, invisible at 110m scale) ----
def rnd(c):
    return [rnd(x) for x in c] if isinstance(c[0], list) else [round(c[0], 2), round(c[1], 2)]
land = {'features': [{'geometry': {'type': f['geometry']['type'],
                                   'coordinates': rnd(f['geometry']['coordinates'])}}
                     for f in LAND['features'] if f.get('geometry')]}

def as_json_script(id_, obj):
    txt = json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/').replace('<!--', '<\\!--')
    return f'<script type="application/json" id="{id_}">{txt}</script>\n'

DECODE = r"""const DATA = (() => {
  const P = JSON.parse(document.getElementById('hfdata').textContent);
  const C = P.cols;
  return P.rows.map(a => {
    const r = {};
    for (let i = 0; i < C.length; i++) r[C[i]] = a[i];
    const st = P.loc[r.loc];
    r.site = st[0]; r.lat = st[1]; r.lon = st[2];
    r.langname = P.lang[r.lang]; r.admname = P.adm[r.adm]; r.brcname = P.brc[r.brc];
    // 搜索用文本只算一次，避免每次输入都为全部记录重新拼接
    r._q = (r.f+' '+r.s+' '+r.e+' '+r.loc+' '+r.site+' '+r.langname+' '+r.lang+' '+
      r.brcname+' '+r.brc+' '+r.admname+' '+r.adm+' '+r.notes+' '+r.ciraf+' '+r.pow).toLowerCase();
    return r;
  });
})();
const LAND = JSON.parse(document.getElementById('hfland').textContent);"""

code = '\n'.join([lines[0], DECODE] + lines[3:])

EDITS = [
    # search: use the precomputed haystack
    ("""      const hay = (r.f+' '+r.s+' '+r.e+' '+r.loc+' '+r.site+' '+r.langname+' '+r.lang+' '+
        r.brcname+' '+r.brc+' '+r.admname+' '+r.adm+' '+r.notes+' '+r.ciraf+' '+r.pow).toLowerCase();
      if (!hay.includes(q)) return false;""",
     """      if (!r._q.includes(q)) return false;"""),
    # stats: evaluate on-air once instead of twice over the whole database
    ("""  const onair = DATA.filter(r=>isOnAir(r, curMin, dow)).length;
  const onfreqs = new Set(DATA.filter(r=>isOnAir(r, curMin, dow)).map(r=>r.f)).size;""",
     """  const onRows = DATA.filter(r=>isOnAir(r, curMin, dow));
  const onair = onRows.length;
  const onfreqs = new Set(onRows.map(r=>r.f)).size;"""),
    # map view: don't build the (hidden) table at all
    ("""  // group by band when sorting by freq, else single table""",
     """  // 地图视图下列表是隐藏的，不必生成整张表格（切回列表时 showTab 会重新 render）
  if (mapActive){ MAP.build(rows); MAP.draw(); return; }

  // group by band when sorting by freq, else single table"""),
    ("""  content.innerHTML = html;

  if (mapActive){ MAP.build(rows); MAP.draw(); }
}""",
     """  content.innerHTML = html;
}"""),
    ("""      const on = isOnAir(r, curMin, dow);""",
     """      const on = liveOnly && isOnAir(r, curMin, dow);"""),
    # tabs: list is now rendered lazily, so render on every tab switch
    ("""  if (map){ MAP.resize(); render(); }""",
     """  if (map) MAP.resize();
  render();"""),
    # periodic refresh: skip while the page is in a background tab
    ("""  if (nowChk.checked){ const n = nowUTC();""",
     """  if (nowChk.checked && !document.hidden){ const n = nowUTC();"""),
    # map: coalesce redraws into one per animation frame
    ("""  function draw(){
    const W = cv.width / dpr, H = cv.height / dpr;
    ctx.clearRect(0, 0, W, H);""",
     """  // 每帧最多重绘一次：拖动/悬停/缩放时的多次 draw() 请求合并到下一帧
  let drawPending = false;
  function draw(){
    if (drawPending) return;
    drawPending = true;
    requestAnimationFrame(() => { drawPending = false; drawNow(); });
  }
  function drawNow(){
    const W = cv.width / dpr, H = cv.height / dpr;
    ctx.clearRect(0, 0, W, H);"""),
    # hideTip() already redraws; drop the duplicate draw() calls
    ("""      drag = {x: mx, y: my};
      hideTip(); draw();""",
     """      drag = {x: mx, y: my};
      hideTip();"""),
    ("""clampView(); drag={x:mx,y:my}; hideTip(); draw();""",
     """clampView(); drag={x:mx,y:my}; hideTip();"""),
    ("""    clampView(); hideTip(); draw();
  }""",
     """    clampView(); hideTip();
  }"""),
    # init: enter map view directly instead of building the table first and then rendering again
    ("""  render();

  applyNowLock();
  MAP.resize();
  showTab(true);   // 默认进入地图视图""",
     """  applyNowLock();
  showTab(true);   // 默认进入地图视图（内部会 resize + render）"""),
    # touch: add two-finger pinch zoom (canvas has touch-action:none, so the browser won't do it)
    ("""  // 触摸
  cv.addEventListener('touchstart', e => {
    if (e.touches.length === 1){ const [mx,my]=evtPos(e); drag={x:mx,y:my}; }
  }, {passive:true});
  cv.addEventListener('touchmove', e => {
    if (drag && e.touches.length===1){""",
     """  // 触摸：单指拖动，双指捏合缩放（两指中点移动时同时平移）
  let pinch = null;
  function pinchState(e){
    const r = cv.getBoundingClientRect();
    const a = e.touches[0], b = e.touches[1];
    return { x: (a.clientX + b.clientX)/2 - r.left, y: (a.clientY + b.clientY)/2 - r.top,
             d: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) };
  }
  cv.addEventListener('touchstart', e => {
    if (e.touches.length === 1){ const [mx,my]=evtPos(e); drag={x:mx,y:my}; pinch=null; }
    else if (e.touches.length === 2){ drag=null; pinch=pinchState(e); }
  }, {passive:true});
  cv.addEventListener('touchmove', e => {
    if (pinch && e.touches.length===2){
      e.preventDefault();
      const p = pinchState(e);
      if (p.d > 0 && pinch.d > 0){
        const W=cv.width/dpr, H=cv.height/dpr;
        const dLon=(p.x-pinch.x)*(view.lon1-view.lon0)/W;
        const dLat=(p.y-pinch.y)*(view.lat1-view.lat0)/H;
        view.lon0-=dLon; view.lon1-=dLon; view.lat1+=dLat; view.lat0+=dLat;
        zoom(pinch.d / p.d, p.x, p.y);   // 手指张开 → 放大
      }
      pinch = p;
    } else if (drag && e.touches.length===1){"""),
    ("""  cv.addEventListener('touchend', ()=>{ drag=null; });""",
     """  function touchEnd(e){
    pinch = null;
    // 双指抬起一指后，用剩下的手指继续拖动，避免画面跳动
    if (e.touches.length === 1){ const [mx,my]=evtPos(e); drag={x:mx,y:my}; } else drag=null;
  }
  cv.addEventListener('touchend', touchEnd);
  cv.addEventListener('touchcancel', touchEnd);"""),
]
for old, new in EDITS:
    n = code.count(old)
    assert n == 1, f'edit matched {n} times: {old[:60]!r}'
    code = code.replace(old, new)

head_extra = ('<meta name="description" content="HFCC B26 季全球短波广播频率查询：按 UTC 时间、语言、电台筛选当前可收听的频率，并在世界地图上查看发射方位与功率。">\n'
              '<meta name="theme-color" content="#0f1419">\n'
              '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E%F0%9F%93%BB%3C/text%3E%3C/svg%3E">\n')
assert html.count('<title>') == 1
out = html[:m.start()] + as_json_script('hfdata', packed) + as_json_script('hfland', land) \
    + m.group(1) + code + m.group(3) + html[m.end():]
out = out.replace('<title>', head_extra + '<title>', 1)
open(dst, 'w', encoding='utf-8').write(out)
print(f'{len(html.encode())} -> {len(out.encode())} bytes')
