# hfFreq — HF 短波频率查询

线上地址：**https://sw.yink.shop**（备用：https://muddy-dust-4d36.yangkang5303.workers.dev）

HFCC B26 季全球短波广播排程查询：按 UTC 时间、语言、电台筛选当前可收听的频率，并在世界地图上显示各发射台的方位角与功率。

## 部署方式

Cloudflare Worker `muddy-dust-4d36`，**纯静态资源**，没有服务端代码：`public/` 下的文件原样托管。自定义域名 `sw.yink.shop` 在 `wrangler.toml` 里配置。

```bash
cd ~/coding/web/hfFreq
npx wrangler@4 deploy --message "说明这次改了什么"
```

- 一定要在本目录运行。在主目录 `~` 下运行 wrangler 会生成 `~/.wrangler/`，之后 wrangler 会到那里找登录信息，表现为“Not logged in”。
- 部署后边缘缓存可能要十几秒才刷新，验证时可以加 `?v=随机数`。

查看版本 / 回滚：

```bash
npx wrangler@4 versions list
npx wrangler@4 rollback <version-id>
```

## 目录

| 路径 | 说明 |
|------|------|
| `public/index.html` | 主页（单文件：CSS + JS + 嵌入数据）。**以后改网站就改这个文件** |
| `public/exposure.html` | 语言周暴露量排行（静态页） |
| `public/country_exposure.html` | 发射国家周暴露量排行（静态页） |
| `tools/index.original.html` | 2026-10-26 优化前的线上原版（1.37 MB），留作参照 |
| `tools/build.py` | 把原版转换成现在 `public/index.html` 的一次性脚本 |
| `tools/verify.js` | 校验转换后的数据与原版逐条一致 |

## index.html 的数据格式

数据放在两个 `<script type="application/json">` 块里，页面加载时用 `JSON.parse` 读取，比直接写成 JS 字面量解析更快：

- `#hfdata`：频率表。`cols` 是字段名，`rows` 每行一条记录；台站名称和经纬度、语言名、国家名、机构名按代码存在 `loc` / `lang` / `adm` / `brc` 字典里，加载时还原成完整对象。因此页面代码看到的每条记录字段与原版相同（`f, s, e, site, lat, lon, langname, brcname, …`），另外多一个预先算好的搜索文本 `_q`。
- `#hfland`：Natural Earth 110m 陆地轮廓，只保留几何、坐标保留 2 位小数。

原版里没有被页面用到的 `ant`、`afrq`、`req`、`old` 四个字段已删除。

**换季更新数据**（比如 A27）：拿到新的完整记录数组（与原版 `const DATA = [...]` 同格式）后，可参照 `tools/build.py` 里打包 `packed` 的那段生成新的 `#hfdata` 块替换进去。注意 `site`/`lat`/`lon` 必须由 `loc` 唯一确定（其余三个字典同理），`build.py` 打包前应先确认这一点。

## 变更记录

- **2026-10-26 优化**：页面 1.37 MB → 485 KB；地图视图下不再生成隐藏的列表表格；首次加载只渲染一次；地图重绘合并到每帧一次；后台标签页跳过每 30 秒的刷新；增加 favicon、meta description。
- **2026-10-26 手机双指缩放**：画布设置了 `touch-action:none`（禁用了浏览器自带缩放），所以要自己实现：双指捏合以两指中点为中心缩放，同时可以平移；抬起一指后剩下的手指继续拖动。

## 待确认

- 两个排行页标题写的是 **A26**，主页是 **B26**，可能是笔误。
