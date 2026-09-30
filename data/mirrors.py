# -*- coding: utf-8 -*-
"""下载加速镜像清单 —— **一个必须联网核对、因此必须显式维护的配置文件**。

这个文件和 data/releases.json 是同一类东西，但性质相反：

- `releases.json` 是「我的包长什么样」，由脚本从 GitHub API 自动冻结，事实稳定。
- 本文件是「**别人家的服务**」，列的是第三方反代/加速站。
  它们随时可能关停、限速、投毒，**没有任何自动机制能替你保证它们活着**。

所以这里的原则是：

1. **只列经过实测的**。每个前缀都真下过文件，也确认过它支持 HEAD 与 Range
   （AGENTS 里记着结论）。没验过的地址不要往这里加。
2. **默认保守**。除 `direct` 外全部 `enabled_by_default: False`，
   因为把用户的下载流量交给第三方，是一个**需要用户知情同意**的决定，不是默认项。
3. **宁可空着**。某个镜像挂了就直接删掉这一行，前端会自动少一个候选——
   不要为了「看起来选择多」留一个连不上的地址。

## 前缀怎么用

`prefix + 原始 Release URL` 就是加速地址：

    原始: https://github.com/ice-wocker/iceBrowser/releases/download/v5.0.1/icebrowser.apk
    加速: https://gh-proxy.com/https://github.com/ice-wocker/iceBrowser/releases/download/v5.0.1/icebrowser.apk

所以每个前缀**必须以 `/` 结尾**。空字符串 `""` 表示直连 GitHub 官方。

## 前端的用法（不是「无脑用某个镜像」）

**当前默认只走 `direct`。** 这不是保守，是被实测逼出来的结论：

前端曾经实现过「fetch 并发测速、挑最快的源」，但那条路走不通 ——
GitHub Release 会 302 到 `release-assets.githubusercontent.com`，
而那一跳**不带 `Access-Control-Allow-Origin`**，三个反代同样不带。
浏览器因此读不到响应字节数，任何基于 fetch 的计时都恒为 0，
「自动选源」永远只会退回官方直连，还白花 4 次请求。

更麻烦的是它**看起来能用**：探针全失败后照样退回官方、页面照常下完，
没有任何报错。所以 check_site.py 里有一条守卫专门禁止 fetch 出现在
商店页的下载脚本里，防止以后有人「好心」把它加回来。

那加速靠什么？靠**并行建连**：小包单连接只有 0.7~0.9 MB/s，慢在建连
（TTFB 0.3~1.3s）而不是带宽，所以并行发起能实打实把总吞吐叠起来。
这一点见 `scripts/build_site.py` 里的 `STORE_JS`。

下面这四个前缀的作用是：**给用户一个显式可选项**。谁快谁慢完全看当时当地
（实测差 50 倍以上），页面不该替用户默认开启第三方中转。
"""

MIRRORS = [
    {
        "id": "direct",
        "label": "GitHub 官方",
        "prefix": "",
        "enabled_by_default": True,
        "note": "官方直连。没有中间人，也不依赖任何第三方服务活着。",
    },
    {
        "id": "ghproxy",
        "label": "gh-proxy.com",
        "prefix": "https://gh-proxy.com/",
        "enabled_by_default": False,
        "note": "国内反代，实测与直连同速（5.9 MB/s）。",
    },
    {
        "id": "ghfast",
        "label": "ghfast.top",
        "prefix": "https://ghfast.top/",
        "enabled_by_default": False,
        "note": "国内反代，实测约为直连的 3/4（4.6 MB/s）。",
    },
    {
        "id": "ghproxy_net",
        "label": "ghproxy.net",
        "prefix": "https://ghproxy.net/",
        "enabled_by_default": False,
        "note": "国内反代，本环境实测严重限速（0.09 MB/s），仅作候选。",
    },
]

# 说明：这里**故意不提供**「探测字节数」和「分块并发数」这类参数。
#
# 前者属于已被证伪的 fetch 测速方案（见上），留着只会诱导别人重新捡起来；
# 后者属于「多线程下载大文件」—— 实测同一文件开 1/2/4 条连接总吞吐都是 ~6.2 MB/s，
# 说明单连接吞吐固定、加连接不增带宽，所以本就不该有分块下载这个功能。
#
# 如果以后 GitHub 放宽了下载响应的 CORS 头，「按实测速度自动选源」才值得重做，
# 那时再把探测参数加回来。
