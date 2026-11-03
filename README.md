# ice 工坊 · 站点源码

> **English:** Zero-dependency portfolio + app-store static site in pure Python stdlib. Fork it and make it yours.

[![CI](https://github.com/ice-wocker/icesuite/actions/workflows/ci.yml/badge.svg)](https://github.com/ice-wocker/icesuite/actions)
[![Release](https://img.shields.io/github/v/release/ice-wocker/icesuite)](https://github.com/ice-wocker/icesuite/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Live](https://img.shields.io/badge/Live-Demo-brightgreen)](https://ice-wocker.github.io/icesuite/)

> 一个作品集站点 + 应用商店，零第三方依赖，只用 Python 标准库从结构化数据渲染出纯静态 HTML。

**在线**：<https://ice-wocker.github.io/icesuite/> ·
**商店**：<https://ice-wocker.github.io/icesuite/store.html> ·
**最新更新**：<https://ice-wocker.github.io/icesuite/latest.html> ·
**时间线**：<https://ice-wocker.github.io/icesuite/timeline.html> ·
**对比**：<https://ice-wocker.github.io/icesuite/compare.html> ·
**集合**：<https://ice-wocker.github.io/icesuite/collections.html> ·
**数据**：<https://ice-wocker.github.io/icesuite/stats.html> ·
**RSS**：<https://ice-wocker.github.io/icesuite/feed.xml>

> **文档导航**
> [本文件](README.md)（门面 + 设计取舍） · [架构与数据流](docs/ARCHITECTURE.md) ·
> [自检与守卫](docs/CHECKS.md) · [部署与域名](docs/DEPLOY.md) ·
> [机器可读产物](docs/CONTRACTS.md) · [离线与可安装](docs/PWA.md) ·
> [数据字典](docs/DATA.md) · [开发指南](docs/DEVELOPING.md) ·
> [故障排查](docs/TROUBLESHOOTING.md) · [深问答](docs/FAQ.md) ·
> [更新日志](CHANGELOG.md) · [域名切换手册](docs/DNS.md)

---

## 一句话说清这一版在干什么

上一版把「版本号要人推代码」和「新项目只能后加」这两件事挪进了流水线。
这一版接着往下做同一件事：**把「站点自己有多少东西、准不准、能不能离线」也变成流水线能回答的问题。**

具体是四件事，每一件都能在页面上点到、在文件里核到：

1. **多五张页面**——最新更新、发版时间线、横向对比、策展集合、数据。
   每一张都不是"再换个排版"，而是回答一个原来站内没有答案的问题。
2. **多三个机器可读产物**——`stats.json`（站点全部数字）、`graph.json`（项目关系）、
   `content.json`（产物逐文件 sha256 + 构建指纹）。站点从此有三个稳定的对外契约。
3. **多一层"能装、能离线"**——Web App Manifest + Service Worker。
   装到桌面之后不联网也能翻站点；下载行为仍然需要网络，这一点不粉饰。
4. **守卫从 15 条涨到 44 条**，其中 29 条是这一版新增的，全部走过「注入缺陷 → 必须变红」的自证。

---

## 站点里有什么

### 五张核心页面

| 页面 | 它回答的问题 | 为什么原来没有 |
|---|---|---|
| [`index.html`](https://ice-wocker.github.io/icesuite/) | 这个账号里有什么 | 原来有，但只有卡片墙；现在加了六个入口和「最近更新」 |
| [`store.html`](https://ice-wocker.github.io/icesuite/store.html) | 什么能下载、多大、怎么下 | 原来有 |
| `latest.html` | 最近有什么新东西 | 原来只能一个个项目页翻 |
| `timeline.html` | 一共发过多少版、节奏如何 | Release 正文本来就是史料，但从没被摊平看过 |
| `compare.html` | 同类项目摆在一起差在哪 | 原来要开四个标签页自己记 |
| `collections.html` | 按主题看有什么 | 标签索引是穷举，集合是编排 |
| `stats.html` | 页面上的数字凭什么是这个数 | 没有数据页，读者只能信 |

### 三个机器可读产物

| 文件 | 给谁用 | 里面是什么 |
|---|---|---|
| `update.json` | 应用自带的「检查更新」 | 版本 / 体积 / sha256 / 直链，不必解析 HTML |
| `stats.json` | 想核对本站数字的人 | 每月发版、语言分布、体积榜、下载量，与数据页同源 |
| `graph.json` | 想做可视化 / 推荐的人 | 节点=项目，边=同分组或同标签，权重只由共享标签数决定 |
| `content.json` | 想核对站点完整性的人 | 每个文件的 sha256 + 字节数 + 构建指纹（`build.id`） |

细节与字段语义见 [机器可读产物](docs/CONTRACTS.md)。

---

## 三条硬约束（这一版新增的，都进了 CI）

### 1. 构建必须可复现：同一份输入 → 逐字节相同的产物

`content.json` 的 `build.id` 是全部产物内容的结构哈希，**不含构建时间**。
所以「同一 commit 同一产物」这句话从一个承诺变成了一个能检验的事实：

```bash
python3 scripts/check_site.py --reproducible
# 内部会再构建一次到临时目录，逐字节比对。任何时间戳/随机数混进产物，这里立刻红。
```

> 这条约束抓到了本版一个真实缺陷：`update.json` 的 `generated_at` 一度写成构建时刻，
> 于是两次同样的构建产出了不同文件。现在它取的是**快照时间**——数据什么时候新鲜
> 由快照决定，不由这次构建什么时候跑的决定的。这两件事混在一起，
> 页面就会在「快照早就过期」的情况下依然显示「刚刚更新过」。

### 2. 线上线下必须对得上

本地全绿不代表线上那份是对的。上一版之前出过两次这样的事故：
店里挂着 v2.6.0，而 Release 已经 v2.7.1，**构建和自检都绿着**。

所以现在有一个独立的 `scripts/live_check.py`，跑在部署之后：

```bash
python3 scripts/live_check.py --retries 8 --sample 4
```

它比对的是能证伪的东西：产物指纹、`update.json` 里的版本与 sha256、
以及**抽样下载 APK 实算 sha256**。最后这一条是唯一能证明「那个包就是那个包」的办法。

### 3. 守卫自己必须先被证伪

`mutate_test.py`（15 条）+ `mutate_v2.py`（29 条）。做法是往产物里注入缺陷，
逐条确认自检会红，**并且红在预期的原因上**。只变红不核对不算——它可能是被别的东西撞红的。

这一版新增的守卫里有 4 条第一次写出来就是橡皮图章，是变异测试当场抓出来的：

| 橡皮图章 | 它当时在骗什么 |
|---|---|
| 「相关项目存在」只查全站有没有这个词 | 删掉 21 张详情页里的 20 张，照样绿 |
| 「集合页有卡片」只数全站 `.cardhit` 总数 | 一个集合渲染成空壳、另一个多渲染几张，总数不变 |
| 「首页有 stats.html 入口」查全文 | 页脚里也有一份，入口区块删了还能绿 |
| 变异测试自己：改页面的用例都被 `content.json` 那条先抓走 | 27 条新守卫里有一批从没被真正验过 |

最后一条最值得说：**变异测试本身也会变成橡皮图章**。所以 `mutate_v2.py` 里所有
「改页面」的用例都会同步刷新 `content.json` 里那个文件的哈希——否则每条都会先被
完整性校验抓走，看起来全绿，实际上只是在测同一条断言。

---

## 快速开始

```bash
python3 scripts/sync.py             # 从 GitHub 同步仓库与 Release（需 GH_TOKEN；不带则跳过）
python3 scripts/build_site.py       # 渲染出 site/，不需要装任何东西
open site/index.html                # 双击就能看，不用起服务
python3 scripts/check_site.py       # 自检：结构、一致性、外链、内联 JS 语法
python3 scripts/check_site.py --reproducible   # 再加一条：两次构建逐字节比对
python3 scripts/mutate_test.py      # 守卫自证（老页面 / 老产物，15 条）
python3 scripts/mutate_v2.py        # 守卫自证（新产物 / 新页面 / PWA，29 条）
python3 scripts/live_check.py       # 核对**线上**那份（需要网络）
```

产物指纹（可选核对）：

```bash
python3 -c "import json;print(json.load(open('site/content.json'))['build'])"
# {'id': '…', 'files': 45, 'bytes': 665364, 'pages': 31}
```

## 加一个项目 / 发一个版本，要做什么

**什么也不用做。**

- **新仓库**：在 GitHub 上建库、推代码。下一次 `sync` 之后它就会出现在站点上，
  卡片文案取仓库描述，标注「自动收录」。
- **新版本**：打 tag、发 Release、传 APK。最多一小时后商店页就换新版。
  想让它是秒级的，去那个应用仓库配一个 webhook →
  `https://api.github.com/repos/ice-wocker/icesuite/dispatches`，body `{"event_type":"release"}`。
- **写介绍**：想让它长得不像自动生成，就在 `data/projects.py` 里加一条同 `repo` 的条目，
  只写你想覆盖的字段。版本号之类的别抄，抄了就会过期。

---

## 目录

```text
data/registry.json      自动同步的快照（勿手改）
data/projects.py        手写叠加层：文案、分组、亮点、已知限制
data/mirrors.py         下载源与地区判定（手写，镜像站没有可靠信号）
scripts/sync.py         拉 GitHub → registry.json
scripts/overlay.py      合并规则的唯一入口（build 与 check 共用）
scripts/insight.py      派生数据：统计、时间线、集合、体检
scripts/pages.py        新增五张页面的渲染器
scripts/app_assets.py   PWA：manifest / service worker / 图标
scripts/build_site.py   渲染 site/
scripts/check_site.py   自检（含内联 JS 语法、可复现构建）
scripts/js_syntax.py    内联 JavaScript 的 node --check
scripts/mutate_test.py  变异测试（老守卫，15 条）
scripts/mutate_v2.py    变异测试（新守卫，29 条）
scripts/live_check.py   线上核对（部署后跑）
```

详见 [架构与数据流](docs/ARCHITECTURE.md)、[自检与守卫](docs/CHECKS.md)、
[部署与域名](docs/DEPLOY.md)、[机器可读产物](docs/CONTRACTS.md)。

---

## 它不做什么

- **不做评论、评分、统计**：要后端、要防滥用、要 GDPR，和「零依赖、无追踪、无 Cookie」直接冲突。
- **不自动编介绍**：`registry.json` 提供事实，文案要么是人写的，要么是从仓库描述原样取的。
- **不推算校验值**：拿不到 `sha256` 就是 `null`，不会从版本号猜一个。
- **不推算 `versionCode`**：`2.7.1` 不猜成 `2710`。猜错会让用户以为「已是最新」，永远收不到更新。
- **不假装离线能下载**：离线时能翻站点、能看版本号与 sha256，但 APK 一定下不下来。
  Service Worker 只缓存同源 GET，跨域的 Release 资产不进缓存——冻在缓存里只会让人以为是本站坏了。
- **不自动刷新页面**：用户可能正在下文件，刷新会把它打断。

## License

MIT
