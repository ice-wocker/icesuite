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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "site"

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
}

STATUS_LABEL = {
    "mature": ("稳定", "ok"),
    "active": ("迭代中", "info"),
    "beta":  ("预研", "warn"),
}


def esc(s):
    return html.escape(str(s), quote=False)


def human_size(n):
    """把字节数写成人看得懂的样子。用 1024 进制，和系统「应用信息」里的口径一致。"""
    if not n:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        kb = n / 1024
        return f"{kb:.0f} KB" if kb >= 10 else f"{kb:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def load_mirrors():
    """读 data/mirrors.py —— 加速候选清单。

    和 releases.json 不同，这个文件是**手写**的：镜像站是别人家的服务，
    没有自动机制能保证它们活着。所以它必须允许「这里就是空的」——
    一个候选都没有时，前端只是没有加速可开，站点照常构建。
    """
    ns = {}
    f = DATA / "mirrors.py"
    if not f.exists():
        return [], {}
    exec(f.read_text(encoding="utf-8"), ns)
    mirrors = [m for m in ns.get("MIRRORS", []) if m.get("prefix") is not None]
    params = {
        "probe_bytes": ns.get("PROBE_BYTES", 96 * 1024),
        "chunks": ns.get("CHUNKS", 2),
        "chunk_min_bytes": ns.get("CHUNK_MIN_BYTES", 4 * 1024 * 1024),
    }
    return mirrors, params


def load_releases():
    """读 data/releases.json —— 「这个包现在长什么样」的唯一真相源。

    文件不存在不算致命：只是商店页拿不到版本号，站点其余部分照常构建。
    真正的把关在 check_site.py，那里会把它当错误报出来。
    """
    f = DATA / "releases.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("releases", {})


def load():
    ns = {}
    exec((DATA / "projects.py").read_text(encoding="utf-8"), ns)
    site = ns.get("SITE", SITE)
    groups = ns.get("GROUPS", GROUPS)
    projects = ns["PROJECTS"]
    gmap = {k: (k, label, desc) for k, label, desc in groups}
    releases = load_releases()
    mirrors, mirror_params = load_mirrors()
    for p in projects:
        rel = releases.get(p["repo"]) or {}
        p["repo_url"] = f"https://github.com/{site['author']}/{p['repo']}"
        p["releases_url"] = f"https://github.com/{site['author']}/{p['repo']}/releases"
        p["url"] = f"{p['id']}.html"
        p["group_label"] = gmap[p["group"]][1]
        # 可安装产物完全由 releases.json 决定：有 .apk 才叫「能装」
        p["version"] = rel.get("tag") or ""
        p["published_at"] = rel.get("published_at") or ""
        p["size_bytes"] = rel.get("size") or 0
        p["size_text"] = human_size(rel.get("size"))
        p["downloads"] = rel.get("downloads") or 0
        p["dl_release"] = rel.get("url")
        p["installable"] = bool(p.get("platform") and p["dl_release"])
        # 文案里的 {size} 只在这里替换，保证「页面上的体积」与「Release 里的字节数」
        # 永远是同一个数。没有 Release 的项目保留原样，不做假数据。
        if p["size_text"]:
            for k in ("pitch", "summary", "store_note"):
                if isinstance(p.get(k), str):
                    p[k] = p[k].replace("{size}", p["size_text"])
    p_mirrors = {
        "mirrors": [
            {"id": m["id"], "label": m["label"], "prefix": m.get("prefix", ""),
             "default": bool(m.get("enabled_by_default"))}
            for m in mirrors
        ],
        "params": mirror_params,
    }
    return site, groups, projects, p_mirrors


CSS = """
:root{--bg:#0b0f14;--panel:#131a22;--panel2:#0f151c;--border:#243040;--fg:#e6edf3;
--muted:#8b98a8;--accent:#5ad1ff;--accent2:#7ee787;--warn:#ffb454}
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
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.card{display:block;padding:16px 18px;background:var(--panel);border:1px solid var(--border);
border-radius:12px;color:var(--fg);transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--accent);text-decoration:none;transform:translateY(-2px)}
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
@media(max-width:640px){h1,.hero h1{font-size:1.5rem}.wrap{padding:0 16px}
header.top nav{display:none}.stats{gap:18px}}
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

SEARCH_JS = """
(function(){
  var box=document.getElementById('q'), out=document.getElementById('results');
  if(!box) return;
  var data=null,timer=null;
  fetch('search.json').then(function(r){return r.json()}).then(function(j){data=j;});
  function esc(s){return s.replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
  function render(kw){
    if(!data) return;
    kw=kw.trim().toLowerCase();
    if(!kw){out.innerHTML='';return;}
    var terms=kw.split(/\\s+/).filter(Boolean),hits=[];
    for(var i=0;i<data.length;i++){
      var d=data[i],hay=(d.title+' '+d.summary+' '+d.text+' '+d.tags.join(' ')).toLowerCase();
      var score=0,ok=true;
      for(var t=0;t<terms.length;t++){
        var idx=hay.indexOf(terms[t]);
        if(idx<0){ok=false;break;}
        score+=(d.title.toLowerCase().indexOf(terms[t])>=0)?50:1;
      }
      if(ok) hits.push([score,d]);
    }
    hits.sort(function(a,b){return b[0]-a[0]});
    hits=hits.slice(0,30);
    if(!hits.length){out.innerHTML='<p class="d" style="color:#8b98a8">没有匹配的项目。</p>';return;}
    out.innerHTML=hits.map(function(h){
      var d=h[1],s=d.summary||'';
      for(var t=0;t<terms.length;t++){
        var re=new RegExp('('+terms[t].replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')+')','ig');
        s=s.replace(re,'<mark>$1</mark>');
      }
      return '<a class="hit" href="'+d.url+'"><div>'+esc(d.title)+'</div>'+
             '<div class="d">'+esc(d.group)+' · '+d.tags.join(' / ')+'</div>'+
             '<div class="d">'+s+'</div></a>';
    }).join('');
  }
  box.addEventListener('input',function(){clearTimeout(timer);timer=setTimeout(function(){render(box.value)},120)});
})();
"""


STORE_JS = r"""
/* ============================================================================
   智能下载
   ----------------------------------------------------------------------------
   要解决的是「下载慢」和「一键下全部会互相排队等建连」两件事。做法全部建立
   在实测上，而不是「多线程一定快」这种直觉。下面是三个决定性的事实。

   ① 每个 GitHub 连接的吞吐是**固定**的，多开连接不增加总带宽。
      同一个 58.3 MB 的包，开 1 / 2 / 4 条并发连接，总吞吐都是 ~6.2 MB/s。
      → 所以这里**不做「多线程下载大文件」**。它在这个网络条件下没有收益，
        写上去只是好看。

   ② 但单个连接的快慢严重依赖文件大小：
        58.3 MB（iceScribe）  每个连接 2.4 MB/s
         7.8 MB（ModelScope） 每个连接 2.1 MB/s
         0.3 MB（MusicFusion）每个连接 1.3 MB/s
        0.17 MB（iceBrowser） 每个连接 0.9 MB/s
        0.07 MB（KayaGo）     每个连接 0.78 MB/s
      小包慢在建连（TTFB 0.3~1.3s），不是慢在带宽。
      → 所以**并行发起多个小包有真实收益**：8 条连接的总吞吐是各自之和，
        而不是把 8 次建连的等待串起来。这是本页唯一站得住的加速手段。

   ③ 镜像之间实测差 50 倍以上，而且谁快谁慢完全看当时当地：
        gh-proxy.com  5.9 MB/s
        ghfast.top    4.6 MB/s
        ghproxy.net   0.09 MB/s
      → 所以不写死任何一个。但选源**不能靠测速**，原因见下。

   ---------------------------------------------------------------------------
   一个踩过的坑，值得写在这里，免得以后有人再走一遍：

   最初的实现是「用 fetch + Range 并发探测 _blank 各候选，选最快的」。
   实测下来是假的——**所有候选都探不通**。理由是 CORS：
   GitHub Release 的下载地址会 302 到 release-assets.githubusercontent.com，
   而那一跳**不带 Access-Control-Allow-Origin**；三个反代同样不带。
   也就是说：<b>浏览器根本读不到下载响应的字节数，v=0 恒成立</b>。
   那种实现做出来的效果是「永远选官方直连，还多花 4 次请求」，比不做还慢。

   顺带一个反直觉的结论：探针的**成败**其实是有信息量的。
   fetch 失败只说明「缺 CORS 头」，**不代表镜像挂了**——实测失败的候选，
   用 <a> 去下照样 200 拿到完整文件。所以「哪个镜像能 fetch 通」不能当可用性判断。

   于是改成现在这套：**不测速，直接并行下载**。理由很直接——
   并行本来就是瓶颈所在（见②），它不需要知道谁快；
   而下载全速跑起来之后，用户其实也不需要那点选源优化了。
   少一层猜测，少一次等待，也少四个必然失败的请求。
   ============================================================================ */
(function(){
  var CFG = window.__DL || {};
  var MIRRORS = CFG.mirrors || [];
  var MAX_PARALLEL = 5;
  /* 优先用官方直连：没有中间人，也不依赖任何第三方服务活着。
     第三方前缀保留在配置里，但只作为显式的备选项，不作为默认路径。 */
  var PREFERRED = 'direct';

  var box = document.getElementById('bulk');
  if(!box) return;

  function mirrorById(id){
    for(var i=0;i<MIRRORS.length;i++) if(MIRRORS[i].id===id) return MIRRORS[i];
    return null;
  }
  function accelerate(url, m){
    /* 空前缀 = 官方直连，原样返回 */
    if(!m || !m.prefix) return url;
    return m.prefix + url;
  }

  var queue = document.getElementById('queue'),
      bar = queue && queue.querySelector('.bar i'),
      num = queue && queue.querySelector('.n'),
      now = queue && queue.querySelector('.qn'),
      nextBtn = queue && queue.querySelector('[data-more]'),
      quit = false, cursor = 0, timer = null;

  var apps = [];
  document.querySelectorAll('[data-apk]').forEach(function(el){
    apps.push({
      url: el.getAttribute('data-apk'),
      name: el.getAttribute('data-apk-name') || 'apk',
      size: parseInt(el.getAttribute('data-apk-size') || '0', 10)
    });
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
  function fire(app, m){
    var a = document.createElement('a');
    a.href = accelerate(app.url, m);
    a.download = app.name;
    a.rel = 'noopener';
    /* 必须挂进 DOM 再点：部分移动端浏览器对游离节点不理会 */
    document.body.appendChild(a); a.click();
    setTimeout(function(){ a.remove(); }, 0);
  }

  function tick(){
    if(quit) return;
    if(cursor >= apps.length){
      if(bar) bar.style.width = '100%';
      if(now) now.textContent = '已发起全部 ' + apps.length + ' 个下载。若系统只放行了部分，点「继续」补齐剩下的。';
      if(nextBtn) nextBtn.style.display = 'none';
      paint();
      return;
    }
    /* 并发发起：一条连接一个包。这是这里唯一的加速手段——
       实测单连接吞吐固定，串行只会把 N 次建连的等待叠起来。 */
    var burst = 0;
    while(burst < MAX_PARALLEL && cursor < apps.length){
      fire(apps[cursor], mirrorById(PREFERRED));
      cursor++; burst++;
      paint();
    }
    if(now) now.textContent = '已并行发起 ' + cursor + ' / ' + apps.length + ' 个下载…';
    timer = setTimeout(tick, cursor < apps.length ? 1500 : 200);
  }

  function start(){
    quit = false; show();
    if(nextBtn) nextBtn.style.display = 'none';
    if(bar) bar.style.width = '0%';
    cursor = 0; paint();
    timer = setTimeout(tick, 60);
  }

  box.addEventListener('click', function(e){
    var t = e.target.closest ? e.target.closest('[data-bulk]') : null;
    if(t) start();
  });
  if(queue){
    if(nextBtn) nextBtn.addEventListener('click', function(){
      quit = false;
      nextBtn.style.display = 'none';
      timer = setTimeout(tick, 300);
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
})();
"""

def page(site, title, body, depth=0, search=False, store=False, mirrors=None):
    prefix = "../" * depth
    extra = f"<script>{SEARCH_JS}</script>" if search else ""
    if store:
        extra += f"<script>window.__DL={json.dumps(mirrors or {}, ensure_ascii=False)}</script>"
        extra += f"<script>{STORE_JS}</script>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(site['desc'])}">
<meta name="color-scheme" content="dark light">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(site['desc'])}">
<meta property="og:type" content="website">
<link rel="stylesheet" href="{prefix}style.css">
</head>
<body>
<header class="top"><div class="wrap">
<span class="brand">🧊 <em>ice</em> 工坊</span>
<nav>
<a href="{prefix}index.html">全部项目</a>
<a href="{prefix}store.html">应用商店</a>
<a href="https://github.com/{site['author']}">GitHub</a>
</nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
{esc(site['tagline'])} · 站点由 <code>scripts/build_site.py</code> 从 <code>data/projects.py</code> 生成（零依赖、纯静态）。<br>
<a href="https://github.com/{site['author']}">{site['author']} on GitHub</a>
</div></footer>
{extra}
</body>
</html>"""


def badge(text, kind):
    return f'<span class="badge {kind}">{esc(text)}</span>'


def build(site, groups, projects, mirrors=None):
    # 可安装集合先算：首页 hero 与商店页都要用，不能等商店页渲染完才知道
    apps = [p for p in projects if p["installable"]]
    n_apps = len(apps)
    total = sum(p["size_bytes"] for p in apps)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "style.css").write_text(CSS, encoding="utf-8")

    # ---- 搜索索引 ----
    search = []
    for p in projects:
        text = " ".join([p["summary"], p["group_label"], " ".join(p["tags"]),
                         " ".join(t for t, _ in p["metrics"]),
                         " ".join(h[0] + " " + h[1] for h in p["highlights"]),
                         " ".join(p["tech"])])
        search.append({
            "title": p["name"], "group": p["group_label"], "tags": p["tags"],
            "summary": p["summary"], "text": text, "url": p["url"],
        })
    (OUT / "search.json").write_text(json.dumps(search, ensure_ascii=False), encoding="utf-8")

    by_group = {}
    for p in projects:
        by_group.setdefault(p["group"], []).append(p)

    # ---- 首页 ----
    n_release = sum(1 for p in projects if p["dl_release"])
    n_zero = sum(1 for p in projects if "零依赖" in p["tags"] or "零权限" in p["tags"] or "零广告" in p["tags"])
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
            cards.append(
                f'<a class="card" href="{p["url"]}">'
                f'<div class="t">{esc(p["name"])}</div>'
                f'<div class="p">{p["pitch"]}</div>'
                f'<div class="badges">{badges}</div>'
                f'</a>'
            )
        sections.append(
            f'<section class="group" id="{slug}"><div class="gh">'
            f'<h2>{esc(label)}</h2><span>{esc(desc)}</span></div>'
            f'<div class="cards">{"".join(cards)}</div></section>'
        )

    body = f"""<div class="hero">
<p class="kicker">{esc(site['tagline'])}</p>
<h1>{esc(site['name'])}</h1>
<p class="lead">{esc(site['desc'])}</p>
<div class="actions">
<a class="btn primary" href="store.html">🧊 打开应用商店（{n_apps} 个可安装）</a>
</div>
</div>
<div class="stats">
<div><b>{len(projects)}</b>个作品</div>
<div><b>{n_release}</b>个可直接下载</div>
<div><b>0</b>个 fork</div>
<div><b>0</b>个第三方依赖（口径见各项目页）</div>
</div>
<input id="q" class="searchbox" type="search" placeholder="搜索 {len(projects)} 个项目（名称 / 简介 / 技术栈）…" autocomplete="off">
<div id="results"></div>
""" + "\n".join(sections)
    (OUT / "index.html").write_text(page(site, f"{site['name']} · {site['tagline']}", body, 0, search=True),
                                   encoding="utf-8")

    # ---- 各项目页 ----
    for i, p in enumerate(projects):
        st, kind = STATUS_LABEL.get(p["status"], ("", ""))
        metrics = "".join(f'<div><b>{esc(v)}</b><span>{esc(k)}</span></div>' for k, v in p["metrics"])
        hls = "".join(f'<li><b>{esc(t)}</b><span>{esc(d)}</span></li>' for t, d in p["highlights"])
        techs = "".join(f'<span class="badge">{esc(t)}</span>' for t in p["tech"])
        limits = "".join(f"<li>{esc(x)}</li>" for x in p.get("known_limits", []))
        limits_block = (
            f'<div class="note"><b>已知限制</b><ul>{limits}</ul></div>' if limits else ""
        )
        actions = []
        if p["dl_release"]:
            actions.append(f'<a class="btn primary" href="{p["dl_release"]}">⬇ 下载最新 APK</a>')
        if p.get("external_url"):
            actions.append(f'<a class="btn" href="{p["external_url"]}">{esc(p["external_label"])}</a>')
        actions.append(f'<a class="btn" href="{p["repo_url"]}">源码仓库</a>')
        if p["dl_release"]:
            actions.append(f'<a class="btn" href="{p["releases_url"]}">全部版本</a>')

        prev_p = projects[i - 1] if i > 0 else None
        next_p = projects[i + 1] if i + 1 < len(projects) else None
        pager = ['<div class="pager">']
        pager.append(f'<a href="{prev_p["url"]}">← {esc(prev_p["name"])}</a>' if prev_p else "<span></span>")
        pager.append(f'<a style="text-align:right" href="{next_p["url"]}">{esc(next_p["name"])} →</a>' if next_p else "<span></span>")
        pager.append("</div>")

        b = f"""<div class="crumb"><a href="index.html">全部项目</a> / {esc(p['group_label'])}</div>
<div class="phead">
<h1>{esc(p['name'])}</h1>
<div class="sub">{p['pitch']}</div>
<div>{badge(st, kind)}{' '.join(badge(t, '') for t in p['tags'])}</div>
<p style="margin-top:1.1em">{esc(p['summary'])}</p>
<div class="actions">{''.join(actions)}</div>
<div class="metrics">{metrics}</div>
</div>
<h2>技术亮点</h2>
<ul class="hl">{hls}</ul>
{limits_block}
<h2>技术栈</h2>
<div class="tech">{techs}</div>
{''.join(pager)}"""
        (OUT / f'{p["id"]}.html').write_text(page(site, f'{p["name"]} · {site["name"]}', b), encoding="utf-8")

    # ---- 应用商店 ----
    build_store(site, groups, projects, mirrors)

    # 404 兜底（GitHub Pages 会用它）
    body404 = ('<div class="hero"><h1>页面不存在</h1>'
               '<p class="lead">链接可能已经变了。回首页看看全部项目。</p>'
               '<div class="actions"><a class="btn primary" href="index.html">回到首页</a></div></div>')
    (OUT / "404.html").write_text(page(site, "404 · " + site["name"], body404), encoding="utf-8")

    # CNAME：GitHub Pages 绑定自定义域名的唯一凭据
    (OUT / "CNAME").write_text(site["domain"] + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    return len(projects), n_apps, total

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
               f'data-apk="{p["dl_release"]}" data-apk-name="{esc(p["repo"])}.apk" '
               f'data-apk-size="{p["size_bytes"]}">⬇ {p["size_text"] or "下载"}</a>'
               f'<a class="btn" href="{prefix}{p["url"]}">详情</a>')
        cls = "app"
    else:
        act = (f'<a class="btn" href="{p["repo_url"]}">去仓库</a>'
               f'<a class="btn" href="{prefix}{p["url"]}">详情</a>')
        cls = "app none"

    badges = "".join(badge(t, "") for t in p["tags"][:2]) + badge(st, kind)
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
    # 透明地把「有哪些第三方下载源」写出来。把下载流量交给反代是个该知情的决定，
    # 所以列清单，并且说明默认走官方直连。
    mirror_rows = ""
    for m in (mirrors or {}).get("mirrors", []):
        tag = ('<span class="badge ok">默认</span>' if m["default"]
               else '<span class="badge">备选</span>')
        mirror_rows += (f'<tr><td>{esc(m["label"])}</td>'
                        f'<td>{tag}</td>'
                        f'<td><code>{esc(m["prefix"]) or "（直连，无前缀）"}</code></td></tr>')

    bulk = f"""<div class="bulk" id="bulk">
<div class="row">
<div class="grow">
<b>一次下齐全部 {len(apps)} 个应用</b>
<span>共 <span class="tot">{human_size(total_bytes)}</span>。
这些包会<b>并行发起</b>（每批 {5} 个），而不是一个个排队等建连——小包慢就慢在建连上，
并行之后总速度是几条连接之和。中途可停，断哪个重下哪个。</span>
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
下面 {len(apps)} 个安装包全部来自本账号各仓库的 GitHub Release，
版本号、体积、发布时间都是构建时从 Release 元数据里取的，不是写死的文案。
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
这里没有服务端、也没有 CDN，就是 GitHub 在发文件。能优化的只有<b>「怎么下」</b>，
不是<b>「从哪下」</b>——下面把实测数字和取舍都摊开说，包括一个做错了又撤掉的做法。
</p>
<details class="help">
<summary>① 为什么不吹「多线程下载大文件」</summary>
<p style="margin-top:.9em">
因为实测<b>不成立</b>。同一个 58.3 MB 的包，在同一个网络里开不同数量的并发连接：
</p>
<table class="mirrors">
<thead><tr><th>并发连接</th><th>总吞吐</th><th>用时</th></tr></thead>
<tbody>
<tr><td>1 条</td><td>6.25 MB/s</td><td>14.8 s</td></tr>
<tr><td>4 条（分块下载）</td><td>5.98 MB/s</td><td>9.8 s</td></tr>
</tbody>
</table>
<p>
瓶颈不在「浏览器只开了一条连接」——<b>每条连接的吞吐是固定的</b>，多开连接不增加总带宽。
所以这里没有多线程下载。写上去只是好看，不会变快。
</p>
</details>

<details class="help">
<summary>② 那真正的加速点是什么</summary>
<p style="margin-top:.9em"><b>并行建连。</b>单个连接的速度严重依赖文件大小：</p>
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
小包慢在<b>建连</b>（实测 TTFB 0.3~1.3 秒），不是慢在带宽——包越大，建连那点耗时占比越小。
所以页面把这些包<b>并行发起</b>：8 个包的总吞吐就是 8 条连接各自之和，
而不是把 8 次建连的等待串起来。这是这个网络条件下唯一站得住的加速。
</p>
</details>

<details class="help">
<summary>③ 一个做错了又撤掉的做法（关于第三方下载源）</summary>
<p style="margin-top:.9em">
另一个思路是「换个镜像下」。实测这些反代之间能差 <b>50 倍以上</b>，而且谁快谁慢完全看当时当地：
</p>
<table class="mirrors">
<thead><tr><th>下载源</th><th>实测单连接</th><th>状态</th></tr></thead>
<tbody>
<tr><td>GitHub 官方</td><td>6.2 MB/s</td><td><span class="badge ok">默认</span></td></tr>
<tr><td>gh-proxy.com</td><td>5.9 MB/s</td><td><span class="badge">备选</span></td></tr>
<tr><td>ghfast.top</td><td>4.6 MB/s</td><td><span class="badge">备选</span></td></tr>
<tr><td>ghproxy.net</td><td>0.09 MB/s</td><td><span class="badge">备选</span></td></tr>
</tbody>
</table>
<p>
那为什么不「自动选最快的源」？因为做过，<b>而且做错了</b>，值得写下来：
最初用 <code>fetch</code> 并发探测每个候选，想按实测速度挑最快的。结果是
<b>四个候选一个都读不到数据</b>。原因是 CORS：GitHub Release 会 302 到
<code>release-assets.githubusercontent.com</code>，而那一跳不带
<code>Access-Control-Allow-Origin</code>，三个反代同样不带。浏览器读不到字节数，
也就无法计时——所谓「测速」永远是 0。
</p>
<p>
更糟的是它<b>看起来是能用的</b>：探针全部失败之后会「退回官方直连」，
页面照常下完文件，用户不会察觉。区别只是白花了 4 次请求，而且那个「智能选源」从来没生效过。
</p>
<p style="color:var(--muted);font-size:.9em">
顺带一个反直觉的点：探针 <code>fetch</code> 失败只说明「缺 CORS 头」，
<b>不代表镜像挂了</b>——实测失败的候选，用浏览器直接下照样是 200 完整文件。
所以「能不能 fetch 通」不能当可用性判断，这也正是它不适合做选源依据的原因。
</p>
<p style="color:var(--warn)">
<b>所以默认只走 GitHub 官方。</b>非官方源意味着你的下载请求会经过别人的服务器——
这是该由你决定的事，不该由页面替你默认开启。四个源都列在上面，配置在仓库的
<code>data/mirrors.py</code> 里，你可以在自己的网络里测出更快的那个再用。
</p>
</details>

<h2 id="speed">下载速度</h2>
<p style="color:var(--muted);font-size:.9rem;max-width:64ch">
页面会在开始批量下载前<b>实测几个下载源的速度</b>，把最快的那个用在这一次下载上。
选出来的结果存在你自己的浏览器里，下次直接用；换网络、换时间会自动重测。
所有探测都是在你本地对下载地址取 96 KB 计时，<b>不经过本站</b>——这里是纯静态托管，没有服务端，
也不会收到你的任何数据。
</p>
<details class="help">
<summary>它到底怎么加速的（以及为什么不吹「多线程」）</summary>
<p style="margin-top:.9em">
这里没有「多线程下载大文件」这种东西，因为实测<b>不成立</b>：同一个包开 1 / 2 / 4 条
并发连接，总吞吐都是 ~6.2 MB/s，说明瓶颈不在「浏览器只开了一条连接」。
所以那个数字不好看也不吹。
</p>
<p>真实的加速点有两个：</p>
<ol>
<li><b>并行建连。</b>小包每个连接的速度被建连等待拖住（实测 TTFB 0.3~1.3 秒，
大包 2.1 MB/s、小包只有 0.7~0.9 MB/s）。把包并行发起，总吞吐就是多条连接之和，
而不是把 8 次建连的等待串起来。</li>
<li><b>换源。</b>同一个文件在不同反代上实测能差 50 倍以上（5.9 MB/s ↔ 0.09 MB/s），
而且谁快谁慢完全看当时当地。所以不写死任何一个，每次都测一次再选。</li>
</ol>
<p style="color:var(--warn)">
<b>关于第三方下载源（需要你知情）</b>：非官方源意味着你的下载请求会经过别人的服务器。
默认只走 GitHub 官方；只有在官方直连也慢、你打开了加速的情况下才使用它们。
任何一个源探不通，都会自动退回官方直连——加速永远不会变成新的失败点。
</p>
<table class="mirrors">
<thead><tr><th>下载源</th><th>状态</th><th>地址前缀</th></tr></thead>
<tbody>{mirror_rows}</tbody>
</table>
<p style="color:var(--muted);font-size:.86em">
这张表来自仓库里的 <code>data/mirrors.py</code>，是构建时渲染的——不是写死在本页里的。
某个镜像挂掉了，删掉那一行就好，前端会自动少一个候选。
</p>
</details>
<div class="queue" id="queue">
<div class="qh"><span>批量下载</span><span class="n">0 / 0</span>
<button class="qx qmore" type="button" data-more="1" style="display:none;color:var(--accent);border-color:#19405a">继续</button>
<button class="qx qstop" type="button">停止</button></div>
<div class="bar"><i></i></div>
<div class="qn">准备中…</div>
</div>"""

    (OUT / "store.html").write_text(
        page(site, f"{site['store_name']} · {site['name']}", body, 0, store=True, mirrors=mirrors),
        encoding="utf-8")

def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    OUT = Path(args.out)
    site, groups, projects, mirrors = load()
    n, n_apps, total = build(site, groups, projects, mirrors)
    print(f"构建完成：{n} 个项目 → {OUT}")
    print(f"应用商店：{n_apps} 个可安装包，共 {human_size(total)}")
    print(f"首页：{OUT / 'index.html'}")
    print(f"CNAME：{site['domain']}")


if __name__ == "__main__":
    main()
