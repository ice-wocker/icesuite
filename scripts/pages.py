# -*- coding: utf-8 -*-
"""站点新增页面的渲染器。

每个函数只做一件事：把已经算好的数据渲染成 HTML 片段，返回 (title, body, kwargs)。
主题判断、导航、页脚这些外壳仍由 build_site.page() 负责 —— 在这里再实现一遍
就会有两套 <head>，而那正是「一张页面漏了 canonical」这类问题的来源。

所有文案都遵守同一条规则：**说这个页面凭什么这么说**。
「12 个可安装」旁边要能指到快照；「v2.7.1 发布于 2026-11-02」要能点进 Release。
做不到就不写。
"""
from __future__ import annotations

import json
import re

from overlay import plain, rich
from util import attr, esc, human_size

# 状态徽章的样式键 → 展示用的词。和 build_site.STATUS_LABEL 保持同步，
# 但复制一份在这里是**故意的**：那个常量描述「项目状态」，
# 这个描述「体检结果」，两者将来会分开演进。
LEVEL = {"ok": ("正常", "ok"), "warn": ("注意", "warn"),
         "info": ("说明", "info"), "archived": ("已归档", "warn")}


def _ilink(p, prefix=""):
    return f'<a href="{prefix}{p["url"]}">{esc(p["name"])}</a>'


def _short(html_text, limit=26):
    """把一句带行内标签的介绍压成一行。

    直接切片会在「135M int4 模型塞进包 / 里，清单里没有 INTERNET 权限」这种位置
    断开 —— 中文没有词边界，切在哪儿都可能是半个词。所以按标点断句，
    取第一段完整的；第一段还超长，才硬截并加省略号。
    """
    text = plain(html_text).strip()
    for sep in ("，", "。", "；", "：", "(", "（", " — "):
        if sep in text and len(text.split(sep)[0]) <= limit:
            return text.split(sep)[0]
    return text[:limit] + ("…" if len(text) > limit else "")


def _badge(t, k=""):
    return f'<span class="badge {k}">{esc(t)}</span>'


# --------------------------------------------------------------- 最新更新
def latest_page(site, projects, tl, base=""):
    """按发版时间倒序的扁平列表。

    和首页的「最近更新」区别：首页只给 3 条（那是钩子），这里给全部，
    并且**带分组**——同一个项目连发三版时，能一眼看出是同一个项目在迭代，
    而不是三个新包。所以按日期分块，块内保留项目名。
    """
    rows = [r for r in tl if r["date"]]
    by_date = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    blocks = []
    last_month = None
    for date in sorted(by_date, reverse=True):
        month = date[:7]
        if month != last_month:
            blocks.append(f'<h2 class="tlmonth" id="m-{month}">{esc(month)}'
                          f' <span class="fine">{len([d for d in by_date if d[:7] == month])} 天有发布</span></h2>')
            last_month = month
        items = []
        for r in by_date[date]:
            proj = next((p for p in projects if p["id"] == r["id"]), None)
            pre = _badge("pre", "warn") if r["prerelease"] else ""
            note = f' <span class="fine">{esc(r["note"])}</span>' if r["note"] else ""
            asset = f' <code class="fine">{esc(r["asset"])}</code>' if r["asset"] else ""
            link = (f'<a href="{base}{proj["url"]}">{esc(proj["name"])}</a>' if proj
                    else esc(r["name"]))
            items.append(f'<li><span class="ver">{esc(r["tag"])}</span> {link}{pre}{note}{asset}</li>')
        blocks.append(f'<ul class="latestlist">{"".join(items)}</ul>')

    months = sorted({d[:7] for d in by_date}, reverse=True)
    jump = "".join(f'<a class="pill" href="#m-{m}">{m}</a>' for m in months[:12])
    body = f"""<div class="hero">
<h1>最新更新</h1>
<p class="lead">全部 {len(rows)} 个版本按发布日期倒序。数据来自各仓库 GitHub Release 的
<code>published_at</code>，不是「最后修改时间」——改 README 不会出现在这里，发版才会。</p>
</div>
<div class="filterbar">{jump}</div>
{''.join(blocks) if blocks else '<p class="empty">快照里还没有任何带日期的 Release。</p>'}
<p class="fine" style="margin-top:2em">想看某个项目的完整版本史，去它的详情页；想看所有项目摆在一起，
去 <a href="{base}timeline.html">时间线</a>。这里缺一条？说明那个 Release 没写日期（GitHub 允许草稿），本站不猜。</p>"""
    return f"最新更新 · {site['name']}", body, {"len": len(rows)}


# --------------------------------------------------------------- 时间线
def timeline_page(site, projects, tl, base=""):
    """一条竖向时间线：年份 → 月份 → 版本。

    为什么值得单独一页：把 40 个版本摊平之后，看到的是**节奏**——
    哪个月在集中发版、哪些项目发完就停了。这是首页和详情页都给不出的信息，
    而它完全由已有数据决定，不需要任何新输入。
    """
    years = {}
    for r in tl:
        if not r["year"]:
            continue
        years.setdefault(r["year"], {}).setdefault(r["month"], []).append(r)

    max_month = max((len(v) for y in years.values() for v in y.values()), default=1)
    out = []
    for y in sorted(years, reverse=True):
        total_y = sum(len(v) for v in years[y].values())
        out.append(f'<h2 id="y-{y}">{y} 年 <span class="fine">{total_y} 个版本</span></h2>')
        for m in sorted(years[y], reverse=True):
            items = years[y][m]
            # 条形宽度按当月数量归一化到 12 格。它是「相对密度」，不是绝对值，
            # 所以旁边必须写出数字——只有条形的图会让人以为是下载量。
            bar = "▍" * max(1, round(len(items) / max_month * 12))
            rows = []
            for r in items:
                proj = next((p for p in projects if p["id"] == r["id"]), None)
                link = (f'<a href="{base}{proj["url"]}">{esc(proj["name"])}</a>' if proj
                        else esc(r["name"]))
                pre = _badge("pre", "warn") if r["prerelease"] else ""
                rows.append(f'<li><span class="day">{esc(r["date"][8:10])}</span> '
                            f'<span class="ver">{esc(r["tag"])}</span> {link}{pre}</li>')
            out.append(f'<div class="tlrow"><div class="tlhead">'
                       f'<b>{esc(m)}</b><span class="fine">{len(items)} 个版本</span>'
                       f'<span class="tlbar" aria-hidden="true">{bar}</span></div>'
                       f'<ul>{"".join(rows)}</ul></div>')

    n_pre = sum(1 for r in tl if r["prerelease"])
    body = f"""<div class="hero">
<h1>发版时间线</h1>
<p class="lead">{len(tl)} 个版本、跨度 {len(years)} 年。每一条都对应一个真实的 GitHub Release，
点项目名进详情页能看到那一版的正文。右侧短条表示当月发版数量（{n_pre} 个是预发布）。</p>
</div>
{''.join(out) if out else '<p class="empty">快照里还没有可排进时间线的版本。</p>'}"""
    return f"时间线 · {site['name']}", body, {"len": len(tl)}


# --------------------------------------------------------------- 对比
def compare_page(site, projects, groups, base=""):
    """同类项目横向对比表。

    每个分组一张表，列是**能在一行里读完的事实**：版本、体积、要求系统、ABI、
    发版时间、标签。不列「评分」「推荐度」这类需要我替你下结论的列。

    表头可点排序 —— 纯前端，不依赖任何库，也不改变 URL（排序不是导航状态，
    把它写进 URL 会让「返回」变成回退排序，而不是离开页面）。
    """
    apps = [p for p in projects if p["installable"]]
    by_group = {}
    for p in projects:
        by_group.setdefault(p["group"], []).append(p)

    tables = []
    for slug, label, desc in groups:
        items = by_group.get(slug) or []
        if len(items) < 2:
            # 1 个项目的「对比」没有信息量，不为了填满版面而造一张表
            continue
        head = ("<tr><th>项目</th><th data-sort='text'>当前版本</th>"
                "<th data-sort='num'>体积</th><th data-sort='text'>最低系统</th>"
                "<th>ABI</th><th data-sort='text'>发版日期</th><th>标签</th></tr>")
        rows = []
        for p in items:
            dl = (f'<a class="btn small" href="{attr(p["dl_release"])}">下载</a>'
                  if p["installable"] else '<span class="fine">无安装包</span>')
            rows.append(
                f'<tr data-size="{p["size_bytes"]}">'
                f'<td>{_ilink(p, base)}<div class="fine">{esc(_short(p["pitch"]))}</div></td>'
                f'<td class="mono">{esc(p.get("version") or "—")}</td>'
                f'<td class="mono" data-v="{p["size_bytes"]}">{p["size_text"] or "—"}</td>'
                f'<td class="mono">{("Android " + p["min_android"] + "+") if p.get("min_android") else "—"}</td>'
                f'<td class="mono fine">{esc(p.get("arch") or "—")}</td>'
                f'<td class="mono">{esc(p.get("published_at") or "—")}</td>'
                f'<td>{"".join(_badge(t) for t in p["tags"][:3])}</td></tr>')
        tables.append(
            f'<section class="cmpset"><h2>{esc(label)} <span class="fine">{len(items)} 个</span></h2>'
            f'<p class="fine">{esc(desc)}</p>'
            f'<div class="tablewrap"><table class="cmp"><thead>{head}</thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')

    body = f"""<div class="hero">
<h1>横向对比</h1>
<p class="lead">同一分组下的项目摆在一起。只有 2 个以上项目的分组才会出现在这里——
一个项目的「对比表」只是换个方式的介绍页。表头可点排序。</p>
<p class="fine">列里每一项都来自快照：版本 = 最新 Release 的 tag，体积 = 那个 APK 的字节数，
最低系统 / ABI = 手写叠加层（构建时不做 APK 解析）。没写的显示「—」，不填猜测值。</p>
</div>
{''.join(tables) if tables else '<p class="empty">没有 2 个以上项目的分组。</p>'}"""
    return f"对比 · {site['name']}", body, {"len": len(tables)}


# --------------------------------------------------------------- 集合
def collections_page(site, cats, projects, base=""):
    """策展集合页。规则见 insight.collection_catalog —— 全部按当前快照生成。"""
    byid = {p["id"]: p for p in projects}
    blocks = []
    for c in cats:
        cards = []
        for pid in c["items"]:
            p = byid.get(pid)
            if not p:
                continue
            tags = "".join(_badge(t) for t in p["tags"][:2])
            cards.append(
                f'<div class="card reveal">'
                f'<a class="cardhit" href="{base}{p["url"]}" data-rv aria-label="{attr(p["name"])}"></a>'
                f'<div class="t"><a href="{base}{p["url"]}">{esc(p["name"])}</a></div>'
                f'<div class="p">{rich(p["pitch"])}</div>'
                f'<div class="badges">{tags}{_badge(p["size_text"]) if p["size_text"] else ""}</div>'
                f'</div>')
        rule = (f'<div class="rule"><b>入选规则</b><code>{esc(c["rule"])}</code></div>'
                if c.get("rule") else "")
        blocks.append(
            f'<section class="group" id="{esc(c["id"])}">'
            f'<div class="gh"><h2>{esc(c["title"])}</h2>'
            f'<span>{esc(c["desc"])}</span></div>{rule}'
            f'<div class="cards">{"".join(cards)}</div></section>')

    jump = "".join(f'<a class="pill" href="#{esc(c["id"])}">{esc(c["title"])} '
                   f'<b>{len(c["items"])}</b></a>' for c in cats)
    body = f"""<div class="hero">
<h1>集合</h1>
<p class="lead">{len(cats)} 个集合，全部由当前快照<b>算</b>出来的，不是手写的清单。
这意味着它们会随数据变化：某个项目归档、停止发版、或者新开一个仓库，集合自己就跟着变，
不会出现「精选里挂着一个去年就停更的项目」。</p>
<p class="fine">每个集合下面标了入选规则——你可以在 <code>data/registry.json</code> 里
逐条核对这个项目为什么在这里。</p>
</div>
<div class="filterbar">{jump}</div>
{''.join(blocks)}"""
    return f"集合 · {site['name']}", body, {"len": len(cats)}


# --------------------------------------------------------------- 数据
def stats_page(site, st, projects, base=""):
    """站点自己的数据页。所有数字都能追到 stats.json。"""
    t = st["totals"]
    months = st["by_month"]
    peak = max(months.values(), default=1)
    bars = "".join(
        f'<div class="mbar" title="{esc(m)}：{n} 个版本">'
        f'<i style="height:{max(3, round(n / peak * 100))}%"></i>'
        f'<span>{esc(m[5:])}</span></div>'
        for m, n in months.items())

    langs = "".join(
        f'<tr><td>{esc(k)}</td><td class="mono">{v}</td>'
        f'<td><span class="lbar" style="width:{round(v / max(1, max(st["by_language"].values())) * 100)}%"></span></td></tr>'
        for k, v in st["by_language"].items())

    sizes = st["sizes"]
    size_rows = "".join(
        f'<tr><td>{esc(s["name"])}</td><td class="mono">{esc(s["version"] or "—")}</td>'
        f'<td class="mono">{human_size(s["size"])}</td>'
        f'<td class="mono">{s["size"]} B</td></tr>'
        for s in sizes)

    dl = st["downloads"]
    dl_rows = "".join(
        f'<tr><td>{esc(d["name"])}</td><td class="mono">{d["downloads"]}</td>'
        f'<td class="mono">{esc(d["version"] or "—")}</td></tr>' for d in dl) or \
        '<tr><td colspan="3" class="fine">快照里所有资产的下载计数都是 0（或拿不到）。</td></tr>'

    body = f"""<div class="hero">
<h1>数据</h1>
<p class="lead">这一页没有新数据，它就是 <a href="{base}stats.json">stats.json</a> 的排版。
数字全部来自 <code>data/registry.json</code> 快照，快照由流水线从 GitHub API 同步。</p>
<p class="fine">快照时间 {esc(st["generated_at"])}。看不惯谁的数字，去 GitHub 上核对——它改不了。</p>
</div>
<div class="stats">
<div><b>{t["projects"]}</b>个仓库</div>
<div><b>{t["installable"]}</b>个可安装</div>
<div><b>{human_size(t["release_bytes"])}</b>全部安装包合计</div>
<div><b>{t["releases"]}</b>个版本</div>
<div><b>{t["releases_with_notes"]}</b>个写了更新说明</div>
<div><b>{t["downloads"]}</b>次下载</div>
<div><b>{t["tags"]}</b>个标签</div>
<div><b>{t["handwritten"]} / {t["auto"]}</b>手写 / 自动收录</div>
</div>

<h2>每月发版数</h2>
<div class="bars">{bars}</div>
<p class="fine">按 Release 的 <code>published_at</code> 统计。柱高是相对值，数值在悬停提示与
stats.json 的 <code>by_month</code> 里。</p>

<h2>语言分布</h2>
<div class="tablewrap"><table class="cmp"><thead><tr><th>语言</th><th>仓库数</th><th></th></tr></thead>
<tbody>{langs}</tbody></table></div>
<p class="fine">这是仓库的 <b>primary language</b>（GitHub 按字节数判定），不是代码行数——
后者要 clone 才能算，而本站构建时不许联网。</p>

<h2>安装包体积（从小到大）</h2>
<div class="tablewrap"><table class="cmp"><thead><tr><th>项目</th><th>版本</th><th>体积</th><th>字节</th></tr></thead>
<tbody>{size_rows}</tbody></table></div>
<p class="fine">字节数是 Release 资产的 <code>size</code> 字段原值，不是「约 X MB」的换算结论。</p>

<h2>下载量</h2>
<div class="tablewrap"><table class="cmp"><thead><tr><th>项目</th><th>次数</th><th>当前版本</th></tr></thead>
<tbody>{dl_rows}</tbody></table></div>
<p class="fine">GitHub 的 <code>download_count</code> 只统计 Release 资产的直链下载，
不含镜像站转发、不含别人<br>自己 clone 后重新打包发出去的量。所以它只会偏小，不会偏大。</p>

<h2>本站自己的体积</h2>
<p class="fine">见 <a href="{base}content.json">content.json</a> 的 <code>build</code> 字段：
产物总字节数、页面数、以及每个文件的 sha256。站点主张「体积可验证」，那就把自己也放上去。</p>"""
    return f"数据 · {site['name']}", body, {"stats": t}


# --------------------------------------------------------------- 项目页增强块
def health_block(p, h):
    """项目详情页的「体检」区块。

    它不是评分，是把「这个项目现在是什么状态」用可核实的事实说清楚。
    每一条都给出读者可以自己去 GitHub 上验证的那一步。
    """
    rows = []
    for c in h["checks"]:
        label, kind = LEVEL.get(c["level"], ("", ""))
        rows.append(f'<li>{_badge(label, kind)}<b>{esc(c["title"])}</b>'
                    f'<span>{esc(c["detail"])}</span></li>')
    since = h.get("since_release_days")
    age = h.get("age_days")
    meta = []
    if age is not None:
        meta.append(f"仓库存在 {age} 天")
    if since is not None:
        meta.append(f"距最新发版 {since} 天")
    meta_html = (f'<p class="fine">{" · ".join(meta)}（按快照里的建仓时间与发版时间相减，'
                 '不估算未来）</p>') if meta else ""
    return f'<h2>体检</h2><ul class="hl health">{"".join(rows)}</ul>{meta_html}'


def related_block(p, projects, base=""):
    """「相关项目」：同分组 + 标签交集。

    为什么值得有：从搜索结果落到详情页的人，往往想找的是「跟它像的另一个」。
    排序规则写死在这里而不是随机：先按共享标签数，再按同分组，最后按名字——
    保证同一个输入永远得到同一个顺序（构建可复现）。
    """
    mine = set(p["tags"])
    scored = []
    for q in projects:
        if q["id"] == p["id"]:
            continue
        shared = len(mine & set(q["tags"]))
        same = 1 if q["group"] == p["group"] else 0
        if not shared and not same:
            continue
        scored.append((-shared, -same, q["name"], q))
    scored.sort(key=lambda x: x[:3])
    picks = [q for *_, q in scored[:4]]
    if not picks:
        return ""
    cards = "".join(
        f'<a class="relcard" href="{base}{q["url"]}"><b>{esc(q["name"])}</b>'
        f'<span>{rich(q["pitch"])[:70]}</span></a>' for q in picks)
    return f'<h2>相关项目</h2><div class="relgrid">{cards}</div>'


# --------------------------------------------------------------- 静态 JS
COMPARE_JS = r"""
/* 表头排序。纯前端、无依赖，且**不改 URL** —— 排序不是导航状态，
   写进 hash 会让「返回」变成回退排序而不是离开页面。 */
(function(){
  var tables = document.querySelectorAll('table.cmp');
  for (var t = 0; t < tables.length; t++) {
    (function(tb){
      var ths = tb.querySelectorAll('thead th[data-sort]');
      for (var i = 0; i < ths.length; i++) {
        (function(th, idx){
          th.classList.add('sortable');
          th.addEventListener('click', function(){
            var body = tb.querySelector('tbody');
            var rows = Array.prototype.slice.call(body.querySelectorAll('tr'));
            var dir = th.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc';
            for (var j = 0; j < ths.length; j++) ths[j].removeAttribute('data-dir');
            th.setAttribute('data-dir', dir);
            var numeric = th.getAttribute('data-sort') === 'num';
            var col = Array.prototype.indexOf.call(th.parentNode.children, th);
            rows.sort(function(a, b){
              var av = a.children[col].getAttribute('data-v') || a.children[col].textContent.trim();
              var bv = b.children[col].getAttribute('data-v') || b.children[col].textContent.trim();
              var r;
              if (numeric) {
                r = (parseFloat(av) || 0) - (parseFloat(bv) || 0);
              } else {
                r = String(av).localeCompare(String(bv), 'zh-Hans-CN');
              }
              return dir === 'asc' ? r : -r;
            });
            for (var k = 0; k < rows.length; k++) body.appendChild(rows[k]);
          });
        })(ths[i], i);
      }
    })(tables[t]);
  }
})();
"""
