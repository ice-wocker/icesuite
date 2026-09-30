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
