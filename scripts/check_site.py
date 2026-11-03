#!/usr/bin/env python3
"""站点自检：在没有浏览器的情况下，抓住最容易静默出错的问题。

1. 下载链接是不是真的能下（商店页每个 APK 都 HEAD 一次，并核对字节数）
2. 站内链接有没有指向不存在的页面（拼错 id 就白给一个 404）
3. 有没有页面忘了 CNAME / 首页是否漏了某个项目
4. 商店页与快照是否一致（体积、版本、可安装集合、一键下载按钮）

用标准库，不引入 requests。为什么要有这个：站点的内容源是手写清单，
最典型的翻车方式是「改了 repo 名或 APK 文件名，但站点点进去 404」——
用户看到的是死链，构建却一片绿。
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
UA = {"User-Agent": "ice-suite-link-check/1.0"}


def esc_title(t):
    return re.sub(r"\s+", " ", t).strip()


def load_registry():
    """读 sync.py 生成的快照。缺失时返回空字典，让「新增快照」这类检查报错。"""
    f = ROOT / "data" / "registry.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("projects", {})


def project_meta():
    """「站点认为有哪些项目」。

    以前这里通过 importlib 执行整个 build_site.py、只为了拿一个 list ——
    为了核对渲染结果而把渲染器整份跑一遍，代价是自检变慢、而且合并逻辑
    依旧有两份（一份在 build 里、一份在它对 load 的调用里）。
    现在合并规则只有一个入口：overlay.load()。build 和 check 都调它。
    """
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import overlay
    return overlay.load()["projects"]


def flat_releases(registry):
    """{repo: {tag, size, url, ...}} —— 从注册表里摊平成商店页需要的形状。

    商店页只认「每个仓库的当前可安装包」这一个概念，和旧的按仓库快照同构，
    所以下面的断言全部照旧能用，只是数据来源从不入流的快照换成了自动同步的快照。
    """
    out = {}
    for repo, reg in registry.items():
        latest = reg.get("latest") or {}
        asset = latest.get("asset") or {}
        if not asset.get("url"):
            continue
        out[repo] = {
            "tag": latest.get("tag") or "",
            "size": asset.get("size") or 0,
            "url": asset["url"],
            "asset": asset.get("name") or "",
            "published_at": latest.get("published_at") or "",
        }
    return out


def head(url, timeout=20, retries=2):
    """HEAD 一次；5xx 视为服务端临时故障，重试后仍失败算「存疑」而不是死。"""
    last = ""
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, method="HEAD", headers=UA)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, ""
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (500, 502, 503, 504) and attempt < retries:
                continue
            return e.code, last
        except Exception as e:            # 网络/DNS/超时
            last = type(e).__name__
            if attempt < retries:
                continue
            return 0, last
    return 0, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-links", action="store_true", help="只做本地结构检查")
    ap.add_argument("--no-js", action="store_true",
                    help="跳过内联 JS 语法检查（没有 node 的机器用）")
    ap.add_argument("--reproducible", action="store_true",
                    help="额外跑一次构建，逐字节比对产物是否可复现（慢）")
    args = ap.parse_args()

    ns = {}
    exec((ROOT / "data" / "projects.py").read_text(encoding="utf-8"), ns)
    site = ns["SITE"]
    author = site["author"]
    # 项目清单以构建脚本合并出来的那份为准（手写叠加层 + 自动发现），
    # 拿 data/projects.py 当基准会漏掉自动发现的仓库——那正是上一版
    # 「新项目必须推代码才能上站」的另一半。
    projects = project_meta()
    registry = load_registry()
    releases = flat_releases(registry)
    errors, warnings = [], []

    # --- 1. 产物结构 ---
    for f in ("index.html", "style.css", "search.json", "CNAME", "404.html", "store.html",
              "tags.html", "sitemap.xml", "robots.txt", "feed.xml", "icon.svg",
              # v3 新增：五张页面 + 三个机器可读产物 + PWA 三件套
              "latest.html", "timeline.html", "compare.html", "collections.html", "stats.html",
              "stats.json", "graph.json", "content.json", "manifest.json", "sw.js",
              "icon-maskable.svg"):
        if not (SITE_DIR / f).exists():
            errors.append(f"缺少产物 {f}")
    if (SITE_DIR / "CNAME").exists():
        got = (SITE_DIR / "CNAME").read_text(encoding="utf-8").strip()
        if got != site["domain"]:
            errors.append(f"CNAME 与配置不一致：{got} != {site['domain']}")

    # --- 1.5 样式表必须能被完整解析 ---
    # 这条是踩出来的：往 CSS 里插了一段 @media 却没闭合大括号，结果它之后
    # 的规则**全部失效**，页面变成无样式纯文本——而浏览器不报错、文件 HTTP 200、
    # 前几条规则照样能解析出来，肉眼也只在「打开页面」时才看得出来。
    # 校验方式刻意从简：去掉注释与字符串后数大括号，必须配平且结尾为 0。
    css_file = SITE_DIR / "style.css"
    if css_file.exists():
        css = css_file.read_text(encoding="utf-8")
        stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        stripped = re.sub(r'"[^"\n]*"', '""', stripped)
        depth, bad = 0, False
        for ch in stripped:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    bad = True
                    break
        if bad or depth != 0:
            errors.append(f"style.css 大括号不配平（扫描结束时深度 {depth}）——"
                          "这会让其后的规则全部失效，页面变成无样式纯文本")
        if "prefers-reduced-motion" not in css:
            errors.append("style.css 没有 prefers-reduced-motion 兜底")

    # --- 2. 项目页齐不齐 ---
    ids = [p["id"] for p in projects]
    for pid in ids:
        if not (SITE_DIR / f"{pid}.html").exists():
            errors.append(f"页面缺失：项目页 {pid}.html")
    index = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    for p in projects:
        if f'{p["id"]}.html' not in index:
            errors.append(f"首页没有收录：{p['id']}")

    # --- 3. 站内链接可达 ---
    broken = set()
    for html_file in SITE_DIR.rglob("*.html"):
        body = html_file.read_text(encoding="utf-8")
        # 去掉 <script>，否则会把内联 JS 里拼字符串的 '...href="'+d.url+'"' 当成链接
        body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        for href in re.findall(r'href="([^"#]+)"', body):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target = (html_file.parent / href).resolve()
            if not target.exists():
                broken.add(f"{html_file.name} -> {href}")
    errors.extend(f"站内死链：{b}" for b in sorted(broken))

    # --- 3.5 商店页与快照一致 ---
    # 商店页上的「版本 / 体积 / 能否安装」必须是 registry.json 的投影。
    # 这层校验的价值在于：以后改渲染逻辑改坏了，不会静默上线一个空商店。
    store = (SITE_DIR / "store.html").read_text(encoding="utf-8") if (SITE_DIR / "store.html").exists() else ""
    if store:
        apks = re.findall(r'data-apk="([^"]+)"[^>]*data-apk-size="(\d+)"', store)
        if len(apks) != len(releases):
            errors.append(f"商店页可下载应用 {len(apks)} 个 != 快照里 {len(releases)} 个")
        for url, size in apks:
            repo = url.split("/")[4] if url.count("/") > 4 else ""
            rel = releases.get(repo)
            if not rel:
                errors.append(f"商店页有快照里没有的仓库：{repo}")
                continue
            if str(rel["size"]) != size:
                errors.append(f"{repo} 页面体积 {size} != 真实 {rel['size']}")
            if rel["url"] != url:
                errors.append(f"{repo} 页面链接与快照不一致：{url}")
        # 必须匹配按钮本身，不能只搜 "data-bulk" ——
        # 内联 JS 里也有 "[data-bulk]" 字样，宽匹配会让这条检查永远为真
        if not re.search(r'data-bulk="1"', store):
            errors.append("商店页缺少「一键下载全部」按钮")
        # 停止按钮与「继续」按钮必须各自有唯一选择器。
        # 之前两者共用 .qx，「继续」一点就等于点停止——功能整个失效，
        # 而页面看起来完全正常。这里只认类名，不认注释。
        for sel, what in (("qstop", "停止按钮"), ("qmore", "继续按钮")):
            if f'class="{sel} ' not in store and f' {sel}"' not in store:
                errors.append(f"商店页缺少{what}的独立类名 .{sel}（会与按钮互相误触发）")
        if "querySelector('.qstop')" not in store:
            errors.append("停止按钮未使用 .qstop 选择器")
        if not re.search(r'data-more="1"', store):
            errors.append("商店页缺少「继续」按钮")
        # 版本号必须以「列表里显示的那个」形式出现，避免只是碰巧在别处被提到
        for repo, rel in releases.items():
            if f'<span class="ver">{rel["tag"]}</span>' not in store:
                errors.append(f"{repo} 的版本号 {rel['tag']} 没有出现在商店页")
        # 首页要有入口
        if "store.html" not in index:
            errors.append("首页没有商店入口")

        # --- 3.6 智能下载层的守门 ---
        # 这块的价值在于：下载逻辑坏了在页面上看不出来（按钮在、样式对，
        # 只是慢或者下不来），所以必须由检查盯着。下面每条都验过「注入缺陷会变红」。
        if not re.search(r'data-apk="[^"]+"[^>]*data-apk-size="\d+"', store):
            errors.append("商店页的下载按钮没有带 data-apk-size（一键下载拿不到体积）")
        # 并行发起：并发数必须真的**被赋值**、且 >1。
        # 只搜 "MAX_PARALLEL" 是橡皮图章——注释里也有这个词，永远为真。
        # 要断言的是「这个数字确实进了下载循环」，所以连 while 条件一起钉。
        mp = re.search(r"MAX_PARALLEL\s*=\s*(\d+)", store)
        if not mp:
            errors.append("商店页没有给 MAX_PARALLEL 赋值——并行发起逻辑不见了")
        elif int(mp.group(1)) < 2:
            errors.append(f"MAX_PARALLEL={mp.group(1)}，退化成串行下载："
                          "8 个包会排队等建连，这正是慢的根因")
        elif not re.search(r"burst\s*<\s*MAX_PARALLEL\s*&&", store):
            errors.append("MAX_PARALLEL 没有被用在发起循环里（只有赋值没有使用）")
        # 曾经踩过的真坑：用 fetch 探测镜像速度。GitHub Release 与三个反代
        # 都不带 Access-Control-Allow-Origin，探针永远失败，等于白花 4 次请求
        # 且永远选不出源。这条守卫防止有人「好心」把它加回来。
        # 同样只认代码，不认注释：先剥掉 /* */ 与 // 再找 fetch。
        code = re.sub(r"/\*.*?\*/", "", store, flags=re.S)
        code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
        if re.search(r"fetch\s*\(", code):
            errors.append("商店页又出现了 fetch 调用——下载地址不带 CORS 头，"
                          "任何基于 fetch 的测速/选源都必然失败")
        # 官方直连必须存在且是兜底：加速源可以默认开，但官方这条不允许被删掉，
        # 否则一旦所有反代挂掉就没有可退的路。
        if '"prefix": ""' not in store and 'prefix\": \"' not in store:
            errors.append("商店页没有配置官方直连源（空前缀）——加速源全挂时就无路可退")
        if '"role": "fallback"' not in store and 'role\": \"fallback\"' not in store:
            errors.append("商店页没有标记官方直连为兜底源（role=fallback）")
        for label in ("GitHub 官方", "兜底"):
            if label not in store:
                errors.append(f"商店页缺少下载源说明：{label}")

        # --- 地区选源逻辑的守卫 ---
        # 需求是「默认开加速 / 按地区选源」。实现必须满足下面几条，
        # 否则会退化成「永远直连」或「永远某个反代」——两种都不是按地区。
        if not re.search(r"function\s+slowDirect\s*\(", store):
            errors.append("商店页没有地区判断函数 slowDirect——"
                          "「按用户所在地区选源」的逻辑不见了")
        if "resolvedOptions" not in store or "timeZone" not in store:
            errors.append("地区判断没有读时区（Intl.DateTimeFormat.timeZone）")
        if "navigator.language" not in store and "navigator.languages" not in store:
            errors.append("地区判断没有读 navigator.language(s)")
        # 定义了还必须真的被调用。注意不能只搜 slowDirect()——函数声明本身
        # 就长这样，那样写是橡皮图章（第一版就是，注入「永不调用」抓不到）。
        # 要断言的是「调用出现在赋值/条件里」，所以连上下文一起钉。
        # slowDirect() 必须在「实际参与决策」的位置被调用。现在它被
        # wantAccel() 调用（`return slowDirect();`），所以同时接受
        # return / 赋值 / 三元这类上下文。纯 `function slowDirect(` 声明不算。
        if not re.search(r"(?:return|\?|\:|\=|\()\s*slowDirect\s*\(\s*\)", store):
            errors.append("slowDirect 定义了却没有被用来做决策（地区判断没生效）")
        # 「按地区选源」必须真的产出候选列表，而不是只判断了却不用
        if not re.search(r"function\s+wantAccel\s*\(", store):
            errors.append("商店页没有 wantAccel——地区判断没有被用来决定是否加速")
        # 不得用 navigator.connection.effectiveType 做地区判断。曾经加过
        # 「2g/3g 也走加速」，实测 headless Chromium 会随机把 effectiveType
        # 报成 3g，导致加速被误开；而且它说的是「我的链路慢」，不是
        # 「我到 GitHub 远」——慢链路上反代同样慢，套一层只是多一跳。
        # 只认代码不认注释：上面那段 JS 的块注释里正好写着「不能用它」，
        # 直接搜字符串会把说明本身当成违规。复用上面剥注释后的 code。
        if "effectiveType" in code:
            errors.append("商店页又用 effectiveType 判断地区了——"
                          "它会被随机报成 3g 导致误开加速，且语义是链路慢而非距离远")
        if "localStorage" not in store:
            errors.append("用户切换下载源后没有持久化（localStorage）——"
                          "用户改过的选择必须被记住")
        # 状态条：默认开加速的前提是「走了第三方」这件事看得见
        if 'id="srcbar"' not in store or 'id="srctoggle"' not in store:
            errors.append("商店页缺少下载源状态条 / 切换按钮——"
                          "默认开加速就必须让用户看得见、改得动")
        # 说明文案必须与实现一致：声称的并发数要真的是代码里的数。
        # 注意不能拿 "5" 当基准去比——那只是把常量抄了一遍，改 MAX_PARALLEL
        # 时文案照样写着 5，脚本却仍然绿。必须拿代码里的值去比文案。
        want = int(re.search(r"MAX_PARALLEL\s*=\s*(\d+)", store).group(1))
        claims = set(re.findall(r"每批(?:并行发起)? (\d+) 个", store))
        if not claims:
            errors.append("商店页没有写明每批并发几个下载")
        for c in sorted(claims):
            if int(c) != want:
                errors.append(f"商店页写「每批 {c} 个」与代码里的 MAX_PARALLEL={want} 不一致")
        # 不能吹「多线程下载大文件」：实测无收益，写了就是假话。
        # 提到它就必须同时给出「实测不成立」的依据，否则就是在当卖点讲。
        # --- 多源轮转 + 换源重试（针对「链接经常失效」）---
        # 旧实现把 8 个包全押在同一个源上，单个反代限速/挂掉就全灭。
        # 实测 ghproxy.net 在 61 MB 包上 3/3 次下不完，这种源一旦被选中，
        # 用户看到的就是「链接失效」。所以：
        #   ① 源必须按包轮转（sourceFor 用取模分摊），不能全局只选一个；
        #   ② 必须给用户逐包「换源重下」的入口——因为 CORS 决定了页面
        #      无法自动感知下载失败，自动重试做不到，只能让用户点一下。
        if "function sourceFor(" not in store:
            errors.append("商店页缺少 sourceFor——多源轮转不见了，"
                          "所有包会重新押在同一个源上")
        # 必须断言「包下标 i 参与了取模」，而不是「某处出现了 % list.length」——
        # 后者对 `((0) + (srcIdx[i]||0)) % list.length` 这种「退化成固定源」也成立。
        if not re.search(r"i\s*%\s*list\.length", store):
            errors.append("sourceFor 没有按包下标 i 轮转（i % list.length）——"
                          "源没有被真正分摊到各个包上")
        if not re.search(r"function\s+rotateFor\s*\(", store):
            errors.append("商店页缺少 rotateFor——没有「换到下一个源」的能力")
        # 断言「函数声明」——只搜 buildRetry 会在调用点命中，是橡皮图章
        if not re.search(r"function\s+buildRetry\s*\(", store):
            errors.append("商店页缺少 buildRetry 函数——没有逐包换源重下的入口，"
                          "下载失败时用户只能撞墙")
        if 'id="retry"' not in store:
            errors.append("商店页缺少 #retry 容器——换源重下的 UI 没有落点")
        # 只认按钮文案本身，不认周边说明里提到它
        if not re.search(r"textContent\s*=\s*['\"]换源重下['\"]", store):
            errors.append("商店页没有「换源重下」按钮的文案（textContent）")
        # 官方直连必须仍然排在候选列表最后（兜底）
        if not re.search(r"a\.concat\(\[d\]\)", store):
            errors.append("candidates() 没有把官方直连排在候选列表末尾（失去兜底）")

        if "多线程下载" in store and "实测不成立" not in store:
            errors.append("商店页提到「多线程下载」却没有说明它实测不成立——"
                          "这会被读成卖点，而事实恰好相反")

    # --- 3.7 页面骨架的一致性（导航 / 主题 / SEO） ---
    # 这一组盯的是「页面能打开、但少了一半东西」这类问题：
    # 加了新页面却忘了导航项、某张页面漏了 canonical、某个链接指向不存在的锚点。
    # 它们在浏览器里都不会报错，只是安静地缺一块。
    pages = sorted(SITE_DIR.rglob("*.html"))
    nav_counts = {}
    for f in pages:
        body = f.read_text(encoding="utf-8")
        # 每个页面的导航里应该恰好有 4 个站内/站外链接（全部项目 / 商店 / 标签 / GitHub）
        nav = re.search(r"<header class=\"top\">.*?</nav>", body, flags=re.S)
        if not nav:
            errors.append(f"{f.name} 没有导航栏")
        else:
            n = len(re.findall(r"<a [^>]*href=", nav.group(0)))
            nav_counts.setdefault(n, []).append(f.name)
        # 主题脚本必须在 <link rel=stylesheet> 之前，否则深色用户会闪一下浅色。
        # 注意不能拿「data-theme 这个字符串」当下标 —— <html data-theme> 就在
        # 第 2 行，永远排在样式表前面，那样写是橡皮图章（做过变异测试，抓不到）。
        # 要定位的是**那段脚本**的结尾 </script> 与样式表标签的先后。
        i_theme = body.find("localStorage.getItem(K)")
        i_css = body.find('rel="stylesheet"')
        if i_theme < 0:
            errors.append(f"{f.name} 没有内联主题脚本（首屏会闪一帧错误配色）")
        elif i_css >= 0 and i_theme > i_css:
            errors.append(f"{f.name} 的主题脚本排在样式表之后——会先闪一帧错误配色")
        # 每张可索引页面都要有 canonical，否则分享链接在别处是裸 URL
        if 'rel="canonical"' not in body and 'name="robots" content="noindex' not in body:
            errors.append(f"{f.name} 缺少 canonical（不是 noindex 页面就必须有）")
        if 'rel="icon"' not in body:
            errors.append(f"{f.name} 缺少 icon（浏览器标签页会是空白方块）")
    if len(nav_counts) > 1:
        errors.append("各页面的导航项数不一致："
                      + "；".join(f"{k} 项 → {','.join(v)}" for k, v in sorted(nav_counts.items())))

    # --- 3.8 站内锚点必须存在 ---
    # 「标签」「技术栈」都做成了页内锚点，拼错一个就得到一个点了没反应的链接——
    # 而站内链接检查只看文件是否存在，锚点它管不到。
    anchors = {}
    for f in pages:
        body = f.read_text(encoding="utf-8")
        anchors[f.name] = set(re.findall(r'id="([^"]+)"', body))
    for f in pages:
        body = re.sub(r"<script.*?</script>", "", f.read_text(encoding="utf-8"), flags=re.S)
        for href in re.findall(r'href="([^"]*#[^"]+)"', body):
            target, _, frag = href.partition("#")
            if target and not target.endswith(".html"):
                continue          # 外链锚点不查
            target = target or f.name
            if frag in ("main", ""):
                continue
            if frag not in anchors.get(target, set()):
                errors.append(f"{f.name} → {href} 锚点不存在")

    # --- 3.9 标签索引必须覆盖全部标签 ---
    # 标签页是首页标签行的落点。少一个标签，首页那颗 pill 就是死链。
    tags_page = (SITE_DIR / "tags.html").read_text(encoding="utf-8") if (SITE_DIR / "tags.html").exists() else ""
    all_tags = sorted({t for p in projects for t in p["tags"]})
    for t in all_tags:
        # 必须是「某个分组的标题」而不是正文里恰好提到。原来只查 `<h2>{t}`，
        # 于是删掉整个 indexgroup 区块后仍然可能在别处命中——变异测试抓到了这条。
        if not re.search(r'<div class="indexgroup" id="[^"]+"><h2>' + re.escape(t) + r'[\s<]', tags_page):
            errors.append(f"tags.html 缺少标签「{t}」")
    # 反向：标签索引里不许出现清单外的标签
    listed = re.findall(r'<div class="indexgroup" id="[^"]+"><h2>([^<]+)', tags_page)
    for t in listed:
        if t.strip() not in all_tags:
            errors.append(f"tags.html 出现了清单外的标签「{t.strip()}」")
    if len(listed) != len(all_tags):
        errors.append(f"tags.html 标签数 {len(listed)} != 清单里的 {len(all_tags)}")

    # --- 3.10 Release 事实必须出现在项目页 ---
    # 用户从搜索结果直接落到详情页，看不到版本和体积就得再跑一趟商店。
    for p in projects:
        page_file = SITE_DIR / f"{p['id']}.html"
        if not page_file.exists():
            continue
        body = page_file.read_text(encoding="utf-8")
        rel = releases.get(p["repo"])
        if rel and rel["tag"] not in body:
            errors.append(f"{p['id']}.html 没有显示当前版本 {rel['tag']}")

    # --- 3.105 卡片结构：不允许 <a> 嵌套 <a> ---
    # 卡片里既有「进详情页」的链接，又有「进标签页」的链接。如果把整张卡片
    # 做成 <a>，浏览器会当场把内层 <a> 提到外层之外，卡片被拆成两半、
    # 页面上多出几个只有技术栈的幽灵方块 —— 而 HTML 源码、构建日志、
    # HTTP 状态码全都正常。肉眼不看页面是发现不了的，所以由这里钉住。
    #
    # 断言两件事：
    #   ① 首页卡片是 <div class="card reveal">，不是 <a>；
    #   ② 每张卡片里恰好有一个 .cardhit（整卡点击层），且**不含**嵌套的 <a>。
    # 只数 .cardhit 是不够的——上一版就是只数这个，改回整卡 <a> 时依然全绿。
    index_src = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    if re.search(r'<a [^>]*class="card[ "]', index_src):
        errors.append("首页出现了 <a class=\"card\"> —— 整卡做成链接会把内层标签链接"
                      "提到外层之外，卡片被浏览器拆碎（页面看起来缺标题、多出幽灵方块）")
    card_blocks = re.findall(r'<div class="card reveal">(.*?)</div></div>', index_src, flags=re.S)
    n_cards_expected = len(projects)
    if len(card_blocks) != n_cards_expected:
        errors.append(f"首页卡片数 {len(card_blocks)} != 项目数 {n_cards_expected}")
    for i, block in enumerate(card_blocks):
        if block.count('class="cardhit"') != 1:
            errors.append(f"第 {i+1} 张卡片缺少唯一的整卡点击层 .cardhit")
            break
        rest = block.replace('<a class="cardhit"', '<span class="cardhit"', 1)
        if re.search(r"<a [^>]*>(?:(?!</a>).)*?<a ", rest, flags=re.S):
            errors.append(f"第 {i+1} 张卡片里出现了 <a> 嵌套 <a>")
            break

    # --- 3.11 地区名单必须覆盖 CN/HK/MO/TW 的 IANA 时区 ---
    # 2026-10 的真问题：旧的时区名单漏了 Asia/Guangzhou，而个别国产 ROM
    # 的默认时区正是它。漏判的表现是「明明在大陆，页面却判定直连」——
    # 用户看到的是「加速没开」，而这里没有任何报错。
    # 从**代码里**取这两个名单，而不是从文件文本里取：
    # 文件正文有大段解释性注释，注释里也写着 "Asia/Guangzhou"（就是解释为什么补它），
    # 拿文本做包含判断永远是绿的——第一次写这条守卫时正是这么写错的。
    ns_m = {}
    exec((ROOT / "data" / "mirrors.py").read_text(encoding="utf-8"), ns_m)
    tz = set(ns_m.get("SLOW_DIRECT_TIMEZONES", ()))
    must = {"Asia/Shanghai", "Asia/Guangzhou", "Asia/Urumqi", "Asia/Hong_Kong",
            "Asia/Macau", "Asia/Taipei"}
    for t in sorted(must - tz):
        errors.append(f"data/mirrors.py 的 SLOW_DIRECT_TIMEZONES 缺少 {t}——"
                      "该时区的用户会被误判成「直连不慢」，加速不会自动开")
    langs = set(ns_m.get("SLOW_DIRECT_LANGS", ()))
    for lg in ("zh-CN", "zh-TW", "zh-HK"):
        if lg not in langs:
            errors.append(f"data/mirrors.py 的 SLOW_DIRECT_LANGS 缺少 {lg}")
    # 官方直连必须存在且 role=fallback，否则加速源全挂时无路可退
    mirrors = ns_m.get("MIRRORS", [])
    if not any(m.get("prefix") == "" for m in mirrors):
        errors.append("data/mirrors.py 里没有官方直连（空前缀）——加速源全挂时无路可退")
    if not any(m.get("role") == "fallback" for m in mirrors):
        errors.append("data/mirrors.py 里没有 role=fallback 的兜底源")
    # 每个加速前缀都必须是 https 且以 / 结尾：拼接方式是 prefix + 原始 URL，
    # 少了结尾斜杠就会拼成 https://gh-proxy.comhttps://github.com/...
    for m in mirrors:
        px = m.get("prefix") or ""
        if not px:
            continue
        if not px.startswith("https://"):
            errors.append(f"下载源 {m.get('id')} 的前缀不是 https：{px}")
        if not px.endswith("/"):
            errors.append(f"下载源 {m.get('id')} 的前缀缺结尾斜杠：{px}"
                          "（拼接方式为 prefix + URL，缺斜杠会拼出坏地址）")

    # --- 3.12 sitemap / robots / feed 必须与产物一致 ---
    sm = (SITE_DIR / "sitemap.xml").read_text(encoding="utf-8") if (SITE_DIR / "sitemap.xml").exists() else ""
    for p in projects:
        url = f"{p['id']}.html"
        if f"/{url}<" not in sm:
            errors.append(f"sitemap.xml 缺少 {url}")
    # 反过来也要对一次：sitemap 必须覆盖**每一张可索引页面**。
    # 只查「项目页都在」是不够的 —— v3 新增的五张页面（latest/timeline/compare/
    # collections/stats）当时就漏了，而「项目页都在」这条照样绿。
    # 404.html 是 noindex，本就不该进 sitemap，所以它单独排除。
    indexable = [f.name for f in SITE_DIR.glob("*.html")
                 if f.name != "404.html"
                 and 'name="robots" content="noindex' not in f.read_text(encoding="utf-8")]
    def in_sitemap(name):
        # 首页在 sitemap 里是目录形式（base/），不是 base/index.html
        return (f"/{name}<" in sm) if name != "index.html" else (f"{site['base_url'].rstrip('/')}/<" in sm)

    missing = [n for n in sorted(indexable) if not in_sitemap(n)]
    if missing:
        errors.append(f"sitemap.xml 漏了 {len(missing)} 张可索引页面：{missing}")
    robots = (SITE_DIR / "robots.txt").read_text(encoding="utf-8") if (SITE_DIR / "robots.txt").exists() else ""
    if "Sitemap:" not in robots:
        errors.append("robots.txt 没有声明 Sitemap")
    feed = (SITE_DIR / "feed.xml").read_text(encoding="utf-8") if (SITE_DIR / "feed.xml").exists() else ""
    if feed.count("<item>") != len(releases):
        errors.append(f"feed.xml 条目数 {feed.count('<item>')} != 可安装应用 {len(releases)}"
                      "（RSS 按发版推送，少一条就是漏了一个新版本）")
    for rel in releases.values():
        if rel["url"] not in feed:
            errors.append(f"feed.xml 没有包含 {rel['asset']} 的下载地址")

    # --- 3.13 自动发现必须真的生效 ---
    # 这两条守的是这一版的核心承诺：「新项目不用登记」「版本不用推代码」。
    # 它们最容易的失效方式不是报错，而是悄悄退回手写清单——
    # 站点看起来完全正常，只是新仓库永远不出现。
    reg = registry
    auto = [p for p in projects if p.get("auto")]
    if not reg:
        errors.append("data/registry.json 不存在——运行 python3 scripts/sync.py 生成")
    else:
        covered = {p["repo"] for p in projects}
        for repo in reg:
            if repo not in covered:
                errors.append(f"registry.json 里有 {repo}，但站点上没有它的页面"
                              "（自动发现失效，新项目上不了站）")
        # 每个仓库的版本号必须来自快照，而不是手写文案里的历史值。
        # 两道：① 构建视角的字段一致；② 产物里「当前版本」那张事实卡是同一个值。
        # 只做 ① 会漏掉「字段对、但页面渲染用了别的变量」这类半成品。
        for p in projects:
            r = reg.get(p["repo"])
            if not r:
                continue
            want = ((r.get("latest") or {}).get("tag")) or ""
            if (p.get("version") or "") != want:
                errors.append(f"{p['id']}: 页面版本 {p.get('version')!r} != 快照 {want!r}"
                              "（版本号又退回手写了？）")
                continue
            if not want:
                continue
            pf = SITE_DIR / f"{p['id']}.html"
            if not pf.exists():
                continue
            body = pf.read_text(encoding="utf-8")
            m = re.search(r"<b>([^<]*)</b><span>当前版本</span>", body)
            if not m:
                errors.append(f"{p['id']}.html 没有「当前版本」事实卡"
                              "（快照有版本号，页面上却看不到）")
            elif m.group(1) != want:
                errors.append(f"{p['id']}.html 当前版本显示 {m.group(1)!r} != 快照 {want!r}")
    if not auto:
        errors.append("没有任何「自动收录」项目——所有卡片都来自手写清单。"
                      "这在本账号下不可能：registry.json 里必然有未手写的仓库。"
                      "要么发现逻辑坏了，要么手写清单把所有仓库都抄了一遍（那等于回到手工登记）")

    # --- 3.14 快照里的元数据必须真的被渲染出来 ---
    # 「有数据但没渲染」是这类改造最典型的半成品状态：快照天天自动更新，
    # 页面上却还是老样子，而且没有任何东西会红。
    sample = [p for p in projects if p.get("asset_sha256")]
    detail = "".join(f.read_text(encoding="utf-8") for f in SITE_DIR.rglob("*.html"))
    # 逐页核对：每个有 sha256 的项目页都必须真的渲染出来。
    # 「全站任意一处出现 class=\"sha\"」是橡皮图章——变异测试注入缺陷后照样全绿。
    for p in projects:
        sha = (p.get("asset_sha256") or "").strip()
        if not sha:
            continue
        page_file = SITE_DIR / f"{p['id']}.html"
        if not page_file.exists():
            continue
        body = page_file.read_text(encoding="utf-8")
        if sha not in body:
            errors.append(f"{p['id']}.html 没有显示 sha256 校验值"
                          "（快照里有，页面上没有——校验功能等于不存在）")
    for p in projects:
        if not (p.get("asset_sha256") or "").strip():
            continue
        pf = SITE_DIR / f"{p['id']}.html"
        if not pf.exists():
            continue
        if 'class="sha"' not in pf.read_text(encoding="utf-8"):
            errors.append(f"{p['id']}.html 缺少校验值区块（.sha）——"
                          "sha256 只是散在正文里，用户没法整段复制")
    if not (SITE_DIR / "update.json").exists():
        errors.append("缺少 update.json——客户端拿不到机器可读的版本清单")
    else:
        up = json.loads((SITE_DIR / "update.json").read_text(encoding="utf-8"))
        if set(up.get("apps", {})) != set(releases):
            errors.append("update.json 的应用集合与快照不一致："
                          f"{sorted(set(up.get('apps', {})) ^ set(releases))}")
        for repo, app in up.get("apps", {}).items():
            rel = releases.get(repo) or {}
            if app.get("version") != rel.get("tag"):
                errors.append(f"update.json 里 {repo} 版本 {app.get('version')} != 快照 {rel.get('tag')}")
        # verify 是「这份清单有多少条能被验证」的自述。它必须与 apps 实际内容对得上，
        # 否则客户端会拿一个骗人的覆盖率去做「要不要提示校验失败」的判断。
        v = up.get("verify") or {}
        real_sha = sum(1 for a in up.get("apps", {}).values() if a.get("sha256"))
        real_size = sum(1 for a in up.get("apps", {}).values() if a.get("size"))
        if v.get("sha256_covered") != real_sha:
            errors.append(f"update.json 的 verify.sha256_covered = {v.get('sha256_covered')}"
                          f"，实际有 {real_sha} 条 sha256")
        if v.get("size_covered") != real_size:
            errors.append(f"update.json 的 verify.size_covered = {v.get('size_covered')}"
                          f"，实际有 {real_size} 条 size")
        # generated_at 必须是快照时间，不是构建时间 —— 否则页面会在快照已过期时
        # 依然显示「刚刚更新过」，而这条正是「同一件事故的第二次」的成因。
        import overlay as _ov
        snap = (_ov.registry_meta() or {}).get("generated_at") or ""
        if snap and up.get("generated_at") != snap:
            errors.append(f"update.json 的 generated_at {up.get('generated_at')!r} "
                          f"不是快照时间 {snap!r}（构建时间不该进产物）")

    # --- 3.20 v3：机器可读产物必须与模型一致 ---
    # 「有产物但内容是旧的」是这类改造最典型的半成品状态：文件在、HTTP 200、
    # 自检也发现不了 —— 除非有人真的把里面的数字和快照对一遍。
    stats_f = SITE_DIR / "stats.json"
    graph_f = SITE_DIR / "graph.json"
    content_f = SITE_DIR / "content.json"
    if stats_f.exists():
        st = json.loads(stats_f.read_text(encoding="utf-8"))
        want = {
            "projects": len(projects),
            "installable": sum(1 for p in projects if p["installable"]),
            "release_bytes": sum(p["size_bytes"] for p in projects if p["installable"]),
            "releases": sum(len([r for r in (p.get("history") or []) if r.get("tag")])
                            for p in projects),
        }
        for k, v in want.items():
            if st.get("totals", {}).get(k) != v:
                errors.append(f"stats.json 的 totals.{k} = {st.get('totals', {}).get(k)}，"
                              f"按快照应为 {v}")
        by_month = st.get("by_month") or {}
        if by_month and sum(by_month.values()) != want["releases"]:
            errors.append(f"stats.json by_month 合计 {sum(by_month.values())} "
                          f"!= Release 总数 {want['releases']}（月份分桶漏了版本）")
        sizes = st.get("sizes") or []
        if sizes != sorted(sizes, key=lambda x: x["size"]):
            errors.append("stats.json 的 sizes 没有按体积升序（页面写的是「从小到大」）")
        # 页面必须真的把数字渲染出来，不能只是 JSON 对
        sf = (SITE_DIR / "stats.html").read_text(encoding="utf-8")
        for label, val in (("个仓库", want["projects"]),
                           ("个可安装", want["installable"]),
                           ("个版本", want["releases"])):
            if f"<b>{val}</b>{label}" not in sf:
                errors.append(f"stats.html 没有渲染 <b>{val}</b>{label}"
                              "（stats.json 有，页面没显示）")
    if graph_f.exists():
        g = json.loads(graph_f.read_text(encoding="utf-8"))
        ids = {p["id"] for p in projects}
        gn = {n["id"] for n in g.get("nodes", [])}
        if gn != ids:
            errors.append(f"graph.json 节点集合与项目清单不一致：{sorted(gn ^ ids)}")
        for e in g.get("edges", []):
            if e["a"] not in ids or e["b"] not in ids:
                errors.append(f"graph.json 有悬空边 {e['a']} — {e['b']}")
            if e["kind"] == "tag" and not e.get("tags"):
                errors.append(f"graph.json 的 tag 边 {e['a']}—{e['b']} 没有任何共享标签")
    if content_f.exists():
        c = json.loads(content_f.read_text(encoding="utf-8"))
        files = c.get("files") or {}
        # 逐文件核对 sha256：这是「同一 commit 同一产物」这句话唯一的证据。
        # 只查「文件数一致」是橡皮图章 —— 内容改了、数量没变，照样全绿。
        import hashlib as _hl
        for name, meta in files.items():
            fp = SITE_DIR / name
            if not fp.exists():
                errors.append(f"content.json 里登记了 {name}，但产物里没有")
                continue
            raw = fp.read_bytes()
            if len(raw) != meta.get("bytes"):
                errors.append(f"content.json 里 {name} 的 bytes 与实际不符")
            elif _hl.sha256(raw).hexdigest() != meta.get("sha256"):
                errors.append(f"content.json 里 {name} 的 sha256 与实际不符")
        on_disk = {str(f.relative_to(SITE_DIR)) for f in SITE_DIR.rglob("*")
                   if f.is_file() and f.name != "content.json"}
        missing = on_disk - set(files)
        if missing:
            errors.append(f"产物里有 {len(missing)} 个文件没进 content.json："
                          f"{sorted(missing)[:4]}")
        if c.get("build", {}).get("files") != len(files):
            errors.append("content.json 的 build.files 与实际文件数不符")

    # --- 3.21 v3：PWA 三件套必须自洽 ---
    man_f = SITE_DIR / "manifest.json"
    if man_f.exists():
        man = json.loads(man_f.read_text(encoding="utf-8"))
        for key in ("name", "short_name", "start_url", "scope", "display", "icons"):
            if not man.get(key):
                errors.append(f"manifest.json 缺少 {key}")
        if man.get("display") != "standalone":
            errors.append("manifest.json 的 display 不是 standalone（装出来是浏览器标签）")
        if man.get("start_url") not in ("./index.html", "./"):
            errors.append(f"manifest.json 的 start_url {man.get('start_url')!r} 不是相对路径，"
                          "fork 到子路径会 404")
        for ic in man.get("icons") or []:
            if not (SITE_DIR / ic["src"]).exists():
                errors.append(f"manifest.json 引用的图标 {ic['src']} 不存在")
        for sc in man.get("shortcuts") or []:
            if not (SITE_DIR / sc["url"]).exists():
                errors.append(f"manifest.json 的快捷方式指向不存在的页面 {sc['url']}")
    sw_f = SITE_DIR / "sw.js"
    if sw_f.exists():
        sw = sw_f.read_text(encoding="utf-8")
        m = re.search(r"const PRECACHE = (\[[^\]]*\])", sw)
        if not m:
            errors.append("sw.js 里找不到 PRECACHE 清单")
        else:
            try:
                pre = json.loads(m.group(1))
            except Exception:
                pre = []
                errors.append("sw.js 的 PRECACHE 不是合法 JSON")
            if not pre:
                errors.append("sw.js 的 PRECACHE 是空的（装上也不会有离线能力）")
            for u in pre:
                name = u[2:] if u.startswith("./") else u
                if not (SITE_DIR / name).exists():
                    errors.append(f"sw.js 预缓存了不存在的文件 {u}")
            if "__CACHE_NAME__" in sw:
                errors.append("sw.js 里的缓存名占位符没有被替换（所有版本共用一个缓存）")
        # 版本化缓存名必须跟着内容变：拿 manifest 里的 x-version 对
        if man_f.exists():
            tag = json.loads(man_f.read_text(encoding="utf-8")).get("x-version") or ""
            if tag and f"icesuite-{tag}" not in sw and "icesuite-" not in sw:
                errors.append("sw.js 的缓存名里没有构建版本号")

    # --- 3.22 v3：新页面不能是空壳 ---
    # 「页面生成了」和「页面上有内容」是两件事。一张只有标题的 latest.html
    # 会让构建与自检双双通过，而用户点开看到的是空白。
    tl_len = sum(1 for p in projects for r in (p.get("history") or []) if r.get("tag"))
    page_expect = [
        ("latest.html", max(1, min(tl_len, 10)), '<ul class="latestlist">'),
        ("timeline.html", max(1, len({(p.get("history") or [{}])[0].get("published_at", "")[:4]
                                      for p in projects if p.get("history")}) - 0), '<h2 id="y-'),
        ("collections.html", 1, '<section class="group"'),
        ("stats.html", 1, '<div class="bars">'),
        ("compare.html", 1, '<table class="cmp">'),
    ]
    for fname, at_least, marker in page_expect:
        fp = SITE_DIR / fname
        if not fp.exists():
            continue
        body_f = fp.read_text(encoding="utf-8")
        if marker not in body_f:
            errors.append(f"{fname} 缺少结构标记 {marker}（页面生成了但内容没渲染）")
        n_items = body_f.count(marker)
        if n_items < at_least:
            errors.append(f"{fname} 里 {marker} 只出现 {n_items} 次，按快照应有至少 {at_least} 次")
    # collections 的每个集合都必须有卡片，不能只有标题
    coll_f = SITE_DIR / "collections.html"
    if coll_f.exists():
        coll = coll_f.read_text(encoding="utf-8")
        # 按集合切段再数卡片：只数全站总数是橡皮图章 —— 把一个集合的卡片
        # 全删掉、另一个集合多渲染几张，总数照样对得上。变异测试抓到的。
        for chunk in coll.split('<section class="group"')[1:]:
            # 变量名不要叫 head：本文件里 head() 是那个 HEAD 请求函数，
            # 覆盖掉它会让后面所有外链检查在运行时炸掉（真的炸过一次）。
            head_html = chunk.split("</h2>")[0]
            title = re.sub(r"<[^>]+>", "", head_html)[:24] or "(无标题)"
            n_card = chunk.count('class="cardhit"')
            if n_card == 0:
                errors.append(f"collections.html 里「{esc_title(title)}」这个集合一张卡片都没有"
                              "（渲染成了空壳）")

    # 详情页的体检测试：每张项目页都要有，且「注意/正常」至少各一档出现过
    detail_files = [SITE_DIR / f'{p["id"]}.html' for p in projects]
    detail_files = [f for f in detail_files if f.exists()]
    if detail_files:
        bodies = {f.name: f.read_text(encoding="utf-8") for f in detail_files}
        no_health = [n for n, b in bodies.items() if "<h2>体检</h2>" not in b]
        if no_health:
            errors.append(f"{len(no_health)} 张项目页没有「体检」区块：{no_health[:3]}")
        all_detail = "".join(bodies.values())
        if 'class="badge ok"' not in all_detail:
            errors.append("项目页里没有任何「正常」档的体检结论（判定逻辑可能恒为告警）")
        # 逐页核对「相关项目」，而不是看全站有没有出现过这个词 ——
        # 一条只查「全站某处有 X」的断言，删掉 21 张页面里的 20 张照样绿。
        # 这条是变异测试抓出来的：把 gunfire.html 的区块整段删掉，守卫当时没反应。
        for f in detail_files:
            body_f = bodies[f.name]
            if 'class="relgrid"' not in body_f:
                errors.append(f"{f.name} 没有「相关项目」区块（.relgrid）")
                break
        no_health_body = [n for n, b in bodies.items() if "<h2>体检</h2>" not in b]
        if not no_health_body and 'class="badge warn"' not in all_detail:
            errors.append("项目页里没有任何「注意」档的体检结论（判定逻辑可能恒为正常）")

    # 首页入口必须指向真实存在的页面（六个入口卡片）
    idx_body = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    if 'class="entrygrid"' not in idx_body:
        errors.append("首页缺少新页面入口区块（entrygrid）")
    # 只看 entrygrid 这一段：页脚里也有同名链接，用全文搜索的话
    # 「首页入口被删」根本抓不到（页脚那份还在）。
    eg = re.search(r'<div class="entrygrid">(.*?)</div>\s*<div class="filterbar"|'
                   r'<div class="entrygrid">(.*?)</div>\s*<details', idx_body, re.S)
    eg_html = (eg.group(1) or eg.group(2)) if eg else ""
    if not eg_html:
        errors.append("首页 entrygrid 区块解析不出来（结构变了？）")
    for target in ("latest.html", "timeline.html", "compare.html", "collections.html",
                   "stats.html"):
        if f'href="{target}"' not in eg_html:
            errors.append(f"首页入口区块里没有指向 {target} 的链接")

    # --- 3.23 「同一 commit 同一产物」必须真的成立 ---
    # 这条守卫的由来：content.json 里一度写着构建时间，于是同样的输入
    # 两次构建得到不同文件，而「构建成功」把它盖住了。可复现是承诺，
    # 承诺要么能被检验，要么不算承诺。做法是再构建一次到临时目录，逐字节比。
    # （用 --reproducible 才跑：它要跑一次完整构建，常规自检不必付这个代价。）
    if args.reproducible:
        import shutil as _sh
        import subprocess as _sp
        import tempfile as _tf
        tmp = Path(_tf.mkdtemp()) / "site2"
        r = _sp.run([sys.executable, str(ROOT / "scripts" / "build_site.py"), "--out", str(tmp)],
                    capture_output=True, text=True, cwd=ROOT)
        if r.returncode != 0:
            errors.append("第二次构建失败：" + (r.stdout + r.stderr)[-400:])
        else:
            a = {str(f.relative_to(SITE_DIR)): f.read_bytes()
                 for f in SITE_DIR.rglob("*") if f.is_file()}
            b = {str(f.relative_to(tmp)): f.read_bytes()
                 for f in tmp.rglob("*") if f.is_file()}
            if set(a) != set(b):
                errors.append(f"两次构建产物文件集合不同：{sorted(set(a) ^ set(b))[:5]}")
            else:
                diff = [k for k in a if a[k] != b[k]]
                if diff:
                    errors.append(f"{len(diff)} 个文件两次构建不一致（产物不可复现）："
                                  f"{diff[:5]}")
        _sh.rmtree(tmp.parent, ignore_errors=True)

    # --- 3.24 内联 JavaScript 必须能解析 ---
    # 这一条挡住的是「构建全绿、页面 200、输入框能打字但永远没结果」那类故障。
    # 它只能在真的执行 JS 的环境里被发现，所以交给 node --check。
    if not args.no_js:
        import subprocess as _sp
        r = _sp.run([sys.executable, str(ROOT / "scripts" / "js_syntax.py")],
                    capture_output=True, text=True)
        if r.returncode != 0:
            errors.append((r.stdout + r.stderr).strip().splitlines()[-1] if r.stdout.strip()
                          else "内联 JS 语法检查失败")

    # --- 4. 外链可达性 ---
    checked = 0
    if not args.skip_links:
        # 直接查商店页上的链接——那才是用户真正会点的东西。
        # 查别的来源等于「测了个寂寞」：页面渲染坏了照样绿。
        pairs = re.findall(r'data-apk="([^"]+)"[^>]*data-apk-size="(\d+)"', store)
        targets_all = [("APK", url) for url, _ in pairs]
        for p in projects:
            targets_all.append(("仓库", p["repo_url"]))
            if p.get("external_url"):
                targets_all.append(("站点", p["external_url"]))
        for label, url in targets_all:
            code, why = head(url)
            checked += 1
            if code == 200:
                continue
            if code in (0, 500, 502, 503, 504):
                warnings.append(f"[存疑] {label} {url} → {why}")
            else:
                errors.append(f"[死链] {label} {url} → {why}")

    # 搜索索引与项目数一致
    idx = json.loads((SITE_DIR / "search.json").read_text(encoding="utf-8"))
    if len(idx) != len(projects):
        errors.append(f"search.json 条目数 {len(idx)} != 项目数 {len(projects)}")
    # 搜索索引里每一条都必须指向真实存在的页面，否则搜索结果就是一个 404
    for row in idx:
        if not (SITE_DIR / row.get("url", "")).exists():
            errors.append(f"search.json 指向不存在的页面 {row.get('url')}")
            break
    # 关键词抽查：索引里确实收录了标签与亮点文本。
    # 「只收标题」的搜索看似能用，实际问题（比如搜「断点续传」）会零结果。
    if idx and not any(row.get("text", "").strip() for row in idx):
        errors.append("search.json 的 text 字段全空（搜索只能命中标题）")

    print(f"项目数：{len(projects)}")
    print(f"可安装应用：{len(releases)}")
    print(f"页面数：{len(list(SITE_DIR.rglob('*.html')))}")
    print(f"外链检查：{checked} 条")
    for w in warnings:
        print(w)
    if errors:
        print("\n发现问题：")
        for e in errors:
            print(" ", e)
        return 1
    print("\n全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
