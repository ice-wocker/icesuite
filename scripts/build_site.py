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


def load():
    ns = {}
    exec((DATA / "projects.py").read_text(encoding="utf-8"), ns)
    site = ns.get("SITE", SITE)
    groups = ns.get("GROUPS", GROUPS)
    projects = ns["PROJECTS"]
    gmap = {k: (k, label, desc) for k, label, desc in groups}
    for p in projects:
        p["dl_release"] = (
            f"https://github.com/{site['author']}/{p['repo']}/releases/latest/download/{p['release_asset']}"
            if p.get("release_asset") else None
        )
        p["repo_url"] = f"https://github.com/{site['author']}/{p['repo']}"
        p["releases_url"] = f"https://github.com/{site['author']}/{p['repo']}/releases"
        p["url"] = f"{p['id']}.html"
        p["group_label"] = gmap[p["group"]][1]
    return site, groups, projects


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


def page(site, title, body, depth=0, search=False):
    prefix = "../" * depth
    extra = f"<script>{SEARCH_JS}</script>" if search else ""
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


def build(site, groups, projects):
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

    # 404 兜底（GitHub Pages 会用它）
    body404 = ('<div class="hero"><h1>页面不存在</h1>'
               '<p class="lead">链接可能已经变了。回首页看看全部项目。</p>'
               '<div class="actions"><a class="btn primary" href="index.html">回到首页</a></div></div>')
    (OUT / "404.html").write_text(page(site, "404 · " + site["name"], body404), encoding="utf-8")

    # CNAME：GitHub Pages 绑定自定义域名的唯一凭据
    (OUT / "CNAME").write_text(site["domain"] + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    return len(projects)


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    OUT = Path(args.out)
    site, groups, projects = load()
    n = build(site, groups, projects)
    print(f"构建完成：{n} 个项目 → {OUT}")
    print(f"首页：{OUT / 'index.html'}")
    print(f"CNAME：{site['domain']}")


if __name__ == "__main__":
    main()
