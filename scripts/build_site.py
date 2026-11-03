#!/usr/bin/env python3
"""把一个「项目作品集」渲染成纯静态站点。

与 frontier-knowledge-base 的 build_site.py 同一套思路：
- 零依赖：不用 MkDocs / VitePress / Node，只用 Python 标准库。
- 唯一真相源是 data/projects.py，站点只是它的投影。
- 产物是纯静态 HTML，克隆下来双击 index.html 就能看，换托管不用改代码。

站点本身也是「零依赖」的，这不是巧合——这个账号的主张是零依赖，
门面没理由破自己的例。
"""
import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


import app_assets
import insight
import overlay
import pages
from util import DATA, ROOT, attr, days_between, esc, human_size, iso_now, rfc822, slugify, source_stamp, write_json

OUT = ROOT / "site"
INSTALL_JS = app_assets.INSTALL_JS

GROUPS = [
    ("on-device-ai", "端侧 AI", "把模型塞进手机：本地推理、不上传、不联网也能用"),
    ("tools", "随身工具", "用完就走的实用小工具，装完即用"),
    ("media", "阅读与媒体", "书、音乐、声音——本地优先的消费与管理"),
    ("services", "服务与基础设施", "把设备变成服务端，或者让 API 更便宜"),
]

SITE = {
    "name": "ice 工坊",
    "domain": "icesuite.eu.org",
    "tagline": "零依赖 · 离线优先 · 极小体积",
    "author": "ice-wocker",
    "author_url": "https://github.com/ice-wocker",
    "desc": "ice-wocker 的原创作品集，全部零第三方依赖、离线可用、体积可验证。",
    # base_url 只是一份**兜底**：真实值来自 data/projects.py。这里留着是为了
    # 「只跑 build_site.py 也能出绝对 URL」——canonical / og:url / sitemap
    # 都必须是绝对地址，缺了它们分享出去的卡片就是白板。
    "base_url": "https://ice-wocker.github.io/icesuite",
}

STATUS_LABEL = {
    "mature": ("稳定", "ok"),
    "active": ("迭代中", "info"),
    "beta":  ("预研", "warn"),
}


def load():
    """注册表 + 手写叠加层 → 项目清单。

    合并规则住在 overlay.py —— build 与 check 共用同一份，
    否则「页面上的东西和清单一致」这件事没法真的校验（两边各算一遍必然漂移）。
    """
    model = overlay.load()
    model["generated_at"] = _registry_generated_at()
    return model["site"], model["groups"], model["projects"], model["mirrors"], model


def _registry_generated_at() -> str:
    from util import read_json
    payload = read_json(DATA / "registry.json", {}) or {}
    return payload.get("generated_at") or ""


CSS = """
/* 主题变量：三档（auto/light/dark）在 <html data-theme> 上，不是媒体查询里。
   ------------
   之前只有一套深色配色，<meta name="color-scheme"> 却写着 "dark light" ——
   等于对浏览器说「两种都支持」，实际只有一种。浅色系统用户看到的是深色票，
   而地址栏 / 滚动条却按浅色画，视觉上是断的。
   现在 :root 是深色底（默认，也是打印外最常被分享的样子），
   [data-theme=light] 与 prefers-color-scheme: light + theme=auto 两处覆盖。
   变量名保持不变，所以下面所有组件样式一处都不用改。 */
:root{--bg:#0b0f14;--panel:#131a22;--panel2:#0f151c;--border:#243040;--fg:#e6edf3;
--muted:#8b98a8;--accent:#5ad1ff;--accent2:#7ee787;--warn:#ffb454;
--shadow:0 12px 40px rgba(0,0,0,.5);--markbg:#463300;--markfg:#ffd76e}
html[data-theme=light]{--bg:#f6f8fa;--panel:#ffffff;--panel2:#eef2f6;--border:#d6dee6;
--fg:#1b2430;--muted:#5b6a7a;--accent:#0b74b8;--accent2:#1a7f45;--warn:#9a5b00;
--shadow:0 12px 40px rgba(20,30,45,.14);--markbg:#ffe89a;--markfg:#4a3600}
@media (prefers-color-scheme:light){
html[data-theme=auto]{--bg:#f6f8fa;--panel:#ffffff;--panel2:#eef2f6;--border:#d6dee6;
--fg:#1b2430;--muted:#5b6a7a;--accent:#0b74b8;--accent2:#1a7f45;--warn:#9a5b00;
--shadow:0 12px 40px rgba(20,30,45,.14);--markbg:#ffe89a;--markfg:#4a3600}
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.72 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:940px;margin:0 auto;padding:0 20px}
header.top{position:sticky;top:0;z-index:20;background:rgba(11,15,20,.9);backdrop-filter:blur(10px);
border-bottom:1px solid var(--border)}
header.top .wrap{display:flex;align-items:center;gap:16px;height:58px}
.brand{font-weight:700;white-space:nowrap;letter-spacing:.2px}
.brand em{font-style:normal;color:var(--accent2)}
header.top nav{margin-left:auto;display:flex;gap:16px;font-size:14px}
header.top nav a{color:var(--muted)}
header.top nav a:hover{color:var(--fg);text-decoration:none}
main{padding:34px 0 72px}
h1{font-size:1.85rem;line-height:1.3;margin:.1em 0 .5em;letter-spacing:-.2px}
h2{font-size:1.18rem;margin:2.2em 0 .7em;letter-spacing:-.1px}
h3{font-size:1rem;margin:1.5em 0 .4em}
p{color:#cbd5e1}
.hero{padding:14px 0 6px}
.hero .kicker{color:var(--accent);font-size:.85rem;letter-spacing:1.6px;text-transform:uppercase;margin:0 0 .5em}
.hero h1{font-size:2.1rem}
.hero p.lead{color:var(--muted);font-size:1.02rem;margin:0 0 1.4em;max-width:60ch}
.stats{display:flex;gap:26px;flex-wrap:wrap;margin:1.4em 0 1.8em}
.stats div{color:var(--muted);font-size:.85rem}
.stats b{display:block;color:var(--fg);font-size:1.45rem;font-weight:700;line-height:1.3}
.group{margin:0 0 2.4em}
.group > .gh{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;
padding-bottom:.5em;border-bottom:1px solid var(--border);margin-bottom:1em}
.group > .gh h2{margin:0;font-size:1.2rem}
.group > .gh span{color:var(--muted);font-size:.86rem}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;
grid-auto-rows:max-content;align-items:start}
/* 整卡可点：用一个绝对定位的空 <a> 铺满卡片，而不是把整张卡片做成 <a>。
   后者会和卡片里的标签链接形成 <a> 嵌套 <a>，HTML 解析器会把内层提到外层之外，
   卡片当场被拆碎（真发生过，见 CHANGELOG）。 */
.card{position:relative}
.cardhit{position:absolute;inset:0;z-index:1;border-radius:12px}
.cardhit:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.card .t a{color:var(--fg)}
.card .techrow,.card .badges{position:relative;z-index:2}
.card .techrow a,.card .badges a{position:relative;z-index:3}
/* 注意：.cards 是容器、.card 是卡片。两者只差一个 s，但 .card 的
   display:block 一旦被 .cards 的 display:grid 抢占（同优先级下后出现者赢），
   卡片内的每个子元素都会变成一个网格项——页面上就会看到「标签散成一列方块」。
   所以这里把 .card 的选择器写得更具体（.cards > .card），并且显式定死
   容器只做「一列流式布局」，避免 grid 把子元素也当项。 */
.cards > .card{display:flex;flex-direction:column}
.card{padding:16px 18px;background:var(--panel);border:1px solid var(--border);
border-radius:12px;color:var(--fg);transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--accent);transform:translateY(-2px)}
.card:hover .t a{color:var(--accent)}
.card .p{margin-bottom:auto}
.card .t{font-weight:700;margin-bottom:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.card .p{color:var(--muted);font-size:.86rem;line-height:1.6}
.card .p b{color:var(--accent2);font-weight:600}
.badges{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.badge{font-size:.72rem;padding:2px 8px;border-radius:20px;border:1px solid var(--border);
color:var(--muted);background:var(--panel2)}
.badge.ok{color:var(--accent2);border-color:#1d3f2a}
.badge.info{color:var(--accent);border-color:#19405a}
.badge.warn{color:var(--warn);border-color:#4a3a1c}
.searchbox{width:100%;padding:12px 15px;border-radius:12px;border:1px solid var(--border);
background:var(--panel);color:var(--fg);font-size:1rem}
.searchbox:focus{outline:none;border-color:var(--accent)}
#results{margin-top:12px}
.hit{display:block;padding:11px 14px;border:1px solid var(--border);border-radius:10px;
margin-bottom:8px;color:var(--fg);background:var(--panel)}
.hit:hover{border-color:var(--accent);text-decoration:none}
.hit .d{color:var(--muted);font-size:.8rem;margin-top:2px}
.hit mark{background:#463300;color:#ffd76e;border-radius:3px;padding:0 2px}
.crumb{font-size:.86rem;color:var(--muted);margin-bottom:1.1em}
.crumb a{color:var(--muted)}
.phead{padding-bottom:1.2em;border-bottom:1px solid var(--border);margin-bottom:1.6em}
.phead .sub{color:var(--muted);font-size:.95rem;margin:.5em 0 1em}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:1.1em}
.btn{display:inline-flex;align-items:center;gap:7px;padding:9px 16px;border-radius:9px;
border:1px solid var(--border);background:var(--panel);color:var(--fg);font-size:.9rem;font-weight:600}
.btn:hover{border-color:var(--accent);text-decoration:none}
.btn.primary{background:#0f3a4c;border-color:#1b5c78;color:#d3f3ff}
.btn.primary:hover{background:#134a61}
.metrics{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;margin:1.2em 0 0}
.metrics div{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:11px 14px}
.metrics b{display:block;font-size:1.08rem;color:var(--fg)}
.metrics span{color:var(--muted);font-size:.78rem}

/* 「一次下齐」那块：标题、说明、按钮各占一行。
   原来三者挤在一行里，说明文字被拆得四分五裂（窄屏更糟）*/
.update-item{display:block;margin:.45em 0 .8em;line-height:1.75}
/* 说明里的强调保持行内。上一版因为 `.bulk .row span{display:block}` 把它们
   全顶成了独立段落，一句话被拆成五个自然段——手机上尤其难看 */
.bulk .row span.update-item b{display:inline}
/* 校验值：等宽、可选中、窄屏横向滚动而不是折行——折行的十六进制串没法选中复制 */
pre.sha{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px;overflow-x:auto;margin:.6em 0}
pre.sha code{font-size:.82rem;white-space:pre;color:var(--fg)}
/* 更新记录：默认收起。展开的是「我想知道这版改了什么」的人，不是所有人 */
.relnotes{margin:.4em 0 1.4em}
details.rel{background:var(--panel);border:1px solid var(--border);border-radius:10px;margin:.5em 0;padding:0 14px}
details.rel>summary{cursor:pointer;padding:11px 0;list-style:none}
details.rel>summary::-webkit-details-marker{display:none}
details.rel>summary::before{content:"▸ ";color:var(--muted)}
details.rel[open]>summary::before{content:"▾ "}
details.rel h4{margin:.9em 0 .3em;font-size:.95rem}
details.rel p,details.rel li{font-size:.88rem;color:var(--muted)}
details.rel pre{overflow-x:auto;background:#0f151c;border-radius:8px;padding:10px}
/* 「自动收录」这类标记要能一眼看出语气差别，不能和「稳定」混成同一颗徽章 */
.badge.auto{opacity:.75;border-style:dashed}

ul.hl{list-style:none;padding:0;margin:1em 0}
ul.hl li{padding:12px 16px;background:var(--panel);border:1px solid var(--border);
border-radius:10px;margin-bottom:9px}
ul.hl li b{display:block;color:var(--accent2);margin-bottom:3px;font-size:.95rem}
ul.hl li span{color:var(--muted);font-size:.88rem;line-height:1.65}
.note{margin:1.2em 0;padding:14px 18px;border-left:3px solid var(--warn);
background:var(--panel);border-radius:0 10px 10px 0}
.note b{color:var(--warn)}
.note ul{margin:.6em 0 0;padding-left:1.2em}
.note li{color:var(--muted);font-size:.88rem;margin:.35em 0}
.tech{display:flex;gap:7px;flex-wrap:wrap;margin-top:1em}
footer{border-top:1px solid var(--border);color:var(--muted);font-size:.85rem;padding:26px 0 46px}
footer a{color:var(--muted)}
.pager{display:flex;justify-content:space-between;gap:12px;margin-top:3em;
padding-top:1.4em;border-top:1px solid var(--border);font-size:.9rem}
.pager a{max-width:47%}
/* ---- 可访问性与主题 ---- */
.skip{position:absolute;left:-9999px;top:0;z-index:99;padding:10px 16px;
background:var(--panel);border:1px solid var(--accent);border-radius:0 0 10px 0;color:var(--fg)}
.skip:focus{left:0}
.brand{color:var(--fg)}
.brand:hover{text-decoration:none;color:var(--accent)}
.themebtn{background:var(--panel);border:1px solid var(--border);color:var(--muted);
border-radius:8px;width:32px;height:32px;font-size:15px;line-height:1;cursor:pointer;
font-family:inherit;padding:0;display:inline-flex;align-items:center;justify-content:center}
.themebtn:hover{color:var(--fg);border-color:var(--accent)}
/* 焦点可见：键盘用户靠它找位置，鼠标用户看不到，所以不算视觉噪音 */
a:focus-visible,button:focus-visible,.card:focus-visible,.hit:focus-visible{
outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
/* 进场动效。
   ------------
   .rv 只负责「隐藏」，而隐藏的前提是 <html class="js"> 由内联脚本挂上。
   上一版的做法是「JS 给卡片加 .rv」，看起来一样，但差一个致命细节：
   如果卡片在视口内、而 IntersectionObserver 的回调因为任何原因没跑到
   （后台标签页、无头浏览器、某些 WebView），元素会**永远停在 opacity:0** ——
   页面白得像挂了，控制台一声不响。宁可没有动画，也不能让内容依赖 JS 才可见。
   现在的兜底：<html class="js"> 只在脚本确实执行时出现，而 .rv 的初始态
   另外带了 1.2s 的 CSS 动画兜底，即使回调不来，元素也会自己淡入。 */
/* 兜底只管「JS 回调没来」的情况，且**不依赖滚动**：动画在元素被渲染时
   就开始计时。1.2s 后任何还没进过视口的卡片也会自己显现。
   宁可让淡入动效偶尔「提前」发生，也不能让内容停在不可见状态。 */
.reveal{opacity:1;transform:none}
html.js .reveal.rv{opacity:0;transform:translateY(10px);transition:opacity .35s,transform .35s;
animation:rvfallback .01s 1.2s forwards}
html.js .reveal.rv.on{opacity:1;transform:none;animation:none}
@keyframes rvfallback{to{opacity:1;transform:none}}
/* ---- v3：新增页面（最新 / 时间线 / 对比 / 集合 / 数据）----
   全部复用上面的变量，不引入新配色 —— 一个站点出现第二套色板，
   通常意味着没人再统一维护它。 */
.entrygrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;margin:1.4em 0 2.4em}
.entry{display:flex;flex-direction:column;gap:4px;padding:13px 15px;border-radius:12px;
border:1px solid var(--border);background:var(--panel);color:var(--fg)}
.entry:hover{border-color:var(--accent);text-decoration:none;transform:translateY(-1px)}
.entry b{font-size:.95rem}
.entry span{color:var(--muted);font-size:.8rem;line-height:1.55}
.netbar{background:var(--warn);color:#1b1400;font-size:.85rem;padding:7px 16px;text-align:center}
.installbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 20px;
background:var(--panel2);border-bottom:1px solid var(--border);font-size:.88rem;color:var(--muted)}
.installbar .btn.small{padding:6px 12px;font-size:.84rem}
.btn.ghost{background:transparent;color:var(--muted)}
.tlmonth{margin:2.2em 0 .5em;font-size:1.05rem}
.latestlist{list-style:none;padding:0;margin:0 0 1em}
.latestlist li{padding:8px 0;border-bottom:1px dashed var(--border);color:var(--muted);font-size:.92rem}
.latestlist li .ver{color:var(--accent);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88rem}
.tlrow{border-left:2px solid var(--border);padding:0 0 0 16px;margin:0 0 1.4em;position:relative}
.tlrow:before{content:"";position:absolute;left:-5px;top:.55em;width:8px;height:8px;border-radius:50%;
background:var(--accent)}
.tlhead{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.tlhead b{font-size:.95rem}
.tlbar{color:var(--accent);letter-spacing:1px;font-size:.8rem;overflow:hidden;max-width:40%}
.tlrow ul{list-style:none;padding:0;margin:.5em 0 0}
.tlrow li{font-size:.88rem;color:var(--muted);padding:3px 0}
.tlrow .day{color:var(--muted);font-family:ui-monospace,monospace;font-size:.82rem}
.tlrow .ver{color:var(--accent);font-family:ui-monospace,monospace;font-size:.84rem}
.tablewrap{overflow-x:auto;margin:1em 0 1.8em;border:1px solid var(--border);border-radius:12px}
/* table-layout:fixed + 列宽由 colgroup 给死。
   默认的 auto 布局按内容分配宽度：一列长一点的日期就能把别的列挤到溢出。
   定死之后「窄屏会不会溢出」是算出来的，不是碰运气。 */
table.cmp{width:100%;border-collapse:collapse;font-size:.86rem;table-layout:fixed}
table.cmp th,table.cmp td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border);vertical-align:top}
table.cmp thead th{background:var(--panel2);color:var(--muted);font-weight:600;white-space:nowrap}
table.cmp th.sortable{cursor:pointer;user-select:none}
table.cmp th.sortable:hover{color:var(--fg)}
table.cmp th[data-dir=asc]:after{content:" ↑";color:var(--accent)}
table.cmp th[data-dir=desc]:after{content:" ↓";color:var(--accent)}
table.cmp td.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.82rem;white-space:nowrap}
/* 第一列是「项目」，其余都是短值。给第一列定个下限，否则在 390px 上
   浏览器会把「60 字的中文简介」压成每行 4 个字的窄条，而版本号那一列占着
   大把空白 —— 表格宽度分配是按内容算的，不看语义。 */
table.cmp td:first-child,table.cmp th:first-child{width:auto}
table.cmp td:first-child .fine{display:block;margin-top:4px;color:var(--muted);font-size:.76rem;
line-height:1.5;max-width:26ch}
/* 窄屏：表格改成「只留关键列」。ABI 和标签对手机上的读者信息量最低，
   而表格一旦横向溢出，第一列就会被推到屏幕外，读者看不到项目名。 */
@media(max-width:640px){
table.cmp td:first-child,table.cmp th:first-child{width:30%}
table.cmp th:nth-child(5),table.cmp td:nth-child(5),
table.cmp th:nth-child(7),table.cmp td:nth-child(7){display:none}
table.cmp td:first-child .fine{display:none}
table.cmp th,table.cmp td{padding:9px 6px;font-size:.8rem}
/* 「Android 8.0+」比列宽长 2 个字符时会被切掉末尾（读起来像「Android 8.0」
   或更糟「Android 8.」）。方法：拆成「Android」和版本号两行，宽度立刻够。 */
table.cmp td:nth-child(4){white-space:normal;line-height:1.35}
/* 日期同样会超：「2026-11-02」是 10 个等宽字符，在 390px 屏上放不下。
   日期可以折行（年月 / 日之间本来就该断），所以允许 normal。 */
table.cmp td:nth-child(6),table.cmp th:nth-child(6){white-space:normal}
}
.cmpset{margin:0 0 2.6em}
.rule{margin:.3em 0 .9em;font-size:.82rem;color:var(--muted)}
.rule code{background:var(--panel2);border:1px solid var(--border);border-radius:6px;padding:1px 6px}
.bars{display:flex;align-items:flex-end;gap:8px;height:150px;margin:1em 0 .4em;
padding:0 0 0 2px;border-bottom:1px solid var(--border)}
.mbar{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}
.mbar i{display:block;width:100%;max-width:46px;background:linear-gradient(180deg,var(--accent),#1b5c78);
border-radius:4px 4px 0 0;min-height:3px}
.mbar span{color:var(--muted);font-size:.72rem;margin-top:5px}
.lbar{display:inline-block;height:8px;background:var(--accent);border-radius:4px;min-width:2px}
ul.hl.health li b{color:var(--fg)}
ul.hl.health li span{display:block;margin-top:4px}
ul.hl.health .badge{float:right;margin-left:8px}
.relgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:.8em 0 1em}
.relcard{display:flex;flex-direction:column;gap:3px;padding:12px 14px;border:1px solid var(--border);
border-radius:10px;background:var(--panel);color:var(--fg)}
.relcard:hover{border-color:var(--accent);text-decoration:none}
.relcard b{font-size:.92rem}
.relcard span{color:var(--muted);font-size:.8rem;line-height:1.5}
header.top nav a[aria-current=page]{color:var(--fg);font-weight:600}
.ver{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
@media print{.reveal{opacity:1!important;transform:none!important;animation:none!important}}
.pill{display:inline-block;padding:5px 12px;border-radius:20px;border:1px solid var(--border);
background:var(--panel);color:var(--fg);font-size:.85rem;margin:0 6px 6px 0}
.pill:hover{border-color:var(--accent);text-decoration:none}
.pill b{color:var(--muted);font-weight:400;font-size:.85em;margin-left:5px}
.pill.on{background:#0f3a4c;border-color:#1b5c78;color:#d3f3ff}
.pill.on b{color:#9fd8f0}
.filterbar{margin:1.1em 0 1.4em}
.filterbar .pill{cursor:pointer;font-family:inherit}
.empty{color:var(--muted);padding:18px;border:1px dashed var(--border);border-radius:10px}
.chipmini{gap:6px;flex-wrap:wrap}
.chipset,.techrow{display:flex;gap:6px;flex-wrap:wrap}
.techrow{margin-top:9px;padding-top:8px;border-top:1px dashed var(--border)}
.chipset{margin-top:8px}
.chipset a,.techrow a{font-size:.76rem;padding:2px 9px;border-radius:20px;border:1px solid var(--border);
color:var(--muted);background:var(--panel2)}
.chipset a:hover,.techrow a:hover{color:var(--fg);border-color:var(--accent);text-decoration:none}
.chipset span,.techrow span{font-size:.76rem;padding:2px 9px;border-radius:20px;border:1px dashed var(--border);
color:var(--muted);background:transparent}
.indexgroup{margin:1.6em 0 2.2em}
.indexgroup h2{margin:0 0 .6em}
.indexgroup ul{margin:0;padding-left:1.1em;color:var(--muted);font-size:.9rem}
.indexgroup li{margin:.3em 0}
.indexgroup li a{color:var(--accent)}
.fine{color:var(--muted);font-size:.78rem;line-height:1.7}
footer p{margin:.4em 0}
/* 减少动效：放在最后，让它的 !important 覆盖前面所有 transition/animation。
   上一版把它插在文件开头附近，却没有闭合的大括号——结果从这条规则之后
   整份样式表全部失效，页面变成没有任何样式的纯文本，而浏览器不报错、
   自检也查不出来（文件存在、HTTP 200、能解析出前 6 条规则）。
   这正是「构建成功但站点坏掉」的典型：所以现在有一条守卫在做括号平衡检查。 */
@media (prefers-reduced-motion:reduce){
html{scroll-behavior:auto}
*,*::before,*::after{animation-duration:.001ms!important;transition-duration:.001ms!important}
}
@media(max-width:640px){h1,.hero h1{font-size:1.5rem}.wrap{padding:0 16px}
/* 窄屏只留品牌与主题按钮：导航挤在一起会换行、且 GitHub 链接对移动端没意义。
   标签索引页仍然可以从首页标签行与页脚进入。 */
header.top nav a{display:none}
header.top nav{display:flex;gap:8px}
header.top nav{gap:10px}
.cols{grid-template-columns:1fr!important}.stats{gap:18px}}
/* ---- 应用商店 ---- */
.storehead{display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:.4em}
.storehead h1{margin:0}
.storehead .tag{color:var(--muted);font-size:.9rem}
.bulk{margin:1.2em 0 2em;padding:18px 20px;background:var(--panel);border:1px solid var(--border);
border-radius:14px}
.bulk .row{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.bulk .row .grow{flex:1;min-width:200px}
.bulk b{display:block;font-size:1.02rem;margin-bottom:3px}
.bulk span{color:var(--muted);font-size:.86rem;line-height:1.6}
.bulk .tot{color:var(--accent2);font-weight:700}
table.mirrors{width:100%;border-collapse:collapse;margin:1em 0;font-size:.86rem}
table.mirrors th,table.mirrors td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border)}
table.mirrors th{color:var(--muted);font-weight:600}
table.mirrors td code{color:var(--accent);font-size:.85em;word-break:break-all}
table.mirrors tr:last-child td{border-bottom:none}
.srcinfo{margin-top:.7em;color:var(--muted);font-size:.86rem}
.srcinfo b{color:var(--accent2)}
.srcbar-wrap{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:1em 0 1.4em}
.srcbar{flex:1 1 22ch;min-width:0;padding:10px 14px;border:1px solid var(--border);
border-radius:10px;background:var(--panel);font-size:.88rem;color:var(--muted)}
.srcbar b{color:var(--accent2);font-weight:600}
.btn.small{padding:7px 14px;font-size:.85rem;white-space:nowrap;flex:0 0 auto}
.applist{display:flex;flex-direction:column;gap:10px;margin:0 0 2.4em}
.app{display:grid;grid-template-columns:40px 1fr auto;gap:14px;align-items:center;
padding:14px 16px;background:var(--panel);border:1px solid var(--border);border-radius:12px}
.app:hover{border-color:#2f4a63}
.app .ico{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;
justify-content:center;font-size:20px;background:var(--panel2);border:1px solid var(--border)}
.app .nm{font-weight:700;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.app .nm a{color:var(--fg)}
.app .meta{color:var(--muted);font-size:.8rem;margin-top:3px;
display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.app .meta .dot{opacity:.4}
.app .meta .ver{color:var(--accent2)}
.app .pitch{color:var(--muted);font-size:.86rem;margin-top:5px;line-height:1.6}
.app .pitch b{color:var(--accent2);font-weight:600}
.app .act{display:flex;gap:8px;align-items:center}
.app .act .btn{padding:7px 14px;font-size:.85rem;white-space:nowrap}
.app.none{opacity:.9}
.app.none .ico{opacity:.5}
.queue{position:fixed;left:50%;transform:translateX(-50%);bottom:18px;z-index:60;
width:min(560px,calc(100vw - 24px));background:var(--panel);border:1px solid var(--border);
border-radius:14px;padding:14px 16px;box-shadow:0 12px 40px rgba(0,0,0,.5);display:none}
.queue.on{display:block}
.queue .qh{display:flex;align-items:center;gap:10px;font-size:.9rem;font-weight:600}
.queue .qh .n{margin-left:auto;color:var(--muted);font-weight:400;font-size:.82rem}
.queue .bar{height:5px;border-radius:3px;background:#1d2735;margin:10px 0 8px;overflow:hidden}
.queue .bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .25s}
.queue .qn{color:var(--muted);font-size:.82rem}
.queue .qx{background:none;border:1px solid var(--border);color:var(--muted);
border-radius:7px;padding:3px 9px;font-size:.78rem;cursor:pointer;font-family:inherit}
.queue .qx:hover{color:var(--fg);border-color:var(--accent)}
.help{margin:1.4em 0;padding:14px 18px;background:var(--panel);border:1px solid var(--border);
border-radius:12px}
.help summary{cursor:pointer;font-weight:600;font-size:.93rem}
.help ol{color:var(--muted);font-size:.87rem;line-height:1.8;padding-left:1.3em;margin:.8em 0 0}
.help code{background:var(--panel2);border:1px solid var(--border);border-radius:4px;padding:1px 5px;font-size:.85em}
@media(max-width:640px){
.app{grid-template-columns:34px 1fr;gap:12px}
.app .act{grid-column:1/-1}
.app .act .btn{flex:1;justify-content:center}
.app .ico{width:34px;height:34px;font-size:17px;border-radius:9px}
}
"""

SEARCH_JS = r"""
/* 站内搜索：构建时预生成 search.json，运行时纯前端过滤。
   ------------
   三处刻意设计：

   ① **必须能降级。** fetch 失败（本地 file:// 打开、静态托管漏了文件、
      离线且没缓存）时，输入框不能变成一个「输什么都没反应」的死控件。
      所以失败时提示「搜索索引没加载到」，并给出 tags.html 作为兜底入口。
      纯静态站最常见的翻车就是这种「看起来有搜索，其实一直空结果」。

   ② **键盘可用。** 上下键移动、回车打开、Esc 清空——搜索结果不是纯鼠标控件。
      高亮项用 aria-selected 表达，不是只靠颜色。

   ③ **中文按字符切分。** 英文按空格分词天经地义，中文没有空格：
      「本地推理」这个词用户可能只打「推理」。所以中文查询额外用
      二元切分（bigram）生成候选，再对结果做包含匹配。
      这不是搜索引擎，但比「整串不匹配就零结果」好得多。 */
(function(){
  var box=document.getElementById('q'), out=document.getElementById('results');
  if(!box||!out) return;
  var data=null,timer=null,idx=-1,hits=[],lang=(document.documentElement.lang||'zh').indexOf('zh')===0;

  fetch('__BASE__search.json').then(function(r){return r.json()}).then(function(j){
    data=j;
  }).catch(function(){
    out.innerHTML='<p class="empty">'+(lang
      ? '搜索索引没能加载（可能离线，或 search.json 缺失）。'
      : 'Search index failed to load.')+
      (lang?'可以改从 <a href="__BASE__tags.html">标签索引</a> 浏览。':'')
      +'</p>';
  });

  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}

  /* 中文没有词边界：纯 indexOf('推理') 能中，但纯 indexOf('本地推理') 就漏。
     所以把查询串按中文段切成二元组，任一片命中即算候选。 */
  function terms(kw){
    var raw = kw.trim().toLowerCase();
    if(!raw) return [];
    var out = raw.split(/\s+/).filter(Boolean);
    var cjk = raw.match(/[\u4e00-\u9fa5]+/g) || [];
    for(var i=0;i<cjk.length;i++){
      var t = cjk[i];
      if(t.length <= 2){ out.push(t); continue; }
      for(var k=0;k+2<=t.length;k++) out.push(t.substr(k,2));
    }
    return out.filter(function(v,n,a){return a.indexOf(v)===n});
  }

  function score(hay, ts, title){
    var s=0;
    for(var i=0;i<ts.length;i++){
      var at = hay.indexOf(ts[i]);
      if(at < 0) return -1;
      s += (title.indexOf(ts[i]) >= 0) ? 50 : 1;
    }
    return s;
  }

  function render(kw){
    idx=-1;
    if(!data) return;
    var ts = terms(kw);
    if(!ts.length){ out.innerHTML=''; hits=[]; return; }
    hits = [];
    for(var i=0;i<data.length;i++){
      var d=data[i];
      var hay=(d.title+' '+d.summary+' '+d.text+' '+d.tags.join(' ')).toLowerCase();
      var sc = score(hay, ts, d.title.toLowerCase());
      if(sc >= 0) hits.push([sc, d]);
    }
    hits.sort(function(a,b){return b[0]-a[0]});
    hits = hits.slice(0,30);
    if(!hits.length){
      out.innerHTML='<p class="empty">'+(lang?'没有匹配的项目。':'No matching projects.')+'</p>';
      return;
    }
    out.innerHTML=hits.map(function(h){
      var d=h[1],s=d.summary||'';
      for(var t=0;t<ts.length;t++){
        var re = new RegExp('(' + ts[t].replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
        s=s.replace(re,'<mark>$1</mark>');
      }
      return '<a class="hit" href="'+esc(d.url)+'" role="option" aria-selected="false">'+
             '<div>'+esc(d.title)+'</div>'+
             '<div class="d">'+esc(d.group)+' · '+esc(d.tags.join(' / '))+'</div>'+
             '<div class="d">'+s+'</div></a>';
    }).join('');
    out.setAttribute('role','listbox');
  }

  function move(step){
    var items = out.querySelectorAll('.hit');
    if(!items.length) return;
    if(idx>=0 && items[idx]) items[idx].setAttribute('aria-selected','false');
    idx = (idx + step + items.length) % items.length;
    items[idx].setAttribute('aria-selected','true');
    items[idx].scrollIntoView({block:'nearest'});
  }

  box.addEventListener('input',function(){
    clearTimeout(timer);
    timer=setTimeout(function(){render(box.value)},120);
  });
  /* 键盘：上下键在结果间移动，回车打开，Esc 清空。
     没有这一段时，搜索结果对键盘用户等于不存在。 */
  box.addEventListener('keydown',function(e){
    if(e.key==='ArrowDown'){ e.preventDefault(); move(1); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); move(-1); }
    else if(e.key==='Escape'){ box.value=''; render(''); }
    else if(e.key==='Enter'){
      var el = idx>=0 ? out.querySelectorAll('.hit')[idx] : out.querySelector('.hit');
      if(el){ window.location.href = el.getAttribute('href'); }
    }
  });
})();
"""


STORE_JS = r"""
/* ============================================================================
   智能下载 · 按地区选源 + 并行建连
   ----------------------------------------------------------------------------
   要解决两件事：①「从哪下」（源选得对不对）②「怎么下」（建连等得冤不冤）。
   两件事的做法都得有实测依据，而不是「多线程一定快」「镜像一定比官方快」这种直觉。

   ── 关于「怎么下」──

   ① 每个 GitHub 连接的吞吐是**固定**的，多开连接不增加总带宽。
      同一个 58.3 MB 的包，开 1 / 2 / 4 条并发连接，总吞吐都是 ~6.2 MB/s。
      → 所以**不做「多线程下载大文件」**。没有收益，写上去只是好看。

   ② 但单个连接的快慢严重依赖文件大小：
        58.3 MB（iceScribe）  2.4 MB/s
         7.8 MB（ModelScope） 2.1 MB/s
         0.3 MB（MusicFusion）1.3 MB/s
        0.07 MB（KayaGo）     0.78 MB/s
      小包慢在建连（TTFB 0.3~1.3s），不是慢在带宽。
      → **并行发起多个小包有真实收益**：总吞吐是各连接之和，而不是把 N 次
        建连的等待串起来。这是本页唯一站得住的「怎么下」优化。

   ── 关于「从哪下」：为什么是按地区选，不是按测速选 ──

   ③ 直连 GitHub 的体验是**按地区两极分化**的，而且这个差异是**稳定的**：
      大陆普遍几百 KB/s 甚至断流，海外接近满速。稳定差异可以在本地推断，
      不需要发任何探测请求。

      反过来，镜像之间快慢才是随机的（实测差 50 倍以上，5.9 MB/s ↔ 0.09 MB/s），
      那部分**没有可靠的本地信号**，所以留给用户手动切，不猜。

   ④ 那为什么不用「实测速度自动选源」？因为做过，**而且是假的**：
      最初用 fetch + Range 并发探测各候选，结果**四个候选一个都读不到数据**。
      理由是 CORS：GitHub Release 会 302 到 release-assets.githubusercontent.com，
      而那一跳**不带 Access-Control-Allow-Origin**；三个反代同样不带。
      浏览器读不到响应字节数，计时恒为 0。
      更糟的是它**看起来能用**：探针全失败会悄悄退回官方、页面照常下完，
      没有任何报错——用户不会知道那个「智能选源」从来没生效过。
      所以这里的判断**只用本地信号，一个网络请求都不发**，check_site.py 里还有
      一条守卫禁止 fetch 出现在这个脚本里。

   ⑤ 地区信号（全部本地、零请求）：
        Intl.DateTimeFormat().resolvedOptions().timeZone   主要依据
        navigator.language / languages                     辅助
      命中「大陆时区/语言/地区」→ 判定直连大概率很慢 → 默认启用加速源；
      否则默认官方直连（海外直连本来就不慢，套反代只是多一跳）。

      这里**刻意不看 navigator.connection.effectiveType**。曾经加过一条
      「2g/3g 也走加速」，实测有问题：headless Chromium 会随机把 effectiveType
      报成 3g（同一个 Tokyo / ja-JP 上下文，5 次里 1 次报 3g），于是加速被误开。
      更要紧的是这个信号**语义就不对**——它说的是「我的链路慢」，不是
      「我到 GitHub 远」。两者不是一回事：慢链路上反代同样慢，套一层只是多一跳。
      地区信号才是那个稳定、且指向「距 GitHub 远近」的量。

   ⑥ 「走了第三方」这件事必须**看得见**：顶部有一行状态显示当前用哪个源，
      一点就能切换，选择存在 localStorage。加速源打不开时会**显式回退**到官方
      并在界面上说明，不静默降级。默认开加速的前提，是它完全透明。
   ============================================================================ */
(function(){
  var CFG = window.__DL || {};
  var MIRRORS = CFG.mirrors || [];
  var P = CFG.params || {};
  var MAX_PARALLEL = 5;
  var LSKEY = 'icesuite.dlsrc';

  var box = document.getElementById('bulk');
  if(!box) return;

  function byId(id){
    for(var i=0;i<MIRRORS.length;i++) if(MIRRORS[i].id===id) return MIRRORS[i];
    return null;
  }
  function direct(){ return byId('direct'); }
  function accelerators(){
    return MIRRORS.filter(function(m){ return m.role==='accelerator' && m.prefix; });
  }
  function accelerate(url, m){
    if(!m || !m.prefix) return url;      // 空前缀 = 官方直连，原样返回
    return m.prefix + url;
  }

  /* ── 地区判断：纯本地计算，不发请求 ── */
  function slowDirect(){
    try{
      var tz='', langs=[], reg='';
      if(window.Intl && Intl.DateTimeFormat){
        tz = (Intl.DateTimeFormat().resolvedOptions().timeZone || '');
      }
      if(navigator.languages && navigator.languages.length) langs = [].slice.call(navigator.languages);
      else if(navigator.language) langs = [navigator.language];
      /* 地区码来自语言标签的 -XX 段，如 zh-CN -> CN */
      for(var i=0;i<langs.length;i++){
        var m = /-([A-Za-z]{2})$/.exec(langs[i]);
        if(m){ reg = m[1].toUpperCase(); break; }
      }
      var TZ = P.slow_direct_timezones || [], LG = P.slow_direct_langs || [], RG = P.slow_direct_regions || [];
      if(tz && TZ.indexOf(tz) >= 0) return true;
      if(reg && RG.indexOf(reg) >= 0) return true;
      for(var j=0;j<langs.length;j++) if(LG.indexOf(langs[j]) >= 0) return true;
    }catch(e){}
    return false;
  }

  /* ── 选源模型：不再「全局只选一个源」 ──────────────────────────
     旧实现 pickSource() 只返回**一个**源，8 个包全押在它身上。
     实测 ghproxy.net 在 61 MB 包上 3/3 次下不完，而它当时还在候选里 ——
     一旦被选中，用户看到的就是「链接失效」。所以改成：
       ① 按地区决定「要不要加速」；
       ② 要加速就用**全部可用加速源轮转**分担，单个源挂掉只影响一小部分；
       ③ 官方直连永远排在最后垫底。 */
  function wantAccel(){
    var saved = null;
    try{ saved = localStorage.getItem(LSKEY); }catch(e){}
    if(saved === 'direct') return false;
    if(saved && byId(saved)) return true;
    var policy = P.accel || 'auto';
    if(policy === 'on') return true;
    if(policy === 'off') return false;
    return slowDirect();
  }

  /* 有序候选：首选加速源 → 其余加速源 → 官方兜底 */
  function candidates(){
    var d = direct();
    var a = wantAccel() ? accelerators() : [];
    if(!a.length) return d ? [d] : [];
    if(!d) return a;
    return a.concat([d]);
  }

  /* 用户手动固定的源（localStorage）优先覆盖一切 */
  function pinned(){
    var saved = null;
    try{ saved = localStorage.getItem(LSKEY); }catch(e){}
    return (saved && byId(saved)) ? byId(saved) : null;
  }

  /* 第 i 个包的源：优先用户固定源，否则按 (i + 换源偏移) 轮转。
     srcIdx[i] 记录「这个包被手动换过几次源」，每次换源 +1。 */
  var srcIdx = {};
  function sourceFor(i){
    var list = candidates();
    if(!list.length) return null;
    var p = pinned();
    if(p) return p;
    return list[((i % list.length) + (srcIdx[i] || 0)) % list.length];
  }
  function rotateFor(i){
    srcIdx[i] = (srcIdx[i] || 0) + 1;   /* 下一个候选源 */
    return sourceFor(i);
  }

  var queue = document.getElementById('queue'),
      bar = queue && queue.querySelector('.bar i'),
      num = queue && queue.querySelector('.n'),
      now = queue && queue.querySelector('.qn'),
      nextBtn = queue && queue.querySelector('[data-more]'),
      banner = document.getElementById('srcbar'),
      toggle = document.getElementById('srctoggle'),
      quit = false, cursor = 0, timer = null;

  var apps = [];
  document.querySelectorAll('[data-apk]').forEach(function(el){
    apps.push({
      url: el.getAttribute('data-apk'),
      name: el.getAttribute('data-apk-name') || 'apk',
      size: parseInt(el.getAttribute('data-apk-size') || '0', 10)
    });
  });

  /* ── 下载源状态条 ── */
  function paintSource(){
    if(!banner) return;
    var a = accelerators(), pin = pinned();
    var on = wantAccel() && a.length > 0;
    banner.innerHTML = '';
    var b = document.createElement('b');
    b.textContent = pin ? pin.label : (on ? '自动' : 'GitHub 官方');
    banner.appendChild(document.createTextNode((on || pin) ? '加速已开启 · ' : '直连 · '));
    banner.appendChild(b);
    var why;
    if(pin) why = '你手动固定的源——所有包都走它，失败了可以点包上的「换源重下」';
    else if(on) why = '按你的地区自动启用；' + apps.length + ' 个包在 '
                      + (a.length + 1) + ' 个源（含官方兜底）间轮转，单源挂掉不会全灭';
    else why = '你的地区直连速度正常，正在用官方直连';
    banner.appendChild(document.createTextNode(' ── ' + why));
    if(toggle){
      toggle.textContent = (on || pin) ? '改走官方直连' : (a.length ? '开启加速' : '暂无可用加速源');
      toggle.disabled = !a.length && !(on || pin);
    }
  }
  if(toggle) toggle.addEventListener('click', function(){
    var on = (wantAccel() && accelerators().length) || pinned();
    var next = on ? 'direct' : (accelerators()[0] || {}).id;
    if(!next) return;
    try{ localStorage.setItem(LSKEY, next); }catch(e){}
    srcIdx = {};
    paintSource();
    if(queue && queue.classList.contains('on')) buildRetry();
  });

  function human(n){
    if(!n) return '';
    if(n < 1048576) return Math.round(n/1024) + ' KB';
    return (n/1048576).toFixed(1) + ' MB';
  }
  function paint(){
    if(bar) bar.style.width = (apps.length ? cursor/apps.length*100 : 0) + '%';
    if(num) num.textContent = cursor + ' / ' + apps.length;
  }
  function show(){
    if(!queue) return;
    queue.classList.add('on');
    if(nextBtn) nextBtn.style.display = cursor < apps.length ? '' : 'none';
  }
  /* 触发一次下载。srcIdx 为包的下标，源由 sourceFor() 决定。 */
  function fire(i){
    var app = apps[i], m = sourceFor(i);
    if(!app || !m) return false;
    var a = document.createElement('a');
    a.href = accelerate(app.url, m);
    a.download = app.name;
    a.rel = 'noopener';
    /* 必须挂进 DOM 再点：部分移动端浏览器对游离节点不理会 */
    document.body.appendChild(a); a.click();
    setTimeout(function(){ a.remove(); }, 0);
    app._src = m;
    return true;
  }

  function tick(){
    if(quit) return;
    if(cursor >= apps.length){
      if(bar) bar.style.width = '100%';
      /* 全发完之后「继续」是**有意义的**：浏览器对同一页面的连续下载有限流，
         用户处理完系统弹窗后还需要再点一次才能补齐。所以这里重新亮出来，
         不是常显、也不是消失——上一版把它 display:none 了，等于让用户
         卡在「8 个里只下来 3 个」而界面上没有任何下一步。 */
      if(now) now.textContent = '已发起全部 ' + apps.length + ' 个下载（多源轮转）。'
        + '浏览器只会放行一部分，点「继续」补齐剩下的。';
      if(nextBtn) nextBtn.style.display = '';
      paint();
      buildRetry();
      return;
    }
    /* 并发发起多个包。实测单连接吞吐固定，串行只会把 N 次建连的等待叠起来；
       而多源轮转让这批包分摊到不同源上，避免一个反代限速拖垮全部。

       坑：这里**不能再 setTimeout 递归**。旧实现在每批之后挂 1.5 秒再发下一批，
       遇到浏览器弹「允许多个下载」的确认框时，用户还在点确认，页面已经又
       发了一批——两批叠在一起，被限流吞掉的那几个只能靠「换源重下」救。
       所以改成：一批发完就停，等用户点「继续」。限流是浏览器的规则，
       我们只能配合它，不能绕过它。 */
    var burst = 0;
    while(burst < MAX_PARALLEL && cursor < apps.length){
      fire(cursor);
      cursor++; burst++;
      paint();
    }
    if(now){
      now.textContent = cursor < apps.length
        ? '已发起 ' + cursor + ' / ' + apps.length + ' 个下载。处理完浏览器的下载提示后点「继续」发下一批。'
        : '已发起 ' + cursor + ' / ' + apps.length + ' 个下载。';
    }
    if(cursor < apps.length){
      if(nextBtn) nextBtn.style.display = '';
    }else{
      timer = setTimeout(tick, 200);
    }
  }

  function start(){
    quit = false; show();
    if(nextBtn) nextBtn.style.display = 'none';
    if(bar) bar.style.width = '0%';
    cursor = 0; srcIdx = {}; paint();
    timer = setTimeout(tick, 60);
  }

  /* ── 逐包换源重下 ──────────────────────────────────────────────
     为什么要有这个：下载走的是 <a> 导航，浏览器跨域读不到任何响应信息
     （三个反代与直连都不带 Access-Control-Allow-Origin，no-cors 只能拿到
     opaque response，status/字节数全是 0）。所以**页面无法自动知道**某个包
     有没有下成 —— 这决定了「自动重试」在技术上是做不到的，
     能做的是把失败变得「用户一眼能看出 + 一键换源再来一次」。
     这一条是「链接经常失效」的正面对策。 */
  function buildRetry(){
    var host = document.getElementById('retry');
    if(!host) return;
    host.innerHTML = '';
    var list = candidates();
    if(list.length < 2){
      host.innerHTML = '<p style="color:var(--muted);font-size:.88em;margin:.6em 0 0">'
        + '当前只有一个可用下载源（官方直连）。若始终下不下来，通常是网络到 GitHub 不通，'
        + '可在 <code>data/mirrors.py</code> 里加一个加速源。</p>';
      return;
    }
    var p = document.createElement('p');
    p.style.cssText = 'color:var(--muted);font-size:.88em;margin:.8em 0 .5em';
    p.textContent = '某个包没下下来？点它右边的「换源重下」，会改用下一个源再试一次'
      + '（当前共 ' + list.length + ' 个候选）。';
    host.appendChild(p);
    apps.forEach(function(app, i){
      var row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:.6em;align-items:center;justify-content:space-between;'
        + 'padding:.35em 0;border-bottom:1px solid var(--border);font-size:.88em';
      var lab = document.createElement('span');
      lab.textContent = app.name + '　';
      var m = document.createElement('span');
      m.style.color = 'var(--muted)';
      m.textContent = '源：' + ((sourceFor(i) || {}).label || '—');
      lab.appendChild(m);
      var btn = document.createElement('button');
      btn.className = 'btn small';
      btn.type = 'button';
      btn.textContent = '换源重下';
      btn.addEventListener('click', (function(idx, labelEl){
        return function(){
          var nm = rotateFor(idx);
          labelEl.textContent = '源：' + ((nm || {}).label || '—');
          fire(idx);   /* 同一个包，换下一个候选源立即重下 */
        };
      })(i, m));
      row.appendChild(lab); row.appendChild(btn);
      host.appendChild(row);
    });
  }

  box.addEventListener('click', function(e){
    var t = e.target.closest ? e.target.closest('[data-bulk]') : null;
    if(t) start();
  });
  if(queue){
    if(nextBtn) nextBtn.addEventListener('click', function(){
      quit = false;
      nextBtn.style.display = 'none';
      clearTimeout(timer);
      timer = setTimeout(tick, 120);
    });
    /* 停止按钮不能再用 .qx 泛匹配——「继续」按钮上也有这个类，
       泛匹配会让「继续」同时触发停止，表现为「点继续反而停了」 */
    var x = queue.querySelector('.qstop');
    if(x) x.addEventListener('click', function(){
      quit = true; clearTimeout(timer);
      if(now) now.textContent = '已停止。已发起的 ' + cursor + ' 个下载不受影响。';
      queue.classList.remove('on');
    });
  }

  paintSource();
})();
"""

# ---------------------------------------------------------------------------
# 页面骨架
# ---------------------------------------------------------------------------
# 站内导航只在这里定义一次。之所以要「定义一次」而不是每处手写：
# 加一个导航项时，手写的版本总会有某几个页面被忘掉——而这类遗漏在页面上
# 完全看不出来（只是少一个链接），只有用户点不到才发现。check_site.py 里
# 有一条守卫断言**每个页面**的导航项数一致。

THEME_JS = r"""
/* 主题：三档（跟随系统 / 浅色 / 深色）。
   ------------
   为什么要「三档」而不是「只跟随系统」：深色偏好是**设备级**设置，
   但用户在这个站点上的偏好往往和系统不同（比如系统夜里自动切深色，
   而他就想看清图表）。所以给显式覆盖，并把选择存 localStorage。

   为什么这段脚本必须内联在 <head> 里、且在任何样式之前跑：
   否则深色用户会先看到一帧浅色再被切过去（FOUC 闪烁）。
   它做且只做一件事——把 data-theme 挂到 <html> 上，**不改任何样式**。 */
(function(){
  var K = 'icesuite.theme';
  var v = null;
  try{ v = localStorage.getItem(K); }catch(e){}
  var t = (v === 'light' || v === 'dark') ? v : 'auto';
  document.documentElement.setAttribute('data-theme', t);
})();
"""

THEME_BTN_JS = r"""
/* 主题切换按钮：auto → light → dark → auto 循环。
   每次点击都改 data-theme 并落盘；'auto' 时移除显式覆盖，
   交回给 prefers-color-scheme。 */
(function(){
  var K = 'icesuite.theme';
  var btn = document.getElementById('themebtn');
  if(!btn) return;
  var order = ['auto','light','dark'];
  var label = {auto:'🖥', light:'☀', dark:'🌙'};
  var title = {auto:'跟随系统', light:'浅色', dark:'深色'};
  function cur(){
    var t = document.documentElement.getAttribute('data-theme');
    return order.indexOf(t) >= 0 ? t : 'auto';
  }
  function paint(){
    var t = cur();
    btn.textContent = label[t];
    btn.title = '主题：' + title[t] + '（点击切换）';
    btn.setAttribute('aria-label', btn.title);
  }
  btn.addEventListener('click', function(){
    var next = order[(order.indexOf(cur()) + 1) % order.length];
    document.documentElement.setAttribute('data-theme', next);
    try{ localStorage.setItem(K, next); }catch(e){}
    paint();
  });
  paint();
})();
"""

REVEAL_JS = r"""
/* 卡片入场：IntersectionObserver 逐张淡入。
   ------------
   一个刻意的限制：**没有 Observer 或用户偏好减少动效时，必须有兜底**。
   做法是「先给全部卡片加上 .rv，再由 JS 决定要不要观察」——但那样
   JS 挂了就全白。所以反过来：默认不加类，JS 存在才加 .rv 并观察。
   纯静态站最忌讳的就是「JS 一坏整页空白」。 */
(function(){
  if(!('IntersectionObserver' in window)) return;
  if(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  /* 只认 [data-rv] 本身，不要再往下选子元素：上一版把 .rv 挂在 html 上，
     结果卡片里的每个 <span> 都被当成「待淡入元素」，页面上技术栈散成一列方块。 */
  var els = document.querySelectorAll('[data-rv]');
  if(!els.length) return;
  /* 先挂 .js 再挂 .rv：顺序反了会闪一帧「有内容 → 变透明 → 淡入」。
     挂上 <html class="js"> 的同时，CSS 里那 1.2s 的兜底动画就已经在走，
     所以即使下面的 observer 一次都不回调，内容也会自己出现。 */
  document.documentElement.classList.add('js');
  for(var i=0;i<els.length;i++){ els[i].classList.add('rv'); }
  var io = new IntersectionObserver(function(list){
    list.forEach(function(e){
      if(e.isIntersecting){ e.target.classList.add('on'); io.unobserve(e.target); }
    });
  }, {rootMargin: '0px 0px -8% 0px'});
  for(var j=0;j<els.length;j++){ io.observe(els[j]); }
})();
"""


def nav_items(site, prefix):
    """导航项只在这里出现一次。

    新增的四个入口（最新 / 时间线 / 对比 / 集合）不是「多几个链接」——
    它们各自回答一个原来站内没有答案的问题：
      latest   「最近有什么新东西」（原来只能自己翻每个项目页）
      timeline 「这个账号一共发过多少版、节奏如何」（Release 正文就是史料）
      compare  「同类项目摆在一起差在哪」（原来要开四个标签页自己记）
      collections 「按主题看」（标签索引是穷举，集合是编排）
    窄屏仍然只留品牌和主题按钮，这四个从首页入口与页脚进。
    """
    return [
        (f"{prefix}index.html", "全部项目"),
        (f"{prefix}store.html", "应用商店"),
        (f"{prefix}latest.html", "最新"),
        (f"{prefix}timeline.html", "时间线"),
        (f"{prefix}compare.html", "对比"),
        (f"{prefix}collections.html", "集合"),
        (f"{prefix}stats.html", "数据"),
        (f"{prefix}tags.html", "标签"),
        (f"{site['author_url']}", "GitHub"),
    ]


def _cur(active, href):
    """导航高亮。用 aria-current 而不是只有 CSS 类：读屏用户也能知道自己在哪。"""
    if not active:
        return ""
    return ' aria-current="page"' if href.endswith(active) else ""


def page(site, title, body, depth=0, search=False, store=False, mirrors=None,
         desc=None, og_type="website", canonical=None, jsonld=None, robots="index,follow",
         active="", extra_head="", wide=False):
    """渲染一张页面。

    desc / canonical / jsonld 不是可选的锦上添花：没有 canonical 与 og:url，
    分享出去的链接在别的站点上就是一串裸 URL；desc 全站共用一句
    「作品集简介」，等于每张页面在搜索结果里长得一样。
    所以这三样都由调用方按页面类型给出，缺省值只作兜底。
    """
    prefix = "../" * depth
    base = site.get("base_url", "").rstrip("/")
    url = canonical or (f"{base}/" if not depth else "")
    desc = desc or site["desc"]

    theme_js = THEME_JS.replace("__BASE__", prefix)
    # 页面专属脚本要放在 </body> 之前，而不是 <head> 里：
    # 表头排序、安装按钮这类逻辑一上来就要 querySelectorAll，
    # 放 <head> 里那时 DOM 还不存在，等于一段永不生效的死代码。
    # （这一条是浏览器里点了一下「体积」表头没反应才发现的，
    #   静态自检当时全绿——它只查了 data-sort 属性在不在。）
    extra_body_script = extra_head.replace("<script>", "<script>").replace("<link", "<link")
    script = f"<script>{SEARCH_JS.replace('__BASE__', prefix)}</script>" if search else ""
    if store:
        script += f"<script>window.__DL={json.dumps(mirrors or {}, ensure_ascii=False)}</script>"
        script += f"<script>{STORE_JS}</script>"

    ld = ""
    if jsonld:
        ld = ('<script type="application/ld+json">'
              + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
              + "</script>\n")

    canonical_tag = f'<link rel="canonical" href="{esc(url)}">\n' if url else ""
    og_url = f'<meta property="og:url" content="{esc(url)}">\n' if url else ""

    nav = "".join(
        f'<a href="{esc(h)}"{_cur(active, h)}>{esc(t)}</a>'
        for h, t in nav_items(site, prefix))

    html = f"""<!doctype html>
<html lang="zh-CN" data-theme="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="{robots}">
<meta name="color-scheme" content="dark light">
<meta name="author" content="{esc(site['author'])}">
<meta name="theme-color" content="#0b0f14" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f6f8fa" media="(prefers-color-scheme: light)">
<link rel="icon" href="{prefix}icon.svg" type="image/svg+xml">
<link rel="manifest" href="{prefix}manifest.json">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="{esc(site['name'])}">
<link rel="apple-touch-icon" href="{prefix}icon.svg">
{extra_head}
<link rel="alternate" type="application/rss+xml" title="{esc(site['name'])} · 作品更新" href="{prefix}feed.xml">
{canonical_tag}<meta property="og:site_name" content="{esc(site['name'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}">
{og_url}<meta property="og:locale" content="zh_CN">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<script>{theme_js}</script>
<link rel="stylesheet" href="{prefix}style.css">
{ld}</head>
<body>
<a class="skip" href="#main">跳到正文</a>
<div class="netbar" id="netbar" hidden>📴 当前离线，页面来自缓存。下载类操作会失败。</div>
<div class="installbar" id="installbar" hidden>
<span id="installtip" hidden>装到主屏：点下方「分享」→「添加到主屏幕」，之后可离线打开。</span>
<button class="btn small" type="button" id="installbtn" hidden>⤓ 装到桌面</button>
<button class="btn small ghost" type="button" onclick="document.getElementById('installbar').remove()">不用了</button>
</div>
<header class="top"><div class="wrap">
<a class="brand" href="{prefix}index.html">🧊 <em>ice</em> 工坊</a>
<nav>
{nav}
<button class="themebtn" type="button" id="themebtn" aria-label="切换主题">🖥</button>
</nav>
</div></header>
<main class="wrap" id="main">
{body}
</main>
<footer><div class="wrap">
<p>{esc(site['tagline'])} · 站点由 <code>scripts/build_site.py</code> 从 <code>data/projects.py</code> 生成（零依赖、纯静态）。</p>
<p><a href="{prefix}index.html">全部项目</a> · <a href="{prefix}store.html">应用商店</a> ·
<a href="{prefix}latest.html">最新</a> · <a href="{prefix}timeline.html">时间线</a> ·
<a href="{prefix}compare.html">对比</a> · <a href="{prefix}collections.html">集合</a> ·
<a href="{prefix}stats.html">数据</a> · <a href="{prefix}tags.html">标签索引</a> ·
<a href="{prefix}sw.js">离线缓存</a> · <a href="{prefix}sitemap.xml">站点地图</a> ·
<a href="{prefix}feed.xml">RSS</a> · <a href="{site['author_url']}">{esc(site['author'])} on GitHub</a></p>
<p class="fine">页面上的版本号、体积、发布时间均由构建时从仓库内快照渲染，可核对；不含统计脚本、不含 Cookie、不请求任何第三方域。</p>
</div></footer>
{extra_body_script}
<script>{THEME_BTN_JS}</script>
<script>{REVEAL_JS}</script>
<script>{INSTALL_JS}</script>
{script}
</body>
</html>"""
    return html



rich = overlay.rich
plain = overlay.plain


def badge(text, kind):
    return f'<span class="badge {kind}">{esc(text)}</span>'


def _jsonld_project(site, p):
    """单个项目的结构化数据。类型用 SoftwareApplication —— 这些确实是可安装的应用，
    搜索引擎能据此展示「软件」富摘要。没有可安装产物的项目不带该类型，
    它们不是软件，硬套只是为了 SEO 而撒谎。"""
    base = site.get("base_url", "").rstrip("/")
    node = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication" if p["installable"] else "CreativeWork",
        "name": p["name"],
        "description": re.sub(r"<[^>]+>", "", p["summary"]),
        "url": f"{base}/{p['url']}",
        "applicationCategory": "UtilitiesApplication",
        "operatingSystem": "Android" if p.get("platform") == "android" else "Any",
        "author": {"@type": "Person", "name": site["author"], "url": site["author_url"]},
        "isPartOf": {"@type": "WebSite", "name": site["name"], "url": base + "/"},
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "CNY"},
        "license": "https://opensource.org/licenses/MIT",
    }
    if p["installable"]:
        node["softwareVersion"] = p["version"]
        node["fileSize"] = f"{p['size_bytes']} B"
        node["downloadUrl"] = p["dl_release"]
        node["datePublished"] = p["published_at"]
    return node


def _jsonld_site(site, projects, apps):
    base = site.get("base_url", "").rstrip("/")
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "name": site["name"],
                "alternateName": site["tagline"],
                "url": base + "/",
                "inLanguage": "zh-CN",
                "description": site["desc"],
                "author": {"@type": "Person", "name": site["author"],
                           "url": site["author_url"]},
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": base + "/?q={search_term_string}",
                    "query-input": "required name=search_term_string",
                },
            },
            {
                "@type": "ItemList",
                "name": site["store_name"],
                "numberOfItems": len(apps),
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1,
                     "url": f"{base}/{p['url']}", "name": p["name"]}
                    for i, p in enumerate(apps)
                ],
            },
        ],
    }


def _tag_index(projects):
    """标签 → 项目。首页的标签行与 tags.html 都用它，保证两边永远一致。"""
    idx = {}
    for p in projects:
        for t in p["tags"]:
            idx.setdefault(t, []).append(p)
    return dict(sorted(idx.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def _rel_time(site, published_at):
    """把 ISO 日期变回人话。只用来做「最近更新」排序，页面显示仍用原始日期。"""
    return published_at or ""


def build(site, groups, projects, mirrors=None, model=None):
    # 可安装集合先算：首页 hero 与商店页都要用，不能等商店页渲染完才知道
    apps = [p for p in projects if p["installable"]]
    n_apps = len(apps)
    total = sum(p["size_bytes"] for p in apps)
    base = site.get("base_url", "").rstrip("/")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "style.css").write_text(CSS, encoding="utf-8")

    tagmap = _tag_index(projects)
    tag_slug = {t: f"tags.html#{slugify(t)}" for t in tagmap}

    # ---- 搜索索引 ----
    # text 里刻意塞进 tags / metrics / highlights / tech —— 搜索命中「i8mm」
    # 或「断点续传」这种词才有意义，只搜标题等于没搜。
    search = []
    for p in projects:
        text = " ".join([p["summary"], p["group_label"], " ".join(p["tags"]),
                         " ".join(t for t, _ in p["metrics"]),
                         " ".join(h[0] + " " + h[1] for h in p["highlights"]),
                         " ".join(p["tech"])])
        search.append({
            "title": p["name"], "group": p["group_label"], "tags": p["tags"],
            "summary": re.sub(r"<[^>]+>", "", p["summary"]),
            "text": re.sub(r"<[^>]+>", "", text), "url": p["url"],
        })
    (OUT / "search.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")

    by_group = {}
    for p in projects:
        by_group.setdefault(p["group"], []).append(p)

    # ---- 首页 ----
    n_release = sum(1 for p in projects if p["dl_release"])
    n_zero = sum(1 for p in projects if any(k in t for t in p["tags"]
                                            for k in ("零依赖", "零权限", "零广告", "单 dex")))
    sections = []
    for slug, label, desc in groups:
        items = by_group.get(slug, [])
        if not items:
            continue
        cards = []
        for p in items:
            st, kind = STATUS_LABEL.get(p["status"], ("", ""))
            badges = "".join(badge(t, "") for t in p["tags"][:3])
            badges += badge(st, kind)
            if p.get("auto"):
                # 自动发现的仓库用 GitHub 上的原始描述当文案——那是作者自己写的，
                # 但没经过这里的人工编排。标出来，免得读者以为每个字都被审过。
                badges += badge("自动收录", "")
            # 技术栈做成「可点」，但只指向真实存在的标签——tech 里有的词
            # 并不是标签（比如 "Java"），硬链到 #Java 会得到死锚点。
            chips = "".join(
                (f'<a href="{esc(tag_slug[t])}">{esc(t)}</a>' if t in tag_slug else f'<span>{esc(t)}</span>')
                for t in p["tech"][:4])
            # 卡片**不能**是 <a>：卡片里还有指向标签索引的链接，而 HTML 不允许
            # <a> 嵌套 <a>。浏览器不会报错，它会当场把内层 <a> 提到外层之外——
            # 于是卡片被拆成两半，还多出几个「只有技术栈、没有标题」的幽灵卡片，
            # 而构建、自检、HTTP 状态码全都正常。所以改成一个容器 + 一个铺满的标题链接。
            cards.append(
                f'<div class="card reveal">'
                f'<a class="cardhit" href="{p["url"]}" data-rv aria-label="{esc(p["name"])}"></a>'
                f'<div class="t"><a href="{p["url"]}">{esc(p["name"])}</a></div>'
                f'<div class="p">{p["pitch"]}</div>'
                f'<div class="badges">{badges}</div>'
                f'<div class="techrow">{chips}</div>'
                f'</div>'
            )
        sections.append(
            f'<section class="group" id="{slug}"><div class="gh">'
            f'<h2>{esc(label)}</h2><span>{esc(desc)}</span></div>'
            f'<div class="cards">{"".join(cards)}</div></section>'
        )

    # 最近更新：按 Release 日期倒序取前 3。没有日期的不参与排序，
    # 免得「没发过版的项目」被排到最前面当成刚更新。
    recent = sorted([p for p in projects if p["published_at"]],
                    key=lambda x: x["published_at"], reverse=True)[:3]
    recent_html = "".join(
        f'<li><a href="{p["url"]}">{esc(p["name"])}</a> '
        f'<span class="fine">{esc(p["version"] or "")} · {esc(p["published_at"])}'
        f'{(" · " + p["size_text"]) if p["size_text"] else ""}</span></li>'
        for p in recent
    )

    tl_entries = insight.timeline(projects)
    n_collections = len(insight.collection_catalog(model))

    top_tags = list(tagmap.items())[:14]
    tag_html = "".join(
        f'<a class="pill" href="{esc(tag_slug[t])}">{esc(t)} <b>{len(ps)}</b></a>'
        for t, ps in top_tags
    )

    body = f"""<div class="hero">
<p class="kicker">{esc(site['tagline'])}</p>
<h1>{esc(site['name'])}</h1>
<p class="lead">{esc(site['desc'])}</p>
<div class="actions">
<a class="btn primary" href="store.html">🧊 打开应用商店（{n_apps} 个可安装，共 {human_size(total)}）</a>
<a class="btn" href="{esc(site['author_url'])}">源码都在 GitHub</a>
</div>
</div>
<div class="stats">
<div><b>{len(projects)}</b>个作品</div>
<div><b>{n_release}</b>个可直接下载</div>
<div><b>{n_zero}</b>个零第三方依赖</div>
<div><b>{len(tagmap)}</b>个标签</div>
</div>
<input id="q" class="searchbox" type="search" role="combobox" aria-expanded="false"
 aria-controls="results" aria-autocomplete="list"
 placeholder="搜索 {len(projects)} 个项目（名称 / 简介 / 技术栈 / 亮点）…" autocomplete="off">
<div id="results"></div>
<div class="filterbar">{tag_html}<a class="pill" href="tags.html">全部标签 →</a></div>
<div class="entrygrid">
<a class="entry" href="latest.html"><b>🆕 最新更新</b><span>{len(tl_entries)} 个版本按发布日期倒序，改 README 不会出现在这里</span></a>
<a class="entry" href="timeline.html"><b>🕒 时间线</b><span>全部 {len(tl_entries)} 个版本排成一条历史，看节奏</span></a>
<a class="entry" href="compare.html"><b>⇄ 横向对比</b><span>同类项目摆在一起：体积 / 系统 / ABI / 日期</span></a>
<a class="entry" href="collections.html"><b>🗂 集合</b><span>{n_collections} 个按规则自动生成的策展</span></a>
<a class="entry" href="stats.html"><b>📊 数据</b><span>站点每个数字的出处，附 stats.json</span></a>
<a class="entry" href="store.html"><b>🧊 应用商店</b><span>{n_apps} 个包，共 {human_size(total)}</span></a>
</div>
<details class="help" style="margin:1.2em 0 2em">
<summary>最近更新</summary>
<ul style="margin:.7em 0 0;padding-left:1.3em">{recent_html}</ul>
</details>
""" + "\n".join(sections)
    (OUT / "index.html").write_text(
        page(site, f"{site['name']} · {site['tagline']}", body, 0, search=True,
             desc=site["desc"], canonical=base + "/", active="index.html",
             jsonld=_jsonld_site(site, projects, apps)),
        encoding="utf-8")

    # ---- 各项目页 ----
    for i, p in enumerate(projects):
        st, kind = STATUS_LABEL.get(p["status"], ("", ""))
        metrics = "".join(f'<div><b>{esc(v)}</b><span>{esc(k)}</span></div>' for k, v in p["metrics"])
        hls = "".join(f'<li><b>{esc(t)}</b><span>{rich(d)}</span></li>' for t, d in p["highlights"])
        techs = "".join(f'<span class="badge">{esc(t)}</span>' for t in p["tech"])
        limits = "".join(f"<li>{esc(x)}</li>" for x in p.get("known_limits", []))
        limits_block = (
            f'<div class="note"><b>已知限制</b><ul>{limits}</ul></div>' if limits else ""
        )
        # 「这个包现在是什么」：以前只在商店页显示，详情页反而没有。
        # 用户从搜索结果直接落到详情页时，看不到版本和体积，就得再跑一趟商店。
        facts = []
        if p["version"]:
            facts.append(("当前版本", p["version"]))
        if p["size_text"]:
            facts.append(("安装包体积", p["size_text"]))
        if p.get("min_android"):
            facts.append(("最低系统", f"Android {p['min_android']}+"))
        if p.get("arch"):
            facts.append(("ABI", p["arch"]))
        if p["published_at"]:
            facts.append(("发布时间", p["published_at"]))
        if p["downloads"]:
            facts.append(("累计下载", f"{p['downloads']} 次"))
        if p["asset_name"]:
            facts.append(("文件名", p["asset_name"]))
        if p.get("prerelease"):
            facts.append(("状态", "预发布（pre-release）"))
        facts_html = "".join(f'<div><b>{esc(v)}</b><span>{esc(k)}</span></div>' for k, v in facts)

        actions = []
        if p["dl_release"]:
            actions.append(f'<a class="btn primary" href="{p["dl_release"]}">⬇ 下载最新 APK'
                           f'{"（" + p["size_text"] + "）" if p["size_text"] else ""}</a>')
        if p.get("external_url"):
            actions.append(f'<a class="btn" href="{p["external_url"]}">{esc(p["external_label"])}</a>')
        actions.append(f'<a class="btn" href="{p["repo_url"]}">源码仓库</a>')
        if p["dl_release"]:
            actions.append(f'<a class="btn" href="{p["releases_url"]}">全部版本</a>')

        tags_line = " ".join(
            f'<a class="badge" href="{esc(tag_slug[t])}">{esc(t)}</a>' for t in p["tags"])
        prev_p = projects[i - 1] if i > 0 else None
        next_p = projects[i + 1] if i + 1 < len(projects) else None
        pager = ['<div class="pager">']
        pager.append(f'<a href="{prev_p["url"]}">← {esc(prev_p["name"])}</a>' if prev_p else "<span></span>")
        pager.append(f'<a style="text-align:right" href="{next_p["url"]}">{esc(next_p["name"])} →</a>' if next_p else "<span></span>")
        pager.append("</div>")

        # 校验值区块：这是「包是不是你以为的那个包」唯一能自证的东西。
        # 没有快照里的 digest 就不写这一段——不编一个看起来很像的十六进制串。
        sha_block = ""
        if p.get("asset_sha256"):
            sha_block = (
                '<h2>校验安装包</h2>'
                '<p style="color:var(--muted);font-size:.9rem;max-width:64ch">'
                'GitHub 在 Release 元数据里给出的 sha256。下完对一下，对不上就是没下全或被人换过。</p>'
                f'<pre class="sha"><code>sha256sum {esc(p["asset_name"])}\n'
                f'{esc(p["asset_sha256"])}</code></pre>'
                '<p style="color:var(--muted);font-size:.86rem">Windows：'
                f'<code>certutil -hashfile {esc(p["asset_name"])} SHA256</code></p>')

        # 更新记录：Release 正文本来就是作者写的 changelog，白拿一部版本史。
        hist = [h for h in (p.get("history") or []) if h.get("tag")]
        history_block = ""
        if hist:
            rows = []
            for h in hist[:5]:
                body = md_subset(h.get("body") or "")
                if not body.strip():
                    body = ('<p class="fine">这一版没有写更新说明'
                            '（Release 正文为空，只有 GitHub 自动生成的对比链接）。</p>')
                rows.append(
                    f'<details class="rel"><summary><b>{esc(h["tag"])}</b>'
                    f' <span class="fine">{esc(h.get("published_at") or "")}</span></summary>'
                    f'{body}</details>')
            history_block = ('<h2>更新记录</h2>'
                             f'<div class="relnotes">{"".join(rows)}</div>')

        # 自动收录项目的「亮点」= 从 GitHub 上能核实的事实。
        # 不编文案：这几条每一条都能在仓库页面上点开看到。
        facts_auto = []
        if not [h for h in p.get("highlights") or [] if (h[1] if isinstance(h, tuple) else h)]:
            if p.get("language"):
                facts_auto.append(("主要语言", f"仓库主要语言是 {p['language']}，可直接在仓库里按它筛代码。"))
            if p.get("stars") is not None:
                facts_auto.append(("社区反应", f"{p['stars']} 个 Star、{p.get('forks', 0)} 次 Fork —— 数字取自构建时的仓库 API。"))
            if p.get("pushed_at"):
                facts_auto.append(("最近提交", f"{p['pushed_at']} 还有提交，不是放着不管的仓库。"))
            if p.get("releases"):
                facts_auto.append(("发版记录", f"{len(p['releases'])} 个 Release，最早可追溯到 "
                                              f"{p['releases'][-1]['published_at'] or '未知'}。"))
            if p.get("asset_name"):
                facts_auto.append(("安装包", f"{p['asset_name']}（{p['size_text']}），"
                                            f"sha256 可在下方核对。"))
        highlight_items = [h for h in (p.get("highlights") or [])
                           if (h[1] if isinstance(h, tuple) else h)]
        if highlight_items:
            hls = "".join(f'<li><b>{esc(a)}</b><span>{rich(b)}</span></li>'
                          for a, b in (h if isinstance(h, tuple) else (h, "") for h in highlight_items))
            hl_block = f'<h2>技术亮点</h2><ul class="hl">{hls}</ul>'
        elif facts_auto:
            hls = "".join(f'<li><b>{esc(a)}</b><span>{rich(b)}</span></li>' for a, b in facts_auto)
            hl_block = (f'<h2>关于这个项目</h2><ul class="hl">{hls}</ul>'
                        '<p class="fine" style="margin-top:.4em">以上几条是自动整理的事实，'
                        '不是宣传文案；人工介绍还没写。</p>')
        else:
            hl_block = ""

        tech_block = (f'<h2>技术栈</h2><div class="tech">{techs}</div>'
                      if p.get("tech") else "")
        # 体检与相关项目：两个都只用已有数据，且都必须能指回 GitHub。
        health_block = pages.health_block(p, insight.health(p))
        related_block = pages.related_block(p, projects, "")
        # 相关项目区块可能因为「没有任何同组/同标签的项目」而真的为空。
        # 那种情况下不隐藏，而是给出理由 —— 一张空白比一句实话更让人困惑。
        if not related_block:
            related_block = ('<h2>相关项目</h2><div class="relgrid">'
                             '<p class="fine">这个项目没有同分组、也没有共享标签的邻居，'
                             '所以这里没有推荐。不是加载失败。</p></div>')

        auto_badge = badge("自动收录", "") if p.get("auto") else ""
        # summary 与 pitch 常常是同一句话（自动收录的项目更是必然相同：
        # 两者都取自仓库描述）。同一段文字在标题下连刷两遍，读者会以为页面出了 bug。
        plain = re.sub(r"<[^>]+>", "", p["summary"])
        pitch_plain = re.sub(r"<[^>]+>", "", p["pitch"]).strip()
        summary_block = ("" if plain.strip() == pitch_plain else
                         f'<p style="margin-top:1.1em">{esc(plain)}</p>')
        b = f"""<div class="crumb"><a href="index.html">全部项目</a> / <a href="index.html#{p['group']}">{esc(p['group_label'])}</a></div>
<div class="phead">
<h1>{esc(p['name'])}</h1>
<div class="sub">{p['pitch']}</div>
<div>{badge(st, kind)}{auto_badge}{tags_line}</div>
{summary_block}
<div class="actions">{''.join(actions)}</div>
<div class="metrics">{metrics}</div>
{f'<div class="metrics" style="margin-top:10px">{facts_html}</div>' if facts_html else ''}
</div>
{sha_block}
{history_block}
{hl_block}
{health_block}
{limits_block}
{tech_block}
{related_block}
{''.join(pager)}"""
        (OUT / f'{p["id"]}.html').write_text(
            page(site, f'{p["name"]} · {site["name"]}', b,
                 desc=f'{p["name"]}：{plain[:110]}',
                 canonical=f'{base}/{p["url"]}',
                 jsonld=_jsonld_project(site, p),
                 og_type="article"),
            encoding="utf-8")

    # ---- 标签索引页 ----
    # 46 个标签排成一列会让页面长得没边，也不利于找东西。所以：
    # 顶部给一排锚点跳转（按中文标签的拼音不好排，就按「项目数」排序后的顺序标号），
    # 正文用两列网格。两列比「折叠分组」好：折叠默认收起等于把内容藏起来，
    # 而这个页面的唯一价值就是「一眼看全」。
    groups_html = []
    jump = []
    for i, (t, ps) in enumerate(tagmap.items(), 1):
        sid = slugify(t)
        items = "".join(f'<li><a href="{p["url"]}">{esc(p["name"])}</a></li>' for p in ps)
        groups_html.append(
            f'<div class="indexgroup" id="{sid}"><h2>{esc(t)}'
            f' <span class="fine">{len(ps)} 个</span></h2><ul>{items}</ul></div>')
        jump.append(f'<a class="pill" href="#{sid}">{esc(t)} <b>{len(ps)}</b></a>')
    # 按首字分组做二级索引：中文首字没有简易的字母序，所以按 Unicode 序，
    # 只是为了「同一类的词挨在一起」，不宣称是拼音序。
    tag_body = ('<div class="hero"><h1>标签索引</h1>'
                f'<p class="lead">全部 {len(tagmap)} 个标签，按项目数从多到少。'
                '每个标签是页内锚点，方便直接分享「这类项目」的入口。</p></div>'
                f'<div class="filterbar">{"".join(jump)}</div>'
                f'<div class="cols" style="display:grid;grid-template-columns:1fr 1fr;gap:0 28px">'
                + "".join(groups_html) + "</div>")
    (OUT / "tags.html").write_text(
        page(site, f"标签索引 · {site['name']}", tag_body,
             desc=f"{site['name']}全部 {len(tagmap)} 个标签，按项目数排序",
             canonical=base + "/tags.html", active="tags.html"), encoding="utf-8")

    # ---- 应用商店 ----
    build_store(site, groups, projects, mirrors)

    # ---- 404 兜底（GitHub Pages 会用它） ----
    # 之前的 404 只给一个「回首页」按钮。真正会撞上 404 的人是**从旧链接来的**，
    # 所以要给搜索框：他手里有词（项目名），不该被要求自己一层层点回去。
    top = "".join(f'<a class="pill" href="{p["url"]}">{esc(p["name"])}</a>'
                  for p in projects[:6])
    body404 = f"""<div class="hero">
<h1>这个地址没有页面</h1>
<p class="lead">可能是链接写错了，或者项目改过名。搜一下试试，或者从下面挑一个。</p>
<input id="q" class="searchbox" type="search" placeholder="搜索项目…" autocomplete="off">
<div id="results"></div>
<div class="filterbar" style="margin-top:1.2em">{top}</div>
<div class="actions"><a class="btn primary" href="index.html">回到首页</a>
<a class="btn" href="store.html">应用商店</a></div>
</div>"""
    (OUT / "404.html").write_text(
        page(site, "404 · " + site["name"], body404, robots="noindex,follow"), encoding="utf-8")

    # ---- 新增页面（见 pages.py） ----
    # 每张页面都从**同一份 model** 派生，不重新 load 一次：
    # 重新 load 就会有两份 dict，页面之间出现「一个说 12、一个说 11」的概率不为零。
    st = insight.stats(model)
    tl = insight.timeline(projects)
    cats = insight.collection_catalog(model)
    health_map = {p["id"]: insight.health(p) for p in projects}

    def _emit(fname, tup, **kw):
        title, body, _meta = tup
        # 导航高亮默认指向本页：不传 active 就等于「我在哪」这件事没被表达，
        # 而读屏用户是靠 aria-current 判断位置的（颜色对他们不存在）。
        kw.setdefault("active", fname)
        (OUT / fname).write_text(
            page(site, title, body, 0, desc=kw.pop("desc", None),
                 canonical=f"{base}/{fname}", jsonld=kw.pop("jsonld", None), **kw),
            encoding="utf-8")

    _emit("latest.html", pages.latest_page(site, projects, tl, ""),
          desc=f"{site['name']} 全部版本按发版日期倒序", active="latest.html")
    _emit("timeline.html", pages.timeline_page(site, projects, tl, ""),
          desc=f"{site['name']} 发版时间线：{len(tl)} 个版本的完整历史", active="timeline.html")
    _emit("compare.html", pages.compare_page(site, projects, groups, ""),
          desc="同一分组下的项目横向对比：版本、体积、最低系统、ABI、发版日期",
          active="compare.html", extra_head=f"<script>{pages.COMPARE_JS}</script>")
    _emit("collections.html", pages.collections_page(site, cats, projects, ""),
          desc="按规则自动生成的策展集合：能装的、还没发版的、只有源码的、按标签归类的",
          active="collections.html")
    _emit("stats.html", pages.stats_page(site, st, projects, ""),
          desc="站点全部数字的出处：每月发版、语言分布、包体积、下载量",
          active="stats.html")

    # ---- 机器可读产物 ----
    # stats.json / graph.json / content.json 不是「给页面用的」，
    # 是**给别人的程序用的**：一个客户端能只下 3 KB 就知道有没有新版、
    # 谁依赖谁、这份数据是哪次构建的。站点从此有了三个稳定契约。
    write_json(OUT / "stats.json", st)
    graph = _graph(projects)
    write_json(OUT / "graph.json", graph)
    # ---- PWA：manifest + service worker + maskable 图标 ----
    # 顺序有讲究：sw.js 里要写「缓存的是哪一版」，而版本号是 content.json
    # 算出来的产物指纹 —— 所以先出 PWA 文件，最后再算 content.json。
    # 反过来（先算 content.json 再写 sw.js）会让 content.json 漏掉这两个文件，
    # 而「漏掉」这件事正好是 content.json 存在的意义，自检里有一条专门抓它。
    # 版本号先在「不含 PWA 三件套」的产物上算一遍：这三件套自己也要进索引，
    # 而 sw.js 里写着版本号 —— 直接拿全量索引的 id 会变成自己引用自己。
    # 取「其余全部产物」的指纹做版本名，既有意义（内容变了版本就变），
    # 又不会自指。manifest.json 与 content.json 里的 build.id 是最终全量指纹，
    # 两者用途不同：前者是缓存命名，后者是完整性校验。
    version_tag = _content_index(OUT, base)["build"]["id"][:12]
    (OUT / "icon-maskable.svg").write_text(app_assets.ICON_MASKABLE, encoding="utf-8")
    (OUT / "manifest.json").write_text(
        app_assets.manifest(site, version_tag), encoding="utf-8")
    precache = ["./index.html", "./store.html", "./latest.html", "./timeline.html",
                "./collections.html", "./compare.html", "./tags.html", "./stats.html",
                "./style.css", "./icon.svg", "./search.json", "./update.json",
                "./404.html"]
    (OUT / "sw.js").write_text(
        app_assets.service_worker(version_tag, precache), encoding="utf-8")

    # ---- icon.svg：手写，不引任何素材 ----
    (OUT / "icon.svg").write_text(ICON_SVG, encoding="utf-8")

    # ---- update.json：机器可读的版本清单 ----
    # 给「应用自带的检查更新」用：一个 JSON 就能判断有没有新版、从哪下、校验值是多少，
    # 不必解析 HTML。站点本身也因此多了一个稳定的对外契约。
    apps_json = {}
    for p in apps:
        apps_json[p["repo"]] = {
            "name": p["name"],
            "version": p["version"],
            "prerelease": bool(p.get("prerelease")),
            "published_at": p["published_at"],
            "size": p["size_bytes"],
            "file": p.get("asset_name") or "",
            "sha256": p.get("asset_sha256") or None,
            "url": p["dl_release"],
            "page": f"{base}/{p['url']}",
            "min_android": p.get("min_android") or None,
            "abi": p.get("arch") or None,
        }
    (OUT / "update.json").write_text(json.dumps({
        "_note": "由 scripts/build_site.py 从 data/registry.json 生成；"
                 "sha256 来自 GitHub Release 资产元数据，取不到就是 null（不推算）。",
        "generated_at": source_stamp() or iso_now(),
        "count": len(apps_json),
        # 顶层自述「这份清单有多少条能被验证」，而不是让客户端自己遍历一遍数。
        # 12/12 是健康，10/12 就说明有两个包的校验值拿不到 —— 客户端可以据此
        # 决定要不要提示用户「这版没法验完整性」，而不必自己写这段判断。
        "verify": {
            "sha256_covered": sum(1 for a in apps_json.values() if a.get("sha256")),
            "size_covered": sum(1 for a in apps_json.values() if a.get("size")),
            "note": "sha256 取不到写 null，不推算；size 是 Release 资产的字节数原值。",
        },
        "apps": apps_json,
    }, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ---- sitemap.xml / robots.txt / feed.xml ----
    write_sitemap(site, projects)
    write_feed(site, projects[:0], apps)
    write_robots(site)

    # CNAME：GitHub Pages 绑定自定义域名的唯一凭据；.nojekyll 让 Pages 不要跑 Jekyll
    (OUT / "CNAME").write_text(site["domain"] + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    return len(projects), n_apps, total


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
<rect width="64" height="64" rx="14" fill="#0b0f14"/>
<g fill="none" stroke="#5ad1ff" stroke-width="3" stroke-linecap="round">
<path d="M32 12v40M15 22l34 20M49 22L15 42"/>
<path d="M32 12l-5 5M32 12l5 5M32 52l-5-5M32 52l5-5"/>
<path d="M15 22l7 1M15 22l1-7M49 42l-7-1M49 42l-1 7"/>
<path d="M49 22l-1-7M49 22l-7 1M15 42l1 7M15 42l7-1"/>
</g>
</svg>
"""


def write_sitemap(site, projects):
    base = site.get("base_url", "").rstrip("/")
    pages = [("", "1.0"), ("store.html", "0.9"), ("tags.html", "0.6")]
    for p in projects:
        pages.append((p["url"], "0.8"))
    rows = []
    for path, pri in pages:
        rows.append(f"  <url><loc>{base}/{path}</loc><priority>{pri}</priority></url>")
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows) + "\n</urlset>\n", encoding="utf-8")


def write_robots(site):
    base = site.get("base_url", "").rstrip("/")
    (OUT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % base, encoding="utf-8")


def write_feed(site, _unused, apps):
    """RSS 2.0，按 Release 发布时间倒序。

    为什么是「发版」而不是「改文案」：这个站点最有信息量的变化是某个应用
    出了新版本。文案微调不值得推给任何人——那是把订阅者当垃圾桶。
    """
    base = site.get("base_url", "").rstrip("/")
    items = sorted([p for p in apps if p["published_at"]],
                   key=lambda x: x["published_at"], reverse=True)
    rows = []
    for p in items:
        title = f"{p['name']} {p['version']}（{p['size_text']}）"
        link = p["dl_release"]
        desc = (f"{re.sub(r'<[^>]+>', '', p['pitch'])}｜{p['size_text']}"
                f"｜要求 Android {p.get('min_android', '—')}+")
        rows.append(
            "  <item>\n"
            f"    <title>{html.escape(title)}</title>\n"
            f"    <link>{html.escape(link)}</link>\n"
            f"    <guid isPermaLink=\"false\">{html.escape(p['repo_url'] + '#' + p['version'])}</guid>\n"
            f"    <pubDate>{rfc822(p['published_at'])}</pubDate>\n"
            f"    <description>{html.escape(desc)}</description>\n"
            "  </item>")
    (OUT / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        f"  <title>{html.escape(site['name'])} · 作品更新</title>\n"
        f"  <link>{base}/</link>\n"
        f"  <description>{html.escape(site['desc'])}</description>\n"
        "  <language>zh-CN</language>\n"
        + "\n".join(rows) + "\n</channel></rss>\n", encoding="utf-8")


def md_subset(text):
    """极小的 Markdown 子集渲染器（标题 / 列表 / 引用 / 围栏 / 粗体 / 行内 code / 链接）。

    为什么不引 markdown 库：这个站点的立身之本是「零第三方依赖」，
    为了渲染 Release 正文加一个依赖，等于用立身之本来换一个便利。
    先整体转义，再按白名单放回标记——顺序不能反，否则 <script> 会被当 HTML 执行。
    """
    out, in_code, in_list = [], False, False
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            out.append("</code></pre>" if in_code else "<pre><code>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        esc_line = html.escape(line)
        esc_line = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc_line)
        esc_line = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", esc_line)
        esc_line = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                          r'<a href="\2" rel="nofollow noopener">\1</a>', esc_line)
        m = re.match(r"^(#{1,4})\s+(.*)$", esc_line)
        if m:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f'<h4>{m.group(2)}</h4>')
            continue
        if re.match(r"^\s*[-*+]\s+", esc_line):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append("<li>" + re.sub(r"^\s*[-*+]\s+", "", esc_line) + "</li>")
            continue
        if in_list:
            out.append("</ul>"); in_list = False
        if esc_line.startswith("&gt;"):
            out.append(f'<blockquote>{esc_line[4:].strip()}</blockquote>')
        elif esc_line.strip():
            out.append(f"<p>{esc_line}</p>")
    if in_list:
        out.append("</ul>")
    if in_code:
        out.append("</code></pre>")
    return "".join(out)


ICONS = {
    "icescribe": "🎙", "modelscopebrowser": "🤖", "kayago": "⚫", "icescan": "📄",
    "icebrowser": "🌐", "icereading": "📖", "musicfusion": "🎵", "musicfusionai": "✨",
    "frontier": "🧠", "icellm": "🖥", "iceproxy": "🔌",
}


def store_app_row(p, prefix=""):
    """商店列表里的一行。有 APK 就放下载按钮，没有就说清楚「它不是安装包」。"""
    ico = ICONS.get(p["id"], "📦")
    st, kind = STATUS_LABEL.get(p["status"], ("", ""))
    name = f'<a href="{prefix}{p["url"]}">{esc(p["name"])}</a>'

    meta = []
    if p["version"]:
        meta.append(f'<span class="ver">{esc(p["version"])}</span>')
    if p["size_text"]:
        meta.append(f'<span>{p["size_text"]}</span>')
    if p.get("min_android"):
        meta.append(f'<span>Android {esc(p["min_android"])}+</span>')
    if p["published_at"]:
        meta.append(f'<span>{esc(p["published_at"])}</span>')
    if p["downloads"]:
        meta.append(f'<span>{p["downloads"]} 次下载</span>')
    meta_html = '<span class="dot">·</span>'.join(meta)

    if p["installable"]:
        act = (f'<a class="btn primary" href="{p["dl_release"]}" '
               f'data-apk="{p["dl_release"]}" '
               f'data-apk-name="{esc(p.get("asset_name") or p["repo"] + ".apk")}" '
               f'data-apk-size="{p["size_bytes"]}" '
               f'data-apk-sha="{esc(p.get("asset_sha256") or "")}" '
               f'data-apk-ver="{esc(p["version"])}">⬇ {p["size_text"] or "下载"}</a>'
               f'<a class="btn" href="{prefix}{p["url"]}">详情</a>')
        cls = "app"
    else:
        act = (f'<a class="btn" href="{p["repo_url"]}">去仓库</a>'
               f'<a class="btn" href="{prefix}{p["url"]}">详情</a>')
        cls = "app none"

    badges = "".join(badge(t, "") for t in p["tags"][:2]) + badge(st, kind)
    if p.get("auto"):
        badges += badge("自动收录", "")
    if p.get("prerelease"):
        badges += badge("pre", "warn")
    return (f'<div class="{cls}">'
            f'<div class="ico">{ico}</div>'
            f'<div><div class="nm">{name}{badges}</div>'
            f'<div class="meta">{meta_html}</div>'
            f'<div class="pitch">{p["pitch"]}</div></div>'
            f'<div class="act">{act}</div></div>')


def build_store(site, groups, projects, mirrors=None):
    apps = [p for p in projects if p["installable"]]
    others = [p for p in projects if not p["installable"]]
    total_bytes = sum(p["size_bytes"] for p in apps)
    n_apps, total = len(apps), total_bytes

    n_mirrors = len((mirrors or {}).get("mirrors", []))
    # 把「有哪些源、各自什么角色」写出来。选哪个由前端按地区决定，
    # 所以这里标的是角色而不是「默认/备选」——「默认」是运行时的事，不是静态的。
    mirror_rows = ""
    for m in (mirrors or {}).get("mirrors", []):
        if m.get("role") == "fallback":
            tag = '<span class="badge ok">兜底</span>'
        else:
            tag = '<span class="badge">加速</span>'
        mirror_rows += (f'<tr><td>{esc(m["label"])}</td>'
                        f'<td>{tag}</td>'
                        f'<td><code>{esc(m["prefix"]) or "（直连，无前缀）"}</code></td></tr>')

    bulk = f"""<div class="bulk" id="bulk">
<div class="row">
<div class="grow">
<b>一次下齐全部 {len(apps)} 个应用</b>
<span class="update-item">共 <span class="tot">{human_size(total_bytes)}</span>。
会按你的地区自动决定要不要加速，并把各个包<b>轮转分摊到多个源</b>上，
同时<b>并行发起</b>（每批 5 个）——小包慢就慢在建连上，并行之后总速度是几条连接之和；
多源轮转则保证单源挂掉不会全灭。
中途可停；某个包没下下来的话，下面有它的「换源重下」。</span>
</div>
<button class="btn primary" type="button" data-bulk="1">⬇ 一键下载全部（{human_size(total_bytes)}）</button>
</div>
</div>"""

    rows = "".join(store_app_row(p) for p in apps)
    other_rows = "".join(store_app_row(p) for p in others)

    body = f"""<div class="storehead">
<h1>{esc(site['store_name'])}</h1>
<span class="tag">{esc(site['store_tagline'])}</span>
</div>
<p style="color:var(--muted);max-width:64ch">
下面 {len(apps)} 个安装包全部来自本账号各仓库的 GitHub Release。
这份清单是<b>自动发现</b>的：你新开一个仓库发个 Release，最晚一小时内它就会出现在这里，
不需要谁去改代码。版本号、体积、包名、sha256、发布时间都是构建时从 Release 元数据里取的，不是写死的文案。
没有广告 SDK、没有追踪、没有账号体系——这一点和它们本来的实现一致。
</p>
{bulk}
<h2 style="margin-top:2.4em">可安装应用（{len(apps)}）</h2>
<div class="applist">{rows}</div>
<h2>不是安装包（{len(others)}）</h2>
<p style="color:var(--muted);font-size:.9rem">
这几个是脚本、服务端或纯静态站，本来就没有 APK。放进商店页只是为了让「账号里有什么」一眼看全，
按钮指向仓库，不伪造一个包。
</p>
<div class="applist">{other_rows}</div>
<details class="help">
<summary>装不上 / 下载被拦住了怎么办</summary>
<ol>
<li>Android 8.0 起，浏览器下载的 APK 需要先允许「安装未知应用」——在系统弹窗里点允许即可。</li>
<li>部分机型会提示「此类文件可能有害」，这是对非商店来源 APK 的通用提示，选择仍要安装。</li>
<li>如果浏览器把文件存成了 <code>.bin</code> 或没有后缀，重命名回 <code>.apk</code> 再装。</li>
<li><b>关于一键下载</b>：浏览器对同一页面连续触发的下载有限流（桌面 Chrome 会弹「允许多个下载」，移动端更严格）。所以每批 5 个，收到文件后点「继续」补齐剩下的，断在哪就从哪接着下。</li>
<li>若某个包始终下不下来，直接在列表里单独点它的下载按钮即可，效果一样。</li>
<li>校验完整性：页面上显示的体积就是 Release 里资源的字节数，下载后可自行比对。</li>
</ol>
</details>

<h2 id="speed">下载速度</h2>
<p style="color:var(--muted);font-size:.9rem;max-width:64ch">
这里没有服务端、也没有 CDN，就是 GitHub 在发文件。能动的只有两件事：
<b>「从哪下」</b>和<b>「怎么下」</b>。两件都做了，下面把依据和取舍摊开说——
包括一个做错了又撤掉的做法，因为它失败得太安静，不写下来下一个人会再走一遍。
</p>

<div class="srcbar-wrap">
<span class="srcbar" id="srcbar">正在判断下载源…</span>
<button class="btn small" type="button" id="srctoggle">切换</button>
</div>

<details class="help" open>
<summary>① 「从哪下」：按你的地区自动选源（不用测速）</summary>
<p style="margin-top:.9em">
直连 GitHub 的体验是<b>按地区两极分化</b>的，而且这个差异是<b>稳定的</b>：大陆普遍只有
几百 KB/s 甚至断流，海外接近满速。既然差异稳定，就可以<b>在本地推断</b>，一个网络请求都不用发。
</p>
<p>判断依据全部来自浏览器已有的本地信息：</p>
<table class="mirrors">
<thead><tr><th>信号</th><th>例子</th><th>作用</th></tr></thead>
<tbody>
<tr><td>时区</td><td><code>Asia/Shanghai</code></td><td>主要依据</td></tr>
<tr><td>语言 / 地区</td><td><code>zh-CN</code> → <code>CN</code></td><td>辅助</td></tr>
</tbody>
</table>
<p>
命中 → 判定「直连大概率很慢」→ <b>默认启用加速</b>；否则默认官方直连
（海外直连本来就不慢，套一层反代只是多一跳）。
</p>
<p style="color:var(--warn)">
<b>「走了第三方」这件事必须看得见。</b>上面那行状态会实时显示当前用哪个源，点「切换」就能改回官方直连，
选择会记住。加速源打不开时会<b>显式回退</b>到官方并在页面说明，不静默降级。
默认开加速的前提，是它完全透明。
</p>
</details>

<details class="help">
<summary>② 为什么不「自动测速选源」：做过，是假的</summary>
<p style="margin-top:.9em">
最直觉的做法是用 <code>fetch</code> 并发探测每个候选、按实测速度挑最快的。我实现过，<b>结果是四个候选一个都读不到数据</b>。
原因是 CORS：GitHub Release 会 302 到 <code>release-assets.githubusercontent.com</code>，
而那一跳<b>不带 <code>Access-Control-Allow-Origin</code></b>，三个反代同样不带。
浏览器读不到响应字节数，计时恒为 0。
</p>
<p>
更糟的是它<b>看起来是能用的</b>：探针全部失败后会悄悄退回官方直连，页面照常下完文件，
用户完全不会察觉——区别只是白花了 4 次请求，而那个「智能选源」从来没生效过。
</p>
<p style="color:var(--muted);font-size:.9em">
顺带一个反直觉的点：探针 <code>fetch</code> 失败只说明「缺 CORS 头」，
<b>不代表镜像挂了</b>——实测失败的候选，用浏览器直接下照样是 200 完整文件。
所以「能不能 fetch 通」既不能当可用性判断，也不能当选源依据。
</p>
</details>

<details class="help">
<summary>③ 「怎么下」：并行建连；但别指望「多线程下载」</summary>
<p style="margin-top:.9em">
这里<b>没有</b>「多线程下载大文件」，因为实测不成立。同一个 58.3 MB 的包，
在同一个网络里开不同数量的并发连接：
</p>
<table class="mirrors">
<thead><tr><th>并发连接</th><th>总吞吐</th><th>用时</th></tr></thead>
<tbody>
<tr><td>1 条</td><td>6.25 MB/s</td><td>14.8 s</td></tr>
<tr><td>4 条（分块下载）</td><td>5.98 MB/s</td><td>9.8 s</td></tr>
</tbody>
</table>
<p>
每条连接的吞吐是<b>固定</b>的，多开连接不增加总带宽，所以分块下载写上去只是好看，不会变快。
</p>
<p>但<b>并行发起多个包</b>是真实收益——因为小包慢在建连，不是慢在带宽：</p>
<table class="mirrors">
<thead><tr><th>安装包</th><th>体积</th><th>单连接实测</th></tr></thead>
<tbody>
<tr><td>iceScribe</td><td>58.3 MB</td><td>2.4 MB/s</td></tr>
<tr><td>魔搭模型库</td><td>7.8 MB</td><td>2.1 MB/s</td></tr>
<tr><td>MusicFusion</td><td>0.3 MB</td><td>1.3 MB/s</td></tr>
<tr><td>iceBrowser</td><td>0.17 MB</td><td>0.9 MB/s</td></tr>
<tr><td>KayaGo</td><td>0.07 MB</td><td>0.78 MB/s</td></tr>
</tbody>
</table>
<p>
小包的 TTFB 实测 <b>0.3~1.3 秒</b>，包越大这部分占比越小。所以页面<b>每批并行发起 5 个</b>：
总吞吐是几条连接之和，而不是把 5 次建连的等待串起来。
</p>
</details>

<details class="help">
<summary>④ 修复「下载慢 / 链接经常失效」：多源轮转 + 换源重下</summary>
<p style="margin-top:.9em">
先说清楚一件事：<b>页面没法自动知道哪个包有没有下成。</b>
下载走的是 <code>&lt;a&gt;</code> 导航，而跨域读响应被 CORS 挡死——
直连和三个反代<b>都不带 <code>Access-Control-Allow-Origin</code></b>，
<code>no-cors</code> 只能拿到 opaque response（<code>status=0</code>、<code>type=opaque</code>，字节数读不到）。
实测确认：无论包是否存在、源是否超时，fetch 都在 10~20 ms 内返回，<b>读不出任何差异</b>。
所以「自动重试」在浏览器里是做不到的，任何声称能做的实现都是在骗人。
</p>
<p><b>那能做什么？两件真事：</b></p>
<p>
<b>① 不再把所有包押在一个源上。</b>之前 8 个包全用同一个源，一个反代限速就全灭。
现在按包<b>轮转</b>分摊到多个加速源，单源挂掉最多影响其中一两个。
实测就有反例：<code>ghproxy.net</code> 在 61 MB 包上 <b>3/3 次都下不完</b>
（3 分钟只拿到 3~4 MB），这种源已经被移出候选——留在列表里，
一旦被选中，用户看到的就是「链接失效」。
</p>
<p>
<b>② 每个包都能单独「换源重下」。</b>某个包没下来，点它右边的按钮，
会换到下一个候选源立即重下，不用整批重来。源的状态就写在每个包旁边。
</p>
<table class="mirrors">
<thead><tr><th>下载源</th><th>角色</th><th>地址前缀</th></tr></thead>
<tbody>{mirror_rows}</tbody>
</table>
<p style="color:var(--muted);font-size:.86em">
这张表来自仓库里的 <code>data/mirrors.py</code>，是构建时渲染的——不是写死在本页里的。
某个镜像挂掉了，删掉那一行就好，前端会自动少一个候选；<code>direct</code> 这条不允许删，它是兜底。
</p>
</details>
<div class="queue" id="queue">
<div class="qh"><span>批量下载</span><span class="n">0 / 0</span>
<button class="qx qmore" type="button" data-more="1" style="display:none;color:var(--accent);border-color:#19405a">继续</button>
<button class="qx qstop" type="button">停止</button></div>
<div class="bar"><i></i></div>
<div class="qn">准备中…</div>
</div>
<div id="retry"></div>"""

    (OUT / "store.html").write_text(
        page(site, f"{site['store_name']} · {site['name']}", body, 0, store=True,
             mirrors=mirrors, active="store.html"),
        encoding="utf-8")

def _graph(projects):
    """项目之间的关系图。

    两种边：同分组（group）与同标签（tag）。权重 = 共享标签数。
    只用**已有数据**，不推断「用户也看了」这类要埋点的东西 ——
    这个站点没有追踪，也就不该有一张假装懂行为的图。
    """
    nodes = [{"id": p["id"], "name": p["name"], "group": p["group"],
              "kind": p.get("platform") or "code",
              "installable": bool(p["installable"]),
              "version": p.get("version") or "",
              "size": p["size_bytes"] if p["installable"] else 0,
              "tags": list(p["tags"]),
              "url": p["url"]} for p in projects]
    edges = []
    for i, a in enumerate(projects):
        for b in projects[i + 1:]:
            shared = sorted(set(a["tags"]) & set(b["tags"]))
            if a["group"] == b["group"]:
                edges.append({"a": a["id"], "b": b["id"], "kind": "group",
                              "group": a["group"], "weight": 1 + len(shared)})
            elif shared:
                edges.append({"a": a["id"], "b": b["id"], "kind": "tag",
                              "tags": shared, "weight": len(shared)})
    edges.sort(key=lambda e: (-e["weight"], e["a"], e["b"]))
    return {"_note": "由 scripts/build_site.py 生成。节点=项目，边=同分组或同标签；"
                     "weight 只由共享标签数决定，不含任何行为数据。",
            "nodes": nodes, "edges": edges}


def _content_index(out: Path, base: str) -> dict:
    """产物自索引：每个文件的 sha256 + 字节数 + 产物指纹。

    这是「同一 commit 同一产物」这句承诺的**可验证形式**：
    任何人下载 content.json 就能核对整站，不用信任构建日志。
    build.id 只由所有文件的哈希决定，所以只要内容一样，id 就一样，
    与构建时间无关 —— 反过来，id 变了就一定是内容变了。
    """
    files = {}
    total = 0
    for f in sorted(out.rglob("*")):
        if not f.is_file() or f.name == "content.json":
            continue
        raw = f.read_bytes()
        files[str(f.relative_to(out))] = {
            "bytes": len(raw),
            "sha256": __import__("hashlib").sha256(raw).hexdigest(),
        }
        total += len(raw)
    ident = __import__("hashlib").sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    pages = [k for k in files if k.endswith(".html")]
    return {
        "_note": "构建产物索引。build.id 是全部文件内容的结构哈希 —— "
                 "同一份输入必然得到同一个 id，与构建时间无关。可用于核对站点完整性。",
        "base_url": base,
        # 刻意没有 generated_at：这一份是完整性与可复现的凭据，
        # 带上时间就不再可复现。要「数据什么时候新鲜」，看 stats.json /
        # update.json 里的 generated_at —— 那两个来自快照，不来自构建。

        "build": {
            "id": ident,
            "files": len(files),
            "bytes": total,
            "pages": len(pages),
        },
        "files": files,
    }


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    OUT = Path(args.out)
    site, groups, projects, mirrors, model = load()
    n, n_apps, total = build(site, groups, projects, mirrors, model)
    # content.json 必须**最后**生成：它是产物索引，早写一步就会漏掉后面写的
    # CNAME / .nojekyll / sitemap / feed。这个错我这一版就犯过一次，
    # 是 check_site 里那条「产物里有文件没进 content.json」抓出来的。
    base = site.get("base_url", "").rstrip("/")
    content = _content_index(OUT, base)
    write_json(OUT / "content.json", content)
    print(f"构建完成：{n} 个项目 → {OUT}")
    print(f"产物指纹：{content['build']['id'][:16]}（{content['build']['files']} 个文件）")
    print(f"应用商店：{n_apps} 个可安装包，共 {human_size(total)}")
    print(f"首页：{OUT / 'index.html'}")
    print(f"CNAME：{site['domain']}")


if __name__ == "__main__":
    main()
