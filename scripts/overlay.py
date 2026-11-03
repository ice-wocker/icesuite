# -*- coding: utf-8 -*-
"""手写叠加层的解析与合并 —— 站点内容的「编辑视角」只有这一个入口。

为什么单独一个文件：
原来这段逻辑写在 build_site.load() 里，check_site 想校验「页面上的东西和
清单一致」只能再实现一遍同样的合并（它当时绕过去 import 了 build_site，
然后为了拿一个 dict 把整个渲染模块都执行了一次）。两份必然漂移。
现在合并规则只在这里，build 与 check 都调它，谁也不许自己抄。

合并次序（不能反）：
  1. data/registry.json 给出「有哪些项目、现在是什么版本」—— 机器的事实
  2. data/projects.py 里同 id / 同 repo 的条目覆盖文案，并补手写事实
  3. registry 里有、projects.py 里没写的仓库，用 derive() 造卡并标 auto
"""
from __future__ import annotations

import re
from pathlib import Path

from util import DATA, human_size

# 叠加层没写时的兜底分组：按仓库形态归位。
# 新项目上线第一天就有位置，不会因为「还没人给它写文案」而从站点上消失。
DEFAULT_GROUP = {"android": "apps", "site": "sites", "code": "code"}
DEFAULT_ICON = {"android": "📱", "site": "🌐", "code": "🧩"}

# 这几个字段是「机器的事实」。叠加层里就算抄了一份，也不许覆盖 ——
# 手抄的版本号过期正是这个站点最初的两起事故之一（页面上 v2.6.0，线上 v2.7.1）。
MACHINE_FIELDS = ("version", "published_at", "size_bytes", "size_text", "asset_name",
                  "asset_sha256", "dl_release", "downloads", "prerelease")


def _exec(path: Path) -> dict:
    ns = {}
    exec(Path(path).read_text(encoding="utf-8"), ns)
    return ns


def load_site_meta() -> dict:
    return _exec(DATA / "projects.py").get("SITE", {})


def load_groups() -> list:
    return list(_exec(DATA / "projects.py").get("GROUPS", []))


def load_handwritten() -> list:
    return list(_exec(DATA / "projects.py").get("PROJECTS", []))


def load_mirrors() -> dict:
    """data/mirrors.py —— 加速候选清单。

    这个文件是**手写**的：镜像站是别人家的服务，没有自动机制能保证它活着。
    所以它必须允许「这里就是空的」—— 一个候选都没有时，前端只是没有加速可开，
    站点照常构建、照常自检。
    """
    f = DATA / "mirrors.py"
    if not f.exists():
        return {"mirrors": [], "params": {}}
    ns = _exec(f)
    mirrors = [m for m in ns.get("MIRRORS", []) if m.get("prefix") is not None]
    return {
        "mirrors": [{"id": m["id"], "label": m["label"], "prefix": m.get("prefix", ""),
                     "role": m.get("role", "accelerator"), "note": m.get("note", "")}
                    for m in mirrors],
        "params": {
            "accel_default": ns.get("ACCEL_DEFAULT", "auto"),
            "timezones": list(ns.get("SLOW_DIRECT_TIMEZONES", ())),
            "langs": list(ns.get("SLOW_DIRECT_LANGS", ())),
            "regions": list(ns.get("SLOW_DIRECT_REGIONS", ())),
        },
    }


def load_registry() -> dict:
    """data/registry.json —— 「GitHub 上真实是什么样」的唯一真相源。"""
    from util import read_json
    payload = read_json(DATA / "registry.json", {}) or {}
    return payload.get("projects", {})


def registry_meta() -> dict:
    from util import read_json
    payload = read_json(DATA / "registry.json", {}) or {}
    return {"schema": payload.get("schema"), "generated_at": payload.get("generated_at") or "",
            "owner": payload.get("owner") or ""}


def derive(reg: dict, author: str) -> dict:
    """从注册表的一条记录派生出项目卡片需要的全部字段。

    原则：**机器能查到的绝不手写，查不到的绝不编。**
    """
    latest = reg.get("latest") or {}
    asset = latest.get("asset") or {}
    name = reg["repo"]
    kind = reg.get("kind") or "code"
    return {
        "id": name.lower(),
        "repo": name,
        "name": name,
        "group": DEFAULT_GROUP.get(kind, "code"),
        "icon": DEFAULT_ICON.get(kind, "🧩"),
        "pitch": reg.get("description") or name,
        "summary": reg.get("description") or f"{name}（GitHub 上没有填描述）",
        "tags": list(reg.get("topics") or []),
        "metrics": [],
        # 自动收录的项目没有人工写的亮点。与其留一个空标题，
        # 不如把 GitHub 上真实可查的事实当成亮点 —— 它们本来就是读者想知道的。
        "highlights": [],
        "tech": [t for t in [reg.get("language")] if t],
        "known_limits": [],
        "store_note": "",
        "installation": "",
        "status": "mature" if (reg.get("releases") or []) else "beta",
        "platform": kind if kind == "android" else None,
        "external_url": reg.get("homepage") or "",
        "external_label": "打开线上站点" if kind == "site" else "项目主页",
        "version": latest.get("tag") or "",
        "published_at": latest.get("published_at") or "",
        "size_bytes": asset.get("size") or 0,
        "size_text": human_size(asset.get("size")),
        "downloads": asset.get("downloads") or 0,
        "asset_name": asset.get("name") or "",
        "asset_sha256": (asset.get("digest") or "").replace("sha256:", ""),
        "dl_release": asset.get("url") or "",
        "prerelease": bool(latest.get("prerelease")),
        "history": [{"tag": r.get("tag") or "", "name": r.get("name") or r.get("tag") or "",
                     "published_at": r.get("published_at") or "",
                     "body": r.get("body") or "",
                     "prerelease": bool(r.get("prerelease")),
                     "asset": (r.get("assets") or [{}])[0].get("name") if r.get("assets") else ""}
                    for r in (reg.get("releases") or [])],
        "repo_url": reg.get("repo_url") or f"https://github.com/{author}/{name}",
        "stars": reg.get("stars") or 0,
        "forks": reg.get("forks") or 0,
        "language": reg.get("language") or "",
        "pushed_at": reg.get("pushed_at") or "",
        "created_at": reg.get("created_at") or "",
        "archived": bool(reg.get("archived")),
        "repo_size_kb": reg.get("size_kb") or 0,
        "has_license": bool(reg.get("has_license")),
        "has_pages": bool(reg.get("has_pages")),
        "open_issues": (reg.get("counts") or {}).get("open_issues") or 0,
        "n_releases": (reg.get("counts") or {}).get("releases") or len(reg.get("releases") or []),
        "auto": True,
    }


def load() -> dict:
    """注册表 + 手写叠加层 → 项目清单。build 与 check 的共同入口。"""
    site = load_site_meta()
    author = site.get("author", "ice-wocker")
    groups = load_groups()
    hand = load_handwritten()
    reg_projects = load_registry()
    mirror_cfg = load_mirrors()

    gmap = {k: (k, label, desc) for k, label, desc in groups}

    projects, auto_n = [], 0
    for p in hand:
        merged = dict(p)
        pid = merged["id"]
        reg = reg_projects.get(merged.get("repo") or "") or reg_projects.get(pid) or {}
        if reg:
            base = derive(reg, author)
            for k, v in base.items():
                # 机器字段永远用机器的；其余字段手写优先
                if k in MACHINE_FIELDS:
                    merged[k] = v
                elif k not in merged or merged[k] in (None, "", [], {}):
                    merged[k] = v
            merged["auto"] = False
        else:
            merged.setdefault("repo_url", f"https://github.com/{author}/{merged.get('repo', pid)}")
            merged["auto"] = False
            merged["missing"] = True
            for k in MACHINE_FIELDS:
                merged.setdefault(k, None if k != "size_bytes" else 0)
        projects.append(merged)

    known = {p.get("repo") or p["id"] for p in projects} | {p["id"] for p in projects}
    known_lower = {k.lower() for k in known}
    for name, reg in sorted(reg_projects.items()):
        if name in known or name.lower() in known_lower:
            continue
        projects.append(derive(reg, author))
        auto_n += 1

    for p in projects:
        p.setdefault("status", "beta")
        p.setdefault("min_android", "")
        p.setdefault("arch", "")
        p.setdefault("store_note", "")
        p.setdefault("installation", "")
        p.setdefault("tags", [])
        p.setdefault("tech", [])
        p.setdefault("metrics", [])
        p.setdefault("highlights", [])
        p.setdefault("known_limits", [])
        p.setdefault("history", [])
        p.setdefault("size_bytes", 0)
        p.setdefault("size_text", "")
        p.setdefault("downloads", 0)
        p["releases_url"] = f"https://github.com/{author}/{p['repo']}/releases"
        p["url"] = f'{p["id"]}.html'
        gl = gmap.get(p["group"])
        p["group_label"] = gl[1] if gl else (p.get("group") or "其他")
        # 「能不能下载」不再看手写的 platform 字段，而看**证据**：
        # Release 里到底有没有一个可下载的包。手写字段漏一处，这个应用
        # 就永远在站点上缺一个下载按钮 —— 那正是「新项目只能后加」的物理原因。
        p["installable"] = bool(p.get("dl_release"))
        if p["size_text"]:
            for k in ("pitch", "summary", "store_note", "installation"):
                if isinstance(p.get(k), str):
                    p[k] = p[k].replace("{size}", p["size_text"])

    used = {p["group"] for p in projects}
    for g in used:
        if g not in gmap:
            groups = list(groups) + [(g, g, "")]
            gmap[g] = (g, g, "")

    return {"site": site, "groups": groups, "projects": projects,
            "mirrors": mirror_cfg, "registry": registry_meta(), "auto_n": auto_n}


def plain(s: str) -> str:
    """去掉行内标签，用于 description / JSON-LD 这类纯文本位置。"""
    return re.sub(r"<[^>]+>", "", s or "").strip()


# 允许出现在文案里的行内标签。数据源是仓库内的 Python 文件（不是外部输入），
# 但仍然先整体转义再按白名单放回：这样即使以后有人从接口拼文案进来，
# 也只会得到字面文本，不会得到一段可执行 HTML。
RICH_TAGS = ("code", "b", "em", "kbd")


def rich(s: str) -> str:
    from util import esc
    out = esc(s)
    for t in RICH_TAGS:
        out = re.sub(rf"&lt;{t}&gt;(.*?)&lt;/{t}&gt;",
                     lambda m, t=t: f"<{t}>{m.group(1)}</{t}>", out, flags=re.S)
    return out
