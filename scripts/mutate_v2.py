#!/usr/bin/env python3
"""v3 新增守卫的变异测试：往产物里注入缺陷，确认自检**必须变红**。

为什么还要再写一份而不是扩充 mutate_test.py：
mutate_test.py 验的是「老页面 + 老产物」那 15 条。这一版新增了 5 张页面、
4 个机器可读产物、1 套 PWA —— 新守卫如果没人注入过缺陷，等于没人知道它是否还在工作。
两份分开跑的好处是 CI 能看出「红的是老守卫还是新守卫」。

判定标准沿用老规矩：**注入后自检必须返回非零，且报出的原因里含预期关键词。**
只变红不核对是因为——它可能是因为别的缺陷红的，那这条守卫其实是哑的。
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

CASES = []


def case(name, expect):
    def deco(fn):
        CASES.append((name, fn, expect))
        return fn
    return deco


def run_check():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_site.py"), "--skip-links"],
                       capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def edit(path, fn):
    p = Path(path)
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def edit_page(site, name, fn):
    """改一张页面，**并同步刷新 content.json 里这个文件的哈希**。

    为什么必须刷新：content.json 的守卫会逐文件核对 sha256，所以任何
    「页面被改坏」的变异都会先被它抓到 —— 结果是新守卫一条都没被验过，
    变异测试看起来全绿，实际上只是在测同一条断言。
    这是本次变异测试自己抓到的第 4 个橡皮图章（前三个来自上一版）。
    """
    import hashlib
    f = site / name
    f.write_text(fn(f.read_text(encoding="utf-8")), encoding="utf-8")
    raw = f.read_bytes()
    def fix(d):
        if name in d["files"]:
            d["files"][name] = {"bytes": len(raw),
                                "sha256": hashlib.sha256(raw).hexdigest()}
        return d
    edit_json(site / "content.json", fix)


def edit_json(path, fn):
    p = Path(path)
    p.write_text(json.dumps(fn(json.loads(p.read_text(encoding="utf-8"))),
                            ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ 产物自索引
@case("content.json 里某个文件的 sha256 被改", "sha256 与实际不符")
def _(site):
    def f(d):
        k = next(iter(d["files"]))
        d["files"][k]["sha256"] = "0" * 64
        return d
    edit_json(site / "content.json", f)


@case("content.json 里某个文件的字节数被改", "bytes 与实际不符")
def _(site):
    def f(d):
        k = next(iter(d["files"]))
        d["files"][k]["bytes"] += 1
        return d
    edit_json(site / "content.json", f)


@case("content.json 登记了产物里没有的文件", "但产物里没有")
def _(site):
    (site / "robots.txt").unlink()
    def f(d):
        d["files"]["robots.txt"] = {"bytes": 1, "sha256": "0" * 64}
        return d
    edit_json(site / "content.json", f)


@case("产物里多了一个未登记文件", "没进 content.json")
def _(site):
    (site / "extra-test.html").write_text("<html>hi</html>", encoding="utf-8")


# ------------------------------------------------------------------ stats.json
@case("stats.json 的仓库总数被改", "totals.projects")
def _(site):
    edit_json(site / "stats.json", lambda d: {**d, "totals": {**d["totals"], "projects": 99}})


@case("stats.json 的按月分桶漏一个月", "月份分桶漏了版本")
def _(site):
    def f(d):
        d["by_month"].pop(next(iter(d["by_month"])))
        return d
    edit_json(site / "stats.json", f)


@case("stats.json 的体积榜顺序被打乱", "没有按体积升序")
def _(site):
    def f(d):
        d["sizes"] = list(reversed(d["sizes"]))
        return d
    edit_json(site / "stats.json", f)


@case("数据页上的数字与 JSON 不一致", "stats.html 没有渲染")
def _(site):
    edit_page(site, "stats.html",
              lambda s: re.sub(r"<b>\d+</b>个仓库", "<b>123</b>个仓库", s, count=1))


@case("update.json 的自述覆盖率造假", "verify.sha256_covered")
def _(site):
    edit_json(site / "update.json",
              lambda d: {**d, "verify": {**d.get("verify", {}), "sha256_covered": 99}})


@case("update.json 的时间戳写成构建时间", "不是快照时间")
def _(site):
    edit_json(site / "update.json", lambda d: {**d, "generated_at": "2020-01-01T00:00:00Z"})


# ------------------------------------------------------------------ graph.json
@case("graph.json 少一个节点", "节点集合与项目清单不一致")
def _(site):
    edit_json(site / "graph.json", lambda d: {**d, "nodes": d["nodes"][1:]})


@case("graph.json 出现悬空边", "悬空边")
def _(site):
    def f(d):
        d["edges"].append({"a": "nope", "b": d["nodes"][0]["id"], "kind": "tag",
                           "tags": ["x"], "weight": 1})
        return d
    edit_json(site / "graph.json", f)


# ------------------------------------------------------------------ PWA
@case("manifest 的 start_url 写成绝对路径", "start_url")
def _(site):
    edit_json(site / "manifest.json", lambda d: {**d, "start_url": "/index.html"})


@case("manifest 少一个图标文件", "引用的图标")
def _(site):
    edit_page(site, "manifest.json", lambda s: s.replace('"icon-maskable.svg"', '"missing.svg"', 1))


@case("manifest 的快捷方式指向不存在的页面", "快捷方式")
def _(site):
    edit_json(site / "manifest.json",
              lambda d: {**d, "shortcuts": d["shortcuts"] + [{"name": "x", "short_name": "x",
                                                              "url": "gone.html"}]})


@case("sw.js 预缓存里混进不存在的文件", "预缓存了不存在")
def _(site):
    edit_page(site, "sw.js", lambda s: s.replace('"./index.html"', '"./index.html", "./ghost.html"', 1))


@case("sw.js 的 PRECACHE 被清空", "PRECACHE 是空的")
def _(site):
    edit_page(site, "sw.js", lambda s: re.sub(r"const PRECACHE = \[[^\]]*\]",
                                          "const PRECACHE = []", s, count=1))


@case("sw.js 的缓存名占位符没被替换", "缓存名占位符")
def _(site):
    edit_page(site, "sw.js", lambda s: re.sub(r"icesuite-[a-f0-9]+", "__CACHE_NAME__", s, count=1))


# ------------------------------------------------------------------ 新页面
@case("最新更新页被清空", "latest.html 缺少结构标记")
def _(site):
    edit_page(site, "latest.html", lambda s: re.sub(r'<ul class="latestlist">.*?</ul>', "", s, flags=re.S))


@case("时间线页丢了年份标题", "timeline.html 缺少结构标记")
def _(site):
    edit_page(site, "timeline.html", lambda s: re.sub(r'<h2 id="y-\d{4}"', "<h2", s))


@case("对比页整张表被删", "compare.html 缺少结构标记")
def _(site):
    edit_page(site, "compare.html", lambda s: re.sub(r'<table class="cmp">.*?</table>', "", s, flags=re.S))


@case("集合页某个集合渲染成空壳", "渲染成了空壳")
def _(site):
    def f(s):
        i = s.index('<section class="group"')
        j = s.index('class="cards"', i)
        k = s.index("</section>", j)
        return s[:j] + s[k:]
    edit_page(site, "collections.html", f)


# ------------------------------------------------------------------ 详情页
@case("详情页丢掉「体检」区块", "没有「体检」区块")
def _(site):
    edit_page(site, "gunfire.html", lambda s: s.replace("<h2>体检</h2>", "<h2>检查</h2>", 1))


@case("详情页丢掉「相关项目」", "没有「相关项目」区块")
def _(site):
    edit_page(site, "gunfire.html",
              lambda s: s.replace('<div class="relgrid">', '<div class="rellist">', 1))


@case("相关项目区块整段删掉", "没有「相关项目」区块")
def _(site):
    edit_page(site, "kayago.html",
              lambda s: s.replace('<div class="relgrid">', '', 1).replace(
                  '</div>', '</div>', 1))


@case("首页丢掉新页面入口区块", "缺少新页面入口区块")
def _(site):
    edit_page(site, "index.html", lambda s: re.sub(r'<div class="entrygrid">.*?</div>\s*</div>',
                                               "", s, count=1, flags=re.S))


@case("首页少一个入口链接", "没有指向 stats.html")
def _(site):
    # 只改 entrygrid 里的那一个 href。全局替换会把页脚那个也改掉，
    # 于是守卫「首页有没有指向 stats.html」照样绿 —— 变异等于没做。
    def f(s):
        i = s.index('class="entrygrid"')
        j = s.index('href="stats.html"', i)
        return s[:j] + 'href="data.html"' + s[j + len('href="stats.html"'):]
    edit_page(site, "index.html", f)


# ------------------------------------------------------------------ JS 语法
@case("内联脚本出现语法错误", "JavaScript 语法错误")
def _(site):
    # 这一条挡的是「页面 200、输入框能打字、但永远没结果」那类静默失效。
    # 复现方式：把字符类正则里的反斜杠吃掉一个 —— 整段脚本解析不了。
    edit_page(site, "index.html", lambda s: s.replace(
        "ts[t].replace(/[.*+?^${}()|[\\]\\\\]/g", "ts[t].replace(/[.*+?^${}()|[\\]/g", 1))


@case("内联脚本被整段删掉一块", "JavaScript 语法错误")
def _(site):
    edit_page(site, "index.html", lambda s: s.replace("function terms(kw){", "function terms(kw)", 1))


# ------------------------------------------------------------------ 执行
def mutate(name, fn, expect):
    tmp = Path(tempfile.mkdtemp()) / "site"
    shutil.copytree(SITE, tmp)
    backup = Path(tempfile.mkdtemp()) / "site_orig"
    try:
        fn(tmp)
        shutil.move(str(SITE), str(backup))
        shutil.copytree(tmp, SITE)
        code, out = run_check()
        shutil.rmtree(SITE)
        shutil.move(str(backup), str(SITE))
        if code == 0:
            return False, f"❌ {name}：注入缺陷后自检依然全绿（这条守卫是橡皮图章）"
        if expect and expect not in out:
            first = ""
            for line in out.splitlines():
                if line.strip().startswith(("stats", "graph", "content", "manifest",
                                            "sw.js", "latest", "timeline", "compare",
                                            "collections", "详情", "产物", "首页", "gunfire")):
                    first = line.strip()
                    break
            return False, f"❌ {name}：变红了但不是预期的原因（找不到「{expect}」，实际：{first[:70]}）"
        return True, f"✅ {name}：{expect}"
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def main():
    if not (SITE / "index.html").exists():
        print("先跑 python3 scripts/build_site.py")
        return 1
    results = [mutate(n, f, e) for n, f, e in CASES]
    for ok, msg in results:
        print(msg)
    bad = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} 条 v3 守卫自证通过")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
