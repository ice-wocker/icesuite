#!/usr/bin/env python3
"""线上核对：把**已发布的站点**和仓库里的快照对一遍。

和 check_site.py 的分工：
  check_site    看「本地产物对不对」——构建完就跑，不需要网络（默认）
  live_check    看「线上那份对不对」——需要网络，跑在 deploy 之后

为什么非要单独有它：这一版之前的两次翻车，构建和自检都全绿，
错的是「线上那份和仓库里的快照不是一回事」——
店里挂着 v2.6.0，而 Release 已经是 v2.7.1。本地检查抓不到这个，
因为本地那份本来就是对的。

核对的都是**能证伪的东西**：字节数、sha256、版本号、条目数。
不核对「页面好看不好看」——那件事机器判不了。

    python3 scripts/live_check.py                       # 默认查 GitHub Pages
    python3 scripts/live_check.py --base https://...    # 查别的部署
    python3 scripts/live_check.py --retries 6           # Pages 刚发布时等一会儿
"""
import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
UA = {"User-Agent": "icesuite-live-check/1.0"}


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def fetch_json(base, name, retries):
    last = ""
    for i in range(retries):
        try:
            code, raw = get(f"{base}/{name}")
            if code == 200:
                return json.loads(raw.decode("utf-8")), ""
            last = f"HTTP {code}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(3 * (i + 1))
    return None, last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None, help="默认读 data/projects.py 里的 base_url")
    ap.add_argument("--retries", type=int, default=4)
    ap.add_argument("--sample", type=int, default=6, help="逐字节核对几个 APK")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT / "scripts"))
    import overlay

    base = (args.base or overlay.load_site_meta().get("base_url") or "").rstrip("/")
    if not base:
        print("没有 base_url，跳过")
        return 0
    local_content = SITE / "content.json"
    if not local_content.exists():
        print("先跑 python3 scripts/build_site.py")
        return 1
    want = json.loads(local_content.read_text(encoding="utf-8"))

    errors, warnings = [], []
    print(f"线上核对：{base}（最多重试 {args.retries} 次）")

    live, why = fetch_json(base, "content.json", args.retries)
    if live is None:
        print(f"❌ 取不到线上 content.json：{why}")
        print("   （Pages 刚发布时常见：CDN 还在传。CI 里用 --retries 8 再试）")
        return 1

    # 1. 产物指纹：同一 commit 必须得到同一个 id
    if live.get("build", {}).get("id") != want.get("build", {}).get("id"):
        errors.append(f"线上产物指纹 {live.get('build', {}).get('id', '')[:16]} "
                      f"!= 本地 {want.get('build', {}).get('id', '')[:16]}"
                      "（线上部署的不是这份快照，或构建不可复现）")
    # 2. 文件清单一致
    lf, wf = live.get("files") or {}, want.get("files") or {}
    miss = sorted(set(wf) - set(lf))
    extra = sorted(set(lf) - set(wf))
    if miss:
        errors.append(f"线上少了 {len(miss)} 个文件：{miss[:4]}")
    if extra:
        warnings.append(f"线上多了 {len(extra)} 个文件：{extra[:4]}")
    # 3. 抽查文件字节数（不逐个下 —— 那等于把整站拉一遍）
    for name in ("index.html", "store.html", "update.json", "sw.js", "manifest.json"):
        if name in wf and name in lf and wf[name]["bytes"] != lf[name]["bytes"]:
            errors.append(f"线上 {name} 字节数 {lf[name]['bytes']} != 本地 {wf[name]['bytes']}")

    # 4. update.json：版本号与 sha256 必须与快照一致
    up_live, why = fetch_json(base, "update.json", 1)
    up_local = json.loads((SITE / "update.json").read_text(encoding="utf-8"))
    if up_live is None:
        errors.append(f"取不到线上 update.json：{why}")
    else:
        a, b = up_live.get("apps") or {}, up_local.get("apps") or {}
        if set(a) != set(b):
            errors.append(f"update.json 应用集合不同：{sorted(set(a) ^ set(b))}")
        for k in sorted(set(a) & set(b)):
            if a[k].get("version") != b[k].get("version"):
                errors.append(f"update.json 里 {k} 线上版本 {a[k].get('version')} "
                              f"!= 快照 {b[k].get('version')}")
            if (a[k].get("sha256") or "") != (b[k].get("sha256") or ""):
                errors.append(f"update.json 里 {k} 线上 sha256 与快照不一致")

    # 5. 抽样下载 APK，实算 sha256 —— 这是唯一能证明「那个包就是那个包」的办法
    apps = [p for p in (up_local.get("apps") or {}).items() if p[1].get("sha256")]
    apps.sort(key=lambda kv: kv[1].get("size") or 0)   # 小的先下，别把 CI 拖死
    sample = apps[:max(0, args.sample)]
    for repo, meta in sample:
        url = meta.get("url") or ""
        if not url:
            continue
        try:
            code, raw = get(url, timeout=120)
        except Exception as e:
            errors.append(f"下不动 {repo} 的包：{type(e).__name__}")
            continue
        if code != 200:
            errors.append(f"{repo} 的包返回 HTTP {code}")
            continue
        got = hashlib.sha256(raw).hexdigest()
        if meta.get("size") and len(raw) != meta["size"]:
            errors.append(f"{repo} 实际 {len(raw)} 字节 != update.json 写的 {meta['size']}")
        if got != meta["sha256"]:
            errors.append(f"{repo} 实测 sha256 {got[:16]}… != update.json 声明的 "
                          f"{meta['sha256'][:16]}…（声明值是假的）")
        else:
            print(f"  ✅ {repo:24} {len(raw):>9} B  sha256 与声明一致")

    for w in warnings:
        print("  ⚠ " + w)
    if errors:
        print("\n线上核对失败：")
        for e in errors:
            print("  - " + e)
        return 1
    print(f"\n线上与本地一致：{len(wf)} 个文件、{len(up_local.get('apps') or {})} 个应用、"
          f"抽样 {len(sample)} 个包全部对得上。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
