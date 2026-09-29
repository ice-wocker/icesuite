#!/usr/bin/env python3
"""站点自检：在没有浏览器的情况下，抓住最容易静默出错的三类问题。

1. 下载链接是不是真的能下（每个 release_asset 都 HEAD 一次）
2. 站内链接有没有指向不存在的页面（拼错 id 就白给一个 404）
3. 有没有页面忘了 CNAME / 首页是否漏了某个项目

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
        if p.get("release_asset"):
            p.setdefault("dl_release",
                         f"https://github.com/{author}/{p['repo']}/releases/latest/download/{p['release_asset']}")
    errors, warnings = [], []

    # --- 1. 产物结构 ---
    for f in ("index.html", "style.css", "search.json", "CNAME", "404.html"):
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

    # --- 4. 外链可达性 ---
    checked = 0
    if not args.skip_links:
        for p in projects:
            targets = []
            if p.get("dl_release"):
                targets.append(("APK", p["dl_release"]))
            targets.append(("仓库", p["repo_url"]))
            if p.get("external_url"):
                targets.append(("站点", p["external_url"]))
            for label, url in targets:
                code, why = head(url)
                checked += 1
                if code == 200:
                    continue
                if code in (0, 500, 502, 503, 504):
                    warnings.append(f"[存疑] {p['id']} {label} {url} → {why}")
                else:
                    errors.append(f"[死链] {p['id']} {label} {url} → {why}")

    # 搜索索引与项目数一致
    idx = json.loads((SITE_DIR / "search.json").read_text(encoding="utf-8"))
    if len(idx) != len(projects):
        errors.append(f"search.json 条目数 {len(idx)} != 项目数 {len(projects)}")

    print(f"项目数：{len(projects)}")
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
