#!/usr/bin/env python3
"""变异测试：往产物里注入缺陷，确认自检真的会红。

为什么需要它：守卫本身失效比没有守卫更危险。一条「永远为绿」的断言
会让你以为有人看着，实际上什么都没挡。

上一版就踩过：主题脚本顺序检查找的是 `data-theme` 字符串（它在第 2 行），
时区名单检查在**文件文本**里搜 `Asia/Guangzhou`（注释里正解释着为什么补它），
卡片结构检查只数 `.cardhit` 个数——三条注入缺陷后照样全绿。

这个脚本把「注入 → 必须变红」写成可执行的，进 CI。
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_check(site_dir):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_site.py"), "--skip-links"],
                       capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def mutate(name, mutate_fn, expect):
    """复制 site/ 到临时目录，注入缺陷后跑自检，返回 (是否通过, 说明)。"""
    tmp = Path(tempfile.mkdtemp()) / "site"
    shutil.copytree(ROOT / "site", tmp)
    try:
        mutate_fn(tmp)
        # check_site 固定读 ROOT/site；用环境变量指过去太绕，直接换目录
        backup = Path(tempfile.mkdtemp()) / "site_orig"
        shutil.move(str(ROOT / "site"), str(backup))
        shutil.copytree(tmp, ROOT / "site")
        code, out = run_check(tmp)
        shutil.rmtree(ROOT / "site")
        shutil.move(str(backup), str(ROOT / "site"))
        if code == 0:
            return False, f"❌ {name}：注入缺陷后自检依然全绿（这条守卫是橡皮图章）"
        if expect and expect not in out:
            return False, f"❌ {name}：变红了但不是预期的原因（找不到「{expect}」）"
        return True, f"✅ {name}：{expect or '已变红'}"
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def edit(path, fn):
    p = Path(path)
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


CASES = []


def case(name, expect):
    def deco(fn):
        CASES.append((name, fn, expect))
        return fn
    return deco


@case("删掉一个项目的页面", "页面缺失")
def _(site):
    p = next(site.glob("gunfire.html"))
    p.unlink()


@case("商店页少一个下载按钮", "商店页可下载应用")
def _(site):
    edit(site / "store.html", lambda s: s.replace('data-apk="', 'data-apkx="', 1))


@case("版本号与快照不符", "!= 快照")
def _(site):
    # 改的是项目页里的「当前版本」事实卡，不是商店页的 span——
    # 商店页的数字另有守卫，而 check 的版本断言比的是构建产物里的 version 字段。
    def f(s):
        m = re.search(r'<b>(v[\d.]+)</b><span>当前版本</span>', s)
        assert m, "没有找到「当前版本」事实卡"
        return s.replace(m.group(0), '<b>v0.0.1</b><span>当前版本</span>')
    target = next(p for p in site.glob("gunfire.html"))
    edit(target, f)


@case("首页漏一个项目卡片", "首页卡片数")
def _(site):
    edit(site / "index.html", lambda s: re.sub(r'<div class="card reveal">.*?</div></div>', "", s, count=1, flags=re.S))


@case("update.json 少一个应用", "update.json 的应用集合")
def _(site):
    def f(s):
        d = json.loads(s)
        d["apps"].pop(next(iter(d["apps"])))
        return json.dumps(d, ensure_ascii=False)
    edit(site / "update.json", f)


@case("update.json 版本被改错", "update.json 里")
def _(site):
    def f(s):
        d = json.loads(s)
        k = next(iter(d["apps"]))
        d["apps"][k]["version"] = "v9.9.9"
        return json.dumps(d, ensure_ascii=False)
    edit(site / "update.json", f)


@case("删掉 update.json", "缺少 update.json")
def _(site):
    (site / "update.json").unlink()


@case("校验值从页面里删掉", "sha256 校验值")
def _(site):
    edit(site / "gunfire.html", lambda s: re.sub(r"<pre class=\"sha\">.*?</pre>", "", s, flags=re.S))


@case("卡片变回整块 <a>", 'class="card"')
def _(site):
    edit(site / "index.html", lambda s: s.replace('<div class="card reveal">', '<a class="card" href="#">', 1))


@case("CSS 少一个大括号", "大括号不配平")
def _(site):
    edit(site / "style.css", lambda s: s.replace("}", "", 1))


@case("主题脚本挪到样式表之后", "主题脚本排在样式表之后")
def _(site):
    def f(s):
        i = s.index("localStorage.getItem(K)")
        seg_start = s.rindex("<script>", 0, i)
        seg_end = s.index("</script>", i) + len("</script>")
        seg = s[seg_start:seg_end]
        s2 = s[:seg_start] + s[seg_end:]
        j = s2.index('rel="stylesheet"') + len('rel="stylesheet"')
        return s2[:j] + seg + s2[j:]
    edit(site / "index.html", f)


@case("sitemap 漏一个项目页", "sitemap.xml 缺少")
def _(site):
    edit(site / "sitemap.xml", lambda s: re.sub(r"<url>(?:(?!</url>).)*?gunfire\.html.*?</url>", "", s, flags=re.S))


@case("标签索引漏一个标签", "tags.html 缺少标签")
def _(site):
    # 上一个版本这里写的是 `<h2>[^<]+</h2>`，但标题里还有 `<span class="fine">N 个</span>`，
    # 于是正则一条都匹配不上、实际上什么都没删 —— 变异测试当场抓到了这个橡皮图章。
    edit(site / "tags.html",
         lambda s: re.sub(r'<div class="indexgroup" id="[^"]+">(?:(?!indexgroup).)*?</div>',
                          "", s, count=1, flags=re.S))


@case("feed 少一条", "feed.xml 条目数")
def _(site):
    edit(site / "feed.xml", lambda s: re.sub(r"<item>.*?</item>", "", s, count=1, flags=re.S))


@case("校验值区块丢了样式类名", "校验值区块")
def _(site):
    edit(site / "gunfire.html", lambda s: s.replace('class="sha"', 'class="sh"'))


def main():
    if not (ROOT / "site" / "index.html").exists():
        print("先跑 python3 scripts/build_site.py")
        return 1
    results = [mutate(n, f, e) for n, f, e in CASES]
    for ok, msg in results:
        print(msg)
    bad = [m for ok, m in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} 条守卫自证通过")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
