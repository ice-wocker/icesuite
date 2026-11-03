#!/usr/bin/env python3
"""把 GitHub 上的真实仓库状态同步成 data/registry.json。

这个文件替代了原来手写的 `WATCHED = [...8 个仓库...]` 和按仓库名硬编码的
`data/releases.json`。原来那套的问题不是「写错了」，而是**必须有人记得改**：

- 新项目发布 → 得先推一次代码把仓库名写进 WATCHED，否则站点永远看不到它；
- 版本更新 → 得先跑一次 `fetch_releases.py --write` 再推，否则商店页停在旧版本
  （那个脚本已被本文件取代）。
  两次都真的发生过：商店页挂着 v2.6.0 而线上已经是 v2.7.1。

现在反过来：站点**自动发现**账号下所有仓库与 Release，谁都不需要登记。
人只写「这个项目该被怎么描述」（data/projects.py，可选叠加），
「它现在是什么版本、多大、什么时候发的、包叫什么名字」全部来自这台机器。

    python3 scripts/sync.py            # 刷新快照
    python3 scripts/sync.py --check    # 只比对快照与线上是否一致（CI 用）

快照入库、构建时只读快照 —— 构建过程仍然不联网，同一个 commit 仍然产出同一份站点。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "registry.json"
API = "https://api.github.com"
<<<<<<< HEAD
SCHEMA = 4
=======
SCHEMA = 3
>>>>>>> f5839e68205838e0d618905335f067bec3fd5355

# 账号下不是「作品」的仓库：主页仓库、组织级社区健康文件仓库。
# 这是唯一还需要人写一句的地方 —— 因为「这个仓库算不算作品」没有机器可判的答案。
NOT_A_PROJECT = {"ice-wocker", ".github"}

# GitHub Pages 项目的线上地址：仓库名 → 页面路径。取不到就留空，
# 站内自己会把「在线预览」按钮省掉，而不是给一个 404。
PAGES_OVERRIDES = {
    "frontier-knowledge-base": "https://ice-wocker.github.io/frontier-knowledge-base/",
    "icesuite": "https://ice-wocker.github.io/icesuite/",
}


def api_get(path, token, timeout=30, retries=3):
    url = path if path.startswith("http") else API + path
    headers = {"User-Agent": "icesuite-registry-sync/3.0",
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


def pick_asset(assets, kind):
    """从一次 Release 的资源里挑出「这个平台的主包」。

    一个 Release 里可能躺着 debug/release 两个 APK、或者 arm64+armv7 两个包。
    原来那套取「第一个 .apk」，于是 GunFire 的商店按钮给的是 3.2 MB 的 debug 包，
    而 release 包是 622 KB —— 页面上写着「按百 KB 计」，用户下到的是 3 MB。

    排序规则要能解释：优先不带 debug/unsigned 字样的、优先 arm64、优先体积小的。
    """
    suffix = {"android": (".apk",), "windows": (".exe", ".msi", ".zip"),
              "macos": (".dmg",), "linux": (".appimage", ".deb"),
              "web": (".zip",), "python": (".whl",), "site": (".zip",),
              "code": (), "other": ()}[kind]
    cand = [a for a in assets if a["name"].lower().endswith(suffix)] if suffix else []
    if not cand:
        return None

    def score(a):
        low = a["name"].lower()
        return (
            0 if not any(t in low for t in ("debug", "unsigned", "unaligned")) else 1,
            0 if "arm64" in low or "aarch64" in low else 1,
            a.get("size") or 0,
            low,
        )

    return sorted(cand, key=score)[0]


def detect_kind(repo, releases):
    """仓库是什么形态：能装的包？还是脚本/服务/知识库？

    判断优先看**证据**（Release 里到底有没有可执行产物），不看仓库描述里的自夸。
    没有产物但有 Pages 的算站点，剩下的一律「源码/服务」。
    """
    for rel in releases:
        names = [a["name"].lower() for a in rel.get("assets", [])]
        if any(n.endswith(".apk") for n in names):
            return "android"
    kind = "code"
    if repo["name"] in PAGES_OVERRIDES or repo.get("homepage"):
        kind = "site"
    if (repo.get("language") or "") in ("Python", "Java", "JavaScript", "TypeScript", "C++", "Go", "Rust", "Shell"):
        kind = "code"
    return kind


def normalise(owner, repo, releases, token):
    name = repo["name"]
    rels = []
    for rel in releases:
        if rel.get("draft"):
            continue
        assets = [{"name": a["name"], "size": a.get("size") or 0,
                   "downloads": a.get("download_count") or 0,
                   "url": a["browser_download_url"],
                   "digest": a.get("digest") or ""}
                  for a in rel.get("assets", [])]
        rels.append({
            "tag": rel["tag_name"],
            "name": rel.get("name") or rel["tag_name"],
            "published_at": (rel.get("published_at") or "")[:10],
            "prerelease": bool(rel.get("prerelease")),
            "body": (rel.get("body") or "")[:4000],
            "assets": assets,
        })
    rels.sort(key=lambda r: (r["published_at"], r["tag"]), reverse=True)

    kind = detect_kind(repo, rels)
    latest = None
    for rel in rels:
        # 预发布也算「最新」：这个账号上真有过唯一可安装包只放在 prerelease 里的情况，
        # 跳过它的后果是「明明发了版，站点上这个应用一格都没有」。
        # 页面上会标出 pre 字样，不冒充正式版。
        asset = pick_asset(rel["assets"], kind)
        if asset:
            latest = dict(rel, asset=asset)
            break
    if latest is None and rels:
        # 没有可执行产物的 Release（权重、站点版本）也算「发过版」，只是不可安装
        latest = dict(rels[0], asset=None)

    homepage = PAGES_OVERRIDES.get(name) or (repo.get("homepage") or "").strip() or ""
<<<<<<< HEAD
    # 仓库的 GitHub Pages 地址：GitHub 只在真的开了 Pages 时才给这个字段，
    # 所以它是「有没有线上站」的证据，而不是从技术栈猜出来的。
    pages = repo.get("has_pages") or False
=======
>>>>>>> f5839e68205838e0d618905335f067bec3fd5355
    return {
        "repo": name,
        "description": (repo.get("description") or "").strip(),
        "homepage": homepage,
        "language": repo.get("language") or "",
        "topics": repo.get("topics") or [],
        "stars": repo.get("stargazers_count") or 0,
        "forks": repo.get("forks_count") or 0,
        "archived": bool(repo.get("archived")),
        "pushed_at": (repo.get("pushed_at") or "")[:10],
        "created_at": (repo.get("created_at") or "")[:10],
        "default_branch": repo.get("default_branch") or "main",
        "repo_url": repo["html_url"],
        "size_kb": repo.get("size") or 0,
        "has_license": bool(repo.get("license")),
<<<<<<< HEAD
        "has_pages": bool(pages),
        "counts": {
            # 三个计数都来自同一次仓库详情调用，不额外发请求。
            # 它们是「这个项目有多重」的另一种口径：星标是外部反应，
            # open issue 是自报的欠账，发版次数是迭代密度。
            "open_issues": repo.get("open_issues_count") or 0,
            "releases": len(rels),
            "assets": sum(len(r.get("assets") or []) for r in rels),
        },
=======
>>>>>>> f5839e68205838e0d618905335f067bec3fd5355
        "kind": kind,
        "latest": latest,
        "releases": rels,
    }


def snapshot(owner, token):
    repos = api_get(f"/users/{owner}/repos?per_page=100&type=owner&sort=pushed", token)
    out = {}
    problems = []
    for repo in repos:
        name = repo["name"]
        if name in NOT_A_PROJECT or repo.get("fork"):
            continue
        try:
            rels = api_get(f"/repos/{owner}/{name}/releases?per_page=10", token)
        except Exception as e:                     # 单个仓库失败不该毁掉整次同步
            problems.append(f"{name}: 取 Release 失败 {type(e).__name__} {e}")
            rels = []
        out[name] = normalise(owner, repo, rels, token)
        latest = out[name]["latest"]
        flag = f"{latest['tag']} {latest['asset']['name']}" if latest and latest.get("asset") else "无可安装产物"
        print(f"  {name:26} {out[name]['kind']:8} {flag}")
    if problems:
        for p in problems:
            print("问题：" + p, file=sys.stderr)
    return out, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default="ice-wocker")
    ap.add_argument("--token", default=None, help="不传则读 GH_TOKEN / GITHUB_TOKEN")
    ap.add_argument("--check", action="store_true",
                    help="只比对快照与线上是否一致，不一致返回 1")
    ap.add_argument("-o", "--out", default=str(OUT))
    args = ap.parse_args()

    token = args.token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if args.check and not token:
        # 匿名取 API 在 CI 上会撞 60 次/小时的限额，那会把「绿」变成随机的红。
        print("未提供 GH_TOKEN：跳过一致性检查（CI 里应传入 secrets.GITHUB_TOKEN）")
        return 0

    cur, problems = snapshot(args.owner, token)
    out = Path(args.out)

    if args.check:
        old = {}
        if out.exists():
            old = json.loads(out.read_text(encoding="utf-8")).get("projects", {})
        drift = []
        for name, now in cur.items():
            prev = old.get(name)
            if not prev:
                drift.append(f"{name}: 线上有、快照里没有（新项目还没上站）")
                continue
            a, b = prev.get("latest") or {}, now.get("latest") or {}
            if (a.get("tag"), (a.get("asset") or {}).get("name")) != \
               (b.get("tag"), (b.get("asset") or {}).get("name")):
                drift.append(f"{name}: {a.get('tag')} → {b.get('tag')}")
        for name in old:
            if name not in cur:
                drift.append(f"{name}: 快照里有、线上已不见")
        if drift:
            print("data/registry.json 已过期，请运行 python3 scripts/sync.py 后提交：")
            for d in drift:
                print("  - " + d)
            return 1
        print(f"data/registry.json 与线上一致（{len(cur)} 个仓库）。")
        return 0

    payload = {
        "_note": "由 scripts/sync.py 从 GitHub API 生成，请勿手改。构建时只读本文件，不联网。",
        "schema": SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "owner": args.owner,
        "projects": cur,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    installable = sum(1 for p in cur.values() if (p.get("latest") or {}).get("asset"))
    print(f"已写入 {out}：{len(cur)} 个仓库，{installable} 个可安装。")
    # 全部失败才返回非零：个别仓库抽风不该让整次同步失败，否则每分钟跑一次的
    # 定时任务会变成随机红灯，人就会开始无视它。
    return 1 if problems and len(problems) == len(cur) else 0


if __name__ == "__main__":
    sys.exit(main())
