#!/usr/bin/env python3
"""从 GitHub API 拉取各项目的 Release 元数据，冻结成 data/releases.json。

应用商店页面要显示「版本号 / 体积 / 发布时间」，这些必须是真的：
手写在清单里，发一次版就会漂一次，而且没人会发现。

所以这里做两件事：
1. 联网拉一次，把结果落盘成 data/releases.json（入库、可供 CI 校验）；
2. 构建时只读这个文件，构建过程不联网——同一个 commit 永远产出同一份站点。

只在发版后重新生成：
    python3 scripts/fetch_releases.py --write
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "releases.json"
API = "https://api.github.com"

# 只取这些仓库；key 对应 data/projects.py 里的 repo 名
WATCHED = [
    "iceScribe", "ModelScopeBrowser", "KayaGo", "iceScan",
    "iceBrowser", "iceReading", "MusicFusion", "MusicFusionAI",
]


def get(path, token, timeout=30, retries=3):
    url = path if path.startswith("http") else API + path
    headers = {"User-Agent": "ice-suite-release-fetcher/1.0",
               "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            # 403/429 多半是限流，退避重试
            if e.code in (403, 429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="ice-wocker")
    ap.add_argument("--token", default=None, help="不传则读 GH_TOKEN / GITHUB_TOKEN 环境变量")
    ap.add_argument("--write", action="store_true", help="写入 data/releases.json")
    ap.add_argument("--check", action="store_true",
                    help="只比对 data/releases.json 与线上是否一致，不一致返回 1（CI 用）")
    args = ap.parse_args()

    import os
    token = args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""

    out = {}
    failed = []
    for repo in WATCHED:
        try:
            releases = get(f"/repos/{args.owner}/{repo}/releases?per_page=10", token)
        except Exception as e:
            failed.append(f"{repo}: {type(e).__name__} {e}")
            continue
        entry = None
        for rel in releases:
            if rel.get("draft"):
                continue
            for a in rel.get("assets", []):
                if a["name"].lower().endswith(".apk"):
                    entry = {
                        "tag": rel["tag_name"],
                        "name": rel.get("name") or rel["tag_name"],
                        "published_at": (rel.get("published_at") or "")[:10],
                        "asset": a["name"],
                        "size": a["size"],
                        "downloads": a.get("download_count", 0),
                        "url": a["browser_download_url"],
                    }
                    break
            if entry:
                break
        if entry:
            out[repo] = entry
        else:
            failed.append(f"{repo}: 没有带 .apk 资源的正式 Release")
        print(("  ✅ " if entry else "  ⚠️  ") + repo + (f" {entry['tag']} {entry['size']}" if entry else ""))

    if failed:
        for f in failed:
            print("问题：" + f, file=sys.stderr)

    if args.check:
        old = json.loads(OUT.read_text(encoding="utf-8")).get("releases", {}) if OUT.exists() else {}
        drift = []
        for repo, cur in out.items():
            prev = old.get(repo)
            if not prev:
                drift.append(f"{repo}: 新增 {cur['tag']}（快照里没有）")
                continue
            for k, label in (("tag", "版本"), ("size", "体积"), ("asset", "文件名")):
                if prev.get(k) != cur.get(k):
                    drift.append(f"{repo}: {label} {prev.get(k)} → {cur.get(k)}")
        for repo in old:
            if repo not in out:
                drift.append(f"{repo}: 线上已找不到带 APK 的 Release（快照里还留着）")
        if drift:
            print("data/releases.json 已过期，请运行 python3 scripts/fetch_releases.py --write 后提交：")
            for d in drift:
                print("  - " + d)
            return 1
        print(f"data/releases.json 与线上一致（{len(out)} 个仓库）。")
        return 0

    payload = {
        "_note": "由 scripts/fetch_releases.py 从 GitHub API 生成，请勿手改。构建时只读本文件，不联网。",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "owner": args.owner,
        "releases": out,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.write:
        OUT.write_text(text, encoding="utf-8")
        print(f"已写入 {OUT}（{len(out)} 个仓库）")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failed and not out else 0


if __name__ == "__main__":
    sys.exit(main())
