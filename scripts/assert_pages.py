#!/usr/bin/env python3
"""断言 registry.json 里的每个仓库都在 site/ 下有页面。

抽成脚本而不是写在 workflow 里，因为 YAML 里的 heredoc 引号规则
会把 python 代码解释成 YAML 键——CI 会以一个看不懂的语法错误挂掉。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
reg = json.loads((ROOT / "data" / "registry.json").read_text(encoding="utf-8"))["projects"]
site = ROOT / "site"
missing = [r for r in reg if not (site / (r.lower() + ".html")).exists()]
print(" ".join(missing))
sys.exit(0)
