#!/usr/bin/env python3
"""站点自检：在没有浏览器的情况下，抓住最容易静默出错的问题。

1. 下载链接是不是真的能下（商店页每个 APK 都 HEAD 一次，并核对字节数）
2. 站内链接有没有指向不存在的页面（拼错 id 就白给一个 404）
3. 有没有页面忘了 CNAME / 首页是否漏了某个项目
4. 商店页与 releases.json 是否一致（体积、版本、可安装集合、一键下载按钮）

用标准库，不引入 requests。为什么要有这个：站点的内容源是手写清单，
最典型的翻车方式是「改了 repo 名或 APK 文件名，但站点点进去 404」——
用户看到的是死链，构建却一片绿。
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"
UA = {"User-Agent": "ice-suite-link-check/1.0"}


def load_releases():
    f = ROOT / "data" / "releases.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8")).get("releases", {})


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
    args = ap.parse_args()

    ns = {}
    exec((ROOT / "data" / "projects.py").read_text(encoding="utf-8"), ns)
    projects = ns["PROJECTS"]
    site = ns["SITE"]
    author = site["author"]
    for p in projects:
        p.setdefault("repo_url", f"https://github.com/{author}/{p['repo']}")
    releases = load_releases()
    errors, warnings = [], []

    # --- 1. 产物结构 ---
    for f in ("index.html", "style.css", "search.json", "CNAME", "404.html", "store.html"):
        if not (SITE_DIR / f).exists():
            errors.append(f"缺少产物 {f}")
    if (SITE_DIR / "CNAME").exists():
        got = (SITE_DIR / "CNAME").read_text(encoding="utf-8").strip()
        if got != site["domain"]:
            errors.append(f"CNAME 与配置不一致：{got} != {site['domain']}")

    # --- 2. 项目页齐不齐 ---
    ids = [p["id"] for p in projects]
    for pid in ids:
        if not (SITE_DIR / f"{pid}.html").exists():
            errors.append(f"项目页缺失：{pid}.html")
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

    # --- 3.5 商店页与 releases.json 一致 ---
    # 商店页上的「版本 / 体积 / 能否安装」必须是 releases.json 的投影。
    # 这层校验的价值在于：以后改渲染逻辑改坏了，不会静默上线一个空商店。
    store = (SITE_DIR / "store.html").read_text(encoding="utf-8") if (SITE_DIR / "store.html").exists() else ""
    if store:
        apks = re.findall(r'data-apk="([^"]+)"[^>]*data-apk-size="(\d+)"', store)
        if len(apks) != len(releases):
            errors.append(f"商店页可下载应用 {len(apks)} 个 != releases.json 里 {len(releases)} 个")
        for url, size in apks:
            repo = url.split("/")[4] if url.count("/") > 4 else ""
            rel = releases.get(repo)
            if not rel:
                errors.append(f"商店页有 releases.json 里没有的仓库：{repo}")
                continue
            if str(rel["size"]) != size:
                errors.append(f"{repo} 页面体积 {size} != 真实 {rel['size']}")
            if rel["url"] != url:
                errors.append(f"{repo} 页面链接与 releases.json 不一致：{url}")
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
        if not re.search(r"[?:=(]\s*slowDirect\s*\(\s*\)", store):
            errors.append("slowDirect 定义了却没有被调用（地区判断没生效）")
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
        if "多线程下载" in store and "实测不成立" not in store:
            errors.append("商店页提到「多线程下载」却没有说明它实测不成立——"
                          "这会被读成卖点，而事实恰好相反")

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
