# ice 工坊 · 站点源码

> **English:** Zero-dependency portfolio + app-store static site in pure Python stdlib. Fork it and make it yours.

[![CI](https://github.com/ice-wocker/icesuite/actions/workflows/ci.yml/badge.svg)](https://github.com/ice-wocker/icesuite/actions)
[![Release](https://img.shields.io/github/v/release/ice-wocker/icesuite)](https://github.com/ice-wocker/icesuite/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Live](https://img.shields.io/badge/Live-Demo-brightgreen)](https://ice-wocker.github.io/icesuite/)

> 一个作品集站点 + 应用商店，零第三方依赖，只用 Python 标准库从结构化数据渲染出纯静态 HTML。

**在线**：<https://ice-wocker.github.io/icesuite/> ·
**商店**：<https://ice-wocker.github.io/icesuite/store.html> ·
**标签**：<https://ice-wocker.github.io/icesuite/tags.html> ·
**RSS**：<https://ice-wocker.github.io/icesuite/feed.xml>

> **文档导航**
> [本文件](README.md)（门面 + 设计取舍） · [架构与数据流](docs/ARCHITECTURE.md) ·
> [自检与守卫](docs/CHECKS.md) · [部署与域名](docs/DEPLOY.md) ·
> [更新日志](CHANGELOG.md) · [域名切换手册](docs/DNS.md)

这个仓库是 [ice-wocker](https://github.com/ice-wocker) 全部项目的统一入口，
也是它自己的一个作品——因为它遵守同一套原则：**零第三方依赖、离线可用、体积可验证**。

它有两种用法，取决于你是谁：

- **访客**：直接打开商店页，一键下齐全部 12 个安装包；新版本一小时内自动上站。
- **开发者**：Fork 下来，改 `data/projects.py` 里的文案，30 秒后得到一个属于你自己的同类站点。

> **这一版最大的变化：站点自己读 GitHub。**
> 仓库清单、版本号、包名、体积、sha256、发布时间全部自动同步（`scripts/sync.py`），
> 每小时一次。**新项目不用登记，发新版不用推代码** —— 原来这两件事都要人记得改两个地方，
> 而两次都真的忘了：商店页挂着 v2.6.0 时线上已经是 v2.7.1。

---

## 为什么不用 MkDocs / VitePress

因为它们会给一个「主张零依赖」的账号加上一套会过期的构建链。

这个站的全部需求就是「把结构化数据渲染成 HTML，再放一份搜索索引」——
Python 标准库足够，产物是纯静态的：克隆下来双击 `index.html` 就能看，换任何托管都不用改代码。

代价是没有插件生态。以下功能都是手写的，因为它们都不需要依赖：

| 能力 | 实现 |
|---|---|
| 全站搜索 | 构建时预生成 `search.json`，运行时前端过滤；中文按二元切分，键盘可操作 |
| 站点图标 | 手写 `icon.svg`，没有引任何素材库 |
| 死链检查 | `urllib` + 自己实现的重试策略 |
| 下载加速 | 按地区选源 + 并行建连（不测速、不多线程，见下） |
| 主题切换 | 三档（跟随系统/浅色/深色），选择存 `localStorage`，首屏无闪烁 |
| 可被抓取 | `canonical` / `sitemap.xml` / `robots.txt` / RSS / JSON-LD，全部构建时生成 |
| 标签索引 | 从清单反推，双向校验（不多不少） |
| 自动发现 | `sync.py` 读 GitHub API → `registry.json`；新仓库/新版本零登记 |
| 增量清单 | `update.json`：版本 / 体积 / sha256 / 直链，客户端不必解析 HTML |
| 更新记录 | Release 正文自己就是 changelog，渲染成每个应用的版本史 |
| 校验安装包 | 详情页给出 `sha256sum` 命令，值取自 Release 资产元数据 |

---

## 快速开始

```bash
python3 scripts/sync.py           # 从 GitHub 同步仓库与 Release（需 GH_TOKEN；不带则跳过）
python3 scripts/build_site.py     # 渲染出 site/，不需要装任何东西
open site/index.html              # 双击就能看，不用起服务
python3 scripts/check_site.py     # 自检：结构、一致性、外链
python3 scripts/mutate_test.py    # 守卫自证：注入 15 种缺陷，确认自检会红
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

## 目录

```text
data/registry.json    自动同步的快照（勿手改）
data/projects.py      手写叠加层：文案、分组、亮点、已知限制
data/mirrors.py       下载源与地区判定（手写，镜像站没有可靠信号）
scripts/sync.py       拉 GitHub → registry.json
scripts/build_site.py 渲染 site/
scripts/check_site.py 自检
scripts/mutate_test.py 变异测试（守卫自证）
```

详见 [架构与数据流](docs/ARCHITECTURE.md)、[自检与守卫](docs/CHECKS.md)、[部署与域名](docs/DEPLOY.md)。

## 它不做什么

- **不做评论、评分、统计**：要后端、要防滥用、要 GDPR，和「零依赖、无追踪、无 Cookie」直接冲突。
- **不自动编介绍**：`registry.json` 提供事实，文案要么是人写的，要么是从仓库描述原样取的。
- **不推算校验值**：拿不到 `sha256` 就是 `null`，不会从版本号猜一个。

## License

MIT
