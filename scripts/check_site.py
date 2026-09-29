#!/usr/bin/env python3
"""站点自检：在没有浏览器的情况下，抓住最容易静默出错的三类问题。

1. 下载链接是不是真的能下（每个 release_asset 都 HEAD 一次）
2. 站内链接有没有指向不存在的页面（拼错 id 就白给一个 404）
3. 有没有页面忘了 CNAME / 首页是否漏了某个项目
4. canonical / sitemap / og:image 里的地址是不是同一个（换域名时最容易漏）
5. 首页自称的项目数与清单条数是否一致（文案里写死的数字会过期）
6. 站点对外声明的地址（base_url）还打不打得开

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
        p.setdefault("url", f'{p["id"]}.html')
        if p.get("release_asset"):
            p.setdefault("dl_release",
                         f"https://github.com/{author}/{p['repo']}/releases/latest/download/{p['release_asset']}")
    errors, warnings = [], []
    base = str(site.get("base_url", "")).rstrip("/")

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
        # 站点自己的地址必须能打开：域名掉了却没人发现，是最贵的静默故障
        if base:
            code, why = head(base + "/")
            checked += 1
            if code == 200:
                print(f"入口可访问：{base}/")
            elif code in (0, 500, 502, 503, 504):
                warnings.append(f"[存疑] 站点入口 {base}/ → {why}")
            else:
                errors.append(f"[死链] 站点入口 {base}/ → {why}")

        for p in projects:
            targets = []
            if p.get("dl_release"):
                targets.append(("APK", p["dl_release"]))
            targets.append(("仓库", p["repo_url"]))
            if base:
                targets.append(("项目页", f'{base}/{p["url"]}'))
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

    # --- 5. 地址一致性：canonical / og:url / sitemap 必须都来自 base_url ---
    if not base:
        errors.append("SITE 缺少 base_url（canonical 会退化成相对路径）")
    else:
        index_html = (SITE_DIR / "index.html").read_text(encoding="utf-8")
        if f'rel="canonical" href="{base}/index.html"' not in index_html:
            errors.append(f"首页 canonical 不是 base_url：{base}")
        for f in ("robots.txt", "sitemap.xml", "site.webmanifest"):
            if not (SITE_DIR / f).exists():
                errors.append(f"缺少产物 {f}")
        sm = (SITE_DIR / "sitemap.xml").read_text(encoding="utf-8") if (SITE_DIR / "sitemap.xml").exists() else ""
        if base not in sm:
            errors.append("sitemap.xml 里没有 base_url")
        n_loc = sm.count("<loc>")
        if n_loc != len(projects) + 1:
            errors.append(f"sitemap 条目 {n_loc} 个，应为 {len(projects) + 1}（首页 + 每个项目）")
        # 图标 / 分享图必须真的存在，否则 head 里就是死链
        for f in ("favicon.svg", "apple-touch-icon.png", "og.svg"):
            if not (SITE_DIR / f).exists():
                errors.append(f"head 引用了但产物里没有：{f}")

    # --- 6. 文案里的项目数不能和清单打架 ---
    idx_html = (SITE_DIR / "index.html").read_text(encoding="utf-8")
    if re.search(rf"<b>\s*{len(projects)}\s*</b>\s*个作品", idx_html) is None:
        errors.append(f"首页统计块里的作品数不是 {len(projects)}")
    if f"搜索 {len(projects)} 个项目" not in idx_html:
        errors.append(f"搜索框占位文案里的项目数不是 {len(projects)}")
    stated = set(re.findall(r"<b>(\d+)</b>\s*个作品", idx_html))
    for s in stated:
        if int(s) != len(projects):
            errors.append(f"首页宣称 {s} 个作品，清单是 {len(projects)} 条")
    words = {"十一个": 11, "十二个": 12, "十三个": 13, "十四个": 14}
    for word, num in words.items():
        if word in idx_html and num != len(projects):
            errors.append(f"首页文案写了「{word}」，但清单是 {len(projects)} 条")
    for f in ("index.html", "404.html"):
        body = (SITE_DIR / f).read_text(encoding="utf-8")
        for word, num in words.items():
            if word in body and num != len(projects):
                errors.append(f"{f} 文案写了「{word}」，但清单是 {len(projects)} 条")

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
