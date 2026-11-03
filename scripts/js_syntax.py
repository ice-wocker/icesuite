#!/usr/bin/env python3
"""内联 JavaScript 的语法检查。

为什么需要它：**静态 HTML 检查看不出 JS 语法错误。**
这一版就栽过一次 —— 搜索脚本里一个字符类正则被转义吃掉了一个反斜杠，
整段脚本解析不了，于是「输入框能打字、但永远没有结果」。
构建全绿、自检全绿、HTTP 200、页面看起来完全正常，只有真的在浏览器里
敲三个字才发现。这种「静默失效」正是这个仓库最想防的那一类。

做法：把每张页面里的内联 <script> 抽出来，交给 node --check。
没有 node 时**跳过并明确说明**（而不是静默通过）—— CI 的 runner 自带 node。

    python3 scripts/js_syntax.py            # 检查 site/ 下全部页面
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def scripts_of(html_text):
    """抽出内联脚本。带 src 的、以及 JSON-LD（不是 JS）跳过。"""
    out = []
    for m in re.finditer(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", html_text, re.S):
        attrs, body = m.group(1), m.group(2)
        if "application/ld+json" in attrs or "application/json" in attrs:
            continue
        if body.strip():
            out.append(body)
    return out


def check_one(code, node, tmpdir, label):
    f = Path(tmpdir) / "chunk.js"
    f.write_text(code, encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or r.stdout).strip().splitlines()
        head = next((l for l in err if "Error" in l or "error" in l), err[0] if err else "")
        return f"{label}: JavaScript 语法错误 — {head.strip()[:160]}"
    return None


def main():
    node = shutil.which("node")
    if not node:
        print("跳过：本机没有 node，无法做内联 JS 语法检查（CI 上会真的执行）")
        return 0
    if not SITE.exists():
        print("先跑 python3 scripts/build_site.py")
        return 1
    errors, n = [], 0
    with tempfile.TemporaryDirectory() as td:
        for f in sorted(SITE.glob("*.html")):
            for i, code in enumerate(scripts_of(f.read_text(encoding="utf-8"))):
                n += 1
                e = check_one(code, node, td, f"{f.name} 内联脚本 #{i + 1}")
                if e:
                    errors.append(e)
        # sw.js 也是手写 JS，容易被当成「配置文件」漏掉
        sw = SITE / "sw.js"
        if sw.exists():
            n += 1
            e = check_one(sw.read_text(encoding="utf-8"), node, td, "sw.js")
            if e:
                errors.append(e)
    if errors:
        print(f"检查了 {n} 段内联/独立脚本，发现 {len(errors)} 处语法错误：")
        for e in errors:
            print("  - " + e)
        return 1
    print(f"内联脚本语法检查通过（{n} 段）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
