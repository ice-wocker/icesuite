# -*- coding: utf-8 -*-
"""构建脚本的公共小工具。零依赖：只用 Python 标准库。

几个函数被 build_site / check_site / probe_mirrors / mutate_v2 同时用，
放在一处而不是各抄一份 —— 抄一份的下场是「改了一处，另一处悄悄过期」，
这个仓库里已经有过一次（版本号在 md 里抄了两遍，其中一遍错过了两次发版）。
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


# ------------------------------------------------------------------ 文本
def esc(s) -> str:
    return html.escape(str(s), quote=False)


def attr(s) -> str:
    """属性值：连引号一起转义。esc() 不转引号，塞进属性里会被截断。"""
    return html.escape(str(s), quote=True)


def human_size(n) -> str:
    """字节数 → 人话。1024 进制，和系统「应用信息」里的口径一致。"""
    if not n:
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        kb = n / 1024
        return f"{kb:.0f} KB" if kb >= 10 else f"{kb:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def iso_now() -> str:
    """构建时刻。**只用来给人看**，绝不参与任何产物指纹。

    这条约束是踩出来的：content.json 里一旦带上构建时间，两次同样的构建
    就会得到不同的文件，那条「同一 commit 同一产物」的承诺当场作废。
    所以 content.json 的 build 段里没有时间字段，指纹也只由文件内容决定。
    """
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def source_stamp() -> str:
    """输入侧的时间戳：快照生成时刻。

    页面里要写「数据截至什么时候」时用这个，**不要用当前时间** ——
    数据什么时候新鲜是由快照决定的，不是由这次构建什么时候跑的决定的。
    用 iso_now() 会让页面在「快照早就过期了」的情况下依然显示刚刚更新过。
    """
    from util import read_json as _rj
    payload = _rj(DATA / "registry.json", {}) or {}
    return payload.get("generated_at") or ""


def digest(obj) -> str:
    """结构哈希：只关心内容，不关心 dict 的插入顺序与缩进。

    用途是把「构建产物的输入」压成一个短值写进 manifest —— 站点上的
    `content.json` 里带着它，客户端就能判断「我缓存的这份数据是不是新的」，
    不必下载完整产物再比。
    """
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def sha1_short(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def slugify(text: str) -> str:
    """锚点用。中文不能直接当 id（URL 里会被转义成一串 %E4%BD%A0），
    所以中文标签走「t-<sha1 前 8 位>」—— 稳定、可复现、短。"""
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(text)).strip("-").lower()
    if s and not re.search(r"[\u4e00-\u9fff]", str(text)):
        return s
    return "t-" + sha1_short(str(text))


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, obj) -> None:
    Path(path).write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


# ------------------------------------------------------------------ 时间
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def rfc822(iso_date: str) -> str:
    """2026-09-29 → 'Tue, 29 Sep 2026 00:00:00 +0000'。RSS 只认这个格式。

    刻意不用 datetime.strptime：它对本仓库用到的 `YYYY-MM-DD` 够用，
    但 sync.py 写进来的历史数据里混过 `YYYY-MM-DDTHH:MM:SSZ`，
    strptime 会直接抛异常并原样返回 —— 那会让 feed 里混进两种日期格式。
    """
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (iso_date or "").strip())
    if not m:
        return iso_date or ""
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    # Zeller 同余：算星期几，避免为了一行日期去 import datetime 的时区对象
    if mo < 3:
        mo += 12
        y -= 1
    k, j = y % 100, y // 100
    h = (d + 13 * (mo + 1) // 5 + k + k // 4 + j // 4 + 5 * j) % 7
    dow = _DAYS[(h + 5) % 7]
    return f"{dow}, {d:02d} {_MONTHS[int(m.group(2)) - 1]} {m.group(1)} 00:00:00 +0000"


def days_between(a: str, b: str):
    """两个 YYYY-MM-DD 相差多少天（b - a）。任一不可解析返回 None。

    不 import datetime 不是因为洁癖，是因为 build_site 的产物必须在
    「构建时零外部输入」的前提下可复现 —— 而 datetime.now() 一旦被误用，
    两次构建的产物就会不同，那条「同一 commit 同一产物」的承诺当场破。
    """
    ra = re.match(r"(\d{4})-(\d{2})-(\d{2})", a or "")
    rb = re.match(r"(\d{4})-(\d{2})-(\d{2})", b or "")
    if not ra or not rb:
        return None
    return _days(to_ordinal(int(ra.group(1)), int(ra.group(2)), int(ra.group(3))),
                 to_ordinal(int(rb.group(1)), int(rb.group(2)), int(rb.group(3))))


def to_ordinal(y: int, m: int, d: int) -> int:
    """公历 → 序数日。这是 Howard Hinnant 的 days_from_civil。"""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _days(a: int, b: int) -> int:
    return b - a
