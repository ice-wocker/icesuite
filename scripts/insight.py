# -*- coding: utf-8 -*-
"""从快照里算出**站点自己额外推导的结论**，而不是把快照换个排版。

这里的每一个数都能追到源数据上的一行：
- 发布节奏来自 `releases[].published_at`（GitHub 的 Release 时间）
- 存续天数来自 `created_at`（GitHub 的建仓时间）
- 下载量来自 Release 资产的 `download_count`
- 「久未发版」来自「最新 Release 时间」与「最近一次 push」的比较

一条自我约束：**能算才算，算不出就 null**。
`versionCode` 不推算、`sha256` 不推算，这里同样不推算「预计下一个版本」这类东西。
宁可页面上少一格，也不要一个看起来很像、但点开核实是假的数字。
"""
from __future__ import annotations

from util import days_between, sha1_short

# 「久未发版」的阈值。60 天是个保守值：这个账号的节奏本来就是
# 攒一批改动一起发，而不是每周一版。低于 60 天报「停滞」会把正常节奏说成问题。
STALE_DAYS = 60


def _month(iso: str) -> str:
    return (iso or "")[:7]


def health(p: dict) -> dict:
    """单个项目的「体检」结果。全部是**可核实的事实推导**，不含评价。"""
    latest = p.get("published_at") or ""
    pushed = p.get("pushed_at") or ""
    created = p.get("created_at") or ""
    since_release = days_between(latest, pushed) if latest and pushed else None
    age = days_between(created, pushed) if created and pushed else None
    checks = []
    # 每一档都给出「为什么」，因为读者会问「凭什么是这个颜色」。
    if p.get("archived"):
        checks.append(("archived", "仓库已归档", "GitHub 上标记为 archived，不再接受提交。"))
    if not latest:
        checks.append(("info", "还没有发布过版本", "仓库里没有 Release，所以本站拿不到版本号和包。"))
    elif since_release is not None and since_release > STALE_DAYS:
        checks.append(("warn", f"最新版本发布于 {since_release} 天前",
                       f"期间仓库还有提交。可能是在攒大版本，也可能只是没发版。"))
    if latest and not p.get("asset_name") and p.get("platform") == "android":
        checks.append(("warn", "Android 仓库但没有可下载的包",
                       "Release 里没有 .apk 资产，本站不会伪造一个下载按钮。"))
    if p.get("missing"):
        checks.append(("warn", "手写清单里有、GitHub 上找不到这个仓库",
                       "卡片保留可见，但链接可能是死的。"))
    if p.get("downloads"):
        checks.append(("ok", f"{p['downloads']} 次下载",
                       "数字来自 GitHub Release 资产计数器，会随下载增长。"))
    if p.get("has_license"):
        checks.append(("ok", "仓库带许可证文件", "可在仓库根目录打开 LICENSE 核实。"))
    if not checks:
        checks.append(("ok", "没有发现需要提示的状态", "有版本、有包、发版时间也不旧。"))
    return {
        "since_release_days": since_release,
        "age_days": age,
        "checks": [{"level": l, "title": t, "detail": d} for l, t, d in checks],
    }


def timeline(projects: list) -> list:
    """全部 Release 摊成一条时间线，按日期倒序。

    同一版本可能在多个项目上同一天发布 —— 那不是重复，是真实情况
    （这个账号确实有过一天发三个包的时候）。所以不去重。
    """
    rows = []
    for p in projects:
        for r in p.get("history") or []:
            if not r.get("tag"):
                continue
            rows.append({
                "date": r.get("published_at") or "",
                "year": (r.get("published_at") or "")[:4],
                "month": (r.get("published_at") or "")[:7],
                "repo": p["repo"], "id": p["id"], "name": p["name"],
                "tag": r["tag"], "prerelease": bool(r.get("prerelease")),
                "note": (r.get("name") or "") if (r.get("name") or "") != r.get("tag") else "",
                "asset": r.get("asset") or "",
                "has_body": bool((r.get("body") or "").strip()),
            })
    rows.sort(key=lambda x: (x["date"], x["tag"]), reverse=True)
    return rows


def stats(model: dict) -> dict:
    """站点级统计。写进 stats.json，同时渲染到 index 的「数据」区块。

    这个函数是 stats.json 与页面的**唯一**来源：两边各算一遍必然漂移，
    而漂移的后果是「页面写着 12，JSON 说 13」，谁都对不上。
    """
    projects = model["projects"]
    apps = [p for p in projects if p["installable"]]
    rels = timeline(projects)

    # Release 每月计数：只统计有日期的，缺日期的不塞进任何一个月
    by_month = {}
    for r in rels:
        if r["month"]:
            by_month[r["month"]] = by_month.get(r["month"], 0) + 1
    by_year = {}
    for r in rels:
        if r["year"]:
            by_year[r["year"]] = by_year.get(r["year"], 0) + 1

    # 语言：仓库的 primary language，不是代码行数。两个都「真」，但后者
    # 要 clone 才能算，而站点构建不许联网。
    by_lang = {}
    for p in projects:
        if p.get("language"):
            by_lang[p["language"]] = by_lang.get(p["language"], 0) + 1

    # 体积榜：只排真有包的，源码体积和安装包体积不是一个量纲
    sizes = sorted(({"repo": p["repo"], "id": p["id"], "name": p["name"],
                     "size": p["size_bytes"], "version": p["version"]}
                    for p in apps if p["size_bytes"]),
                   key=lambda x: x["size"])
    dl = sorted(({"repo": p["repo"], "id": p["id"], "name": p["name"],
                  "downloads": p["downloads"], "version": p["version"]}
                 for p in apps if p["downloads"]),
                key=lambda x: x["downloads"], reverse=True)

    body_count = sum(1 for r in rels if r["has_body"])
    tags = {}
    for p in projects:
        for t in p["tags"]:
            tags[t] = tags.get(t, 0) + 1

    newest = max((p["published_at"] for p in projects if p["published_at"]), default="")
    oldest = min((p["created_at"] for p in projects if p["created_at"]), default="")

    return {
        "generated_at": model.get("generated_at") or "",
        "totals": {
            "projects": len(projects),
            "installable": len(apps),
            "release_bytes": sum(p["size_bytes"] for p in apps),
            "releases": len(rels),
            "releases_with_notes": body_count,
            "tags": len(tags),
            "languages": len(by_lang),
            "handwritten": len(projects) - model.get("auto_n", 0),
            "auto": model.get("auto_n", 0),
            "downloads": sum(p["downloads"] for p in apps),
            "sha_covered": sum(1 for p in apps if p.get("asset_sha256")),
        },
        "by_month": dict(sorted(by_month.items())),
        "by_year": dict(sorted(by_year.items())),
        "by_language": dict(sorted(by_lang.items(), key=lambda kv: (-kv[1], kv[0]))),
        "by_tags": dict(sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))),
        "sizes": sizes,
        "downloads": dl,
        "newest_release": newest,
        "oldest_repo": oldest,
    }


def collection_catalog(model: dict) -> list:
    """自动生成的策展集合。

    为什么是「生成」而不是手写：手写的集合一定会过期 —— 某个项目改名 / 归档 /
    停止发版之后，还挂在「端侧 AI 精选」里，读者点进去发现是去年的事。
    这里的每一组都由**当前快照里的字段**决定，明天数据变了集合就变。

    同时保留人写的组：data/projects.py 里的 GROUPS 优先，因为那是编排，
    机器替代不了「把哪几个放在一起讲」这件事。
    """
    projects = model["projects"]
    tags = {}
    for p in projects:
        for t in p["tags"]:
            tags.setdefault(t, []).append(p)

    out = []
    # 1) 有包可下
    apps = [p for p in projects if p["installable"]]
    if apps:
        out.append({
            "id": "installable", "title": "装得上的", "kind": "auto",
            "desc": "Release 里真的有安装包的项目。按钮都是直链，点下去就能下。",
            "rule": "installable == true",
            "items": [p["id"] for p in apps],
        })
    # 2) 一个字节都没有发过版的
    no_rel = [p for p in projects if not p.get("version")]
    if no_rel:
        out.append({
            "id": "no-release", "title": "还没发版的", "kind": "auto",
            "desc": "仓库在，但还没有 Release。本站不会为它们伪造版本号和下载按钮。",
            "rule": "latest == null",
            "items": [p["id"] for p in no_rel],
        })
    # 3) 预发布包
    pre = [p for p in projects if p.get("prerelease")]
    if pre:
        out.append({
            "id": "prerelease", "title": "预发布中的", "kind": "auto",
            "desc": "包只在 GitHub 的 prerelease 里。能用，但作者没把它当正式版。",
            "rule": "prerelease == true",
            "items": [p["id"] for p in pre],
        })
    # 4) 只有源码、没有安装包
    src = [p for p in projects if not p["installable"] and p.get("version")]
    if src:
        out.append({
            "id": "source-only", "title": "只有源码的", "kind": "auto",
            "desc": "发过版，但产物不是安装包（脚本、服务、权重、静态站）。",
            "rule": "installable == false && latest != null",
            "items": [p["id"] for p in src],
        })
    # 5) 主题集合：按标签，只收 >= 2 个项目的标签（1 个项目的「集合」是自欺）
    for t, ps in sorted(tags.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(ps) < 2:
            continue
        out.append({
            "id": "tag-" + sha1_short(t), "title": f"标签：{t}", "kind": "tag",
            "desc": f"带「{t}」标签的 {len(ps)} 个项目。", "rule": f"tag == {t}",
            "items": [p["id"] for p in ps],
        })
    return out
