# 架构与数据流

> 🌐 Language / 语言: 中文 · [English](ARCHITECTURE.en.md)

本文讲这个站点是怎么从「一份 GitHub 快照」变成「45 个文件」的。
想看行为说明去 [README](../README.md)，想看每条断言为什么存在去 [CHECKS](CHECKS.md)，
想看字段从哪来去 [DATA](DATA.md)。

## 0. 全景

```text
                    ┌──────────────────────────────┐
   GitHub API ─────►│  scripts/sync.py             │
   （每小时 / webhook）│  → data/registry.json        │  机器的事实
                    └──────────────────────────────┘
                                 │
                    ┌────────────▼─────────────────┐
   人 ─────────────►│  data/projects.py            │  文案、分组、亮点、已知限制
   （可选）          │  data/mirrors.py             │  下载源与地区判定
                    └────────────┬─────────────────┘
                                 │
                    ┌────────────▼─────────────────┐
                    │  scripts/overlay.py  load()  │  ← 合并规则的唯一入口
                    └────────────┬─────────────────┘
                                 │  {site, groups, projects, mirrors, registry}
              ┌──────────────────┼──────────────────┐
              │                  │                  │
      ┌───────▼──────┐   ┌───────▼───────┐  ┌───────▼────────┐
      │ insight.py   │   │ pages.py      │  │ build_site.py  │
      │ 派生：统计/   │   │ 五张新页面     │  │ 首页 / 商店 /  │
      │ 时间线/集合/  │   │               │  │ 详情 / 标签    │
      │ 体检          │   │               │  │                │
      └───────┬──────┘   └───────┬───────┘  └───────┬────────┘
              └──────────────────┼──────────────────┘
                                 │
                    ┌────────────▼─────────────────┐
                    │  site/  31 张页面 + 14 个文件 │
                    │  含 4 个 JSON + PWA 三件套    │
                    └────────────┬─────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
      ┌───────▼───────┐  ┌───────▼───────┐  ┌──────▼───────┐
      │ check_site.py │  │ mutate_v2.py  │  │ live_check.py│
      │ 本地产物对不对 │  │ 守卫能不能红   │  │ 线上那份对不对 │
      └───────────────┘  └───────────────┘  └──────────────┘
```

## 1. 为什么合并规则要单独一个文件

上一版这段逻辑写在 `build_site.load()` 里，而 `check_site` 想校验「页面上的东西和
清单一致」，只能通过 `importlib` 把整个渲染模块执行一遍、再调它的 `load()`。

两个后果：

1. 为了核对渲染结果，把渲染器整份跑了一遍——自检变慢，且会跟着渲染器的任何 import 一起挂。
2. 合并规则事实上有两份理解：一份在 `load()` 里，一份在调用方对返回值的假设里。

现在只有一个入口：`overlay.load()`。`build_site` 和 `check_site` 都调它，
谁也不许自己抄一遍合并逻辑。

## 2. 一次构建的完整顺序

顺序里有两处不能动，都在代码注释里标了：

```text
1. overlay.load()                 注册表 + 手写层 → 项目清单
2. insight.stats()                统计（stats.json 与数据页同源）
   insight.timeline()             时间线
   insight.collection_catalog()   集合
   insight.health(p)              逐项目体检
3. 清理 site/，写 style.css
4. 首页 / 商店 / 详情 / 标签 / 404
5. 五张新页面（pages.py）
6. stats.json / graph.json
7. PWA：icon-maskable.svg / manifest.json / sw.js
8. sitemap.xml / robots.txt / feed.xml / CNAME / .nojekyll
9. content.json                   ← 必须最后
```

**第 7 步在 content.json 之前**：`sw.js` 的缓存名要写「缓存的是哪一版」，
而这个版本号是产物指纹的前 12 位。反过来（先算指纹再写 sw.js）会让
`content.json` 漏掉 PWA 三个文件——这个错本版犯过一次，被自检抓出来了。

**第 9 步必须真的在最后**：`content.json` 是产物索引，早写一步就会漏掉
后面写的 `CNAME`、`sitemap.xml`、`feed.xml`。同一个错，同一版，抓了两次。

## 3. 可复现构建：一条必须守住的约束

`content.json` 的 `build.id` 是「全部文件内容」的结构哈希：

```python
ident = sha256(json.dumps({name: {"bytes":…, "sha256":…}}, sort_keys=True))
```

它**不含构建时间**。所以内容一样，id 就一样——不管在哪台机器、什么时候构建。
反过来，id 变了就一定是内容变了。这就是「同一 commit 同一产物」这句话的可检验形式。

代价是：任何形式的「当前时间」都不许进产物。

- `update.json` 的 `generated_at` 取**快照时间**（`util.source_stamp()`），不是构建时间。
  数据什么时候新鲜，由快照决定，不由这次构建什么时候跑的决定的。
  混在一起会让页面在「快照早就过期」时依然显示「刚刚更新过」。
- 统计里算「距今多少天」用序数日相减（`util.days_between`），**不 `import datetime`**：
  只要 `datetime.now()` 有被误用的一丝可能，这条承诺就守不住。

`check_site.py --reproducible` 会再构建一次到临时目录，逐字节比对。CI 每次都跑。

## 4. 数据怎么流到页面

```text
registry.json
  projects.<repo>.latest.asset.{name,size,digest,url}
        │
        ├── derive() ──► version / size_text / asset_sha256 / dl_release
        │                 （手写层不许覆盖，见 DATA.md 的 MACHINE_FIELDS）
        │
        ├── installable = bool(dl_release)      ← 不再看手写的 platform
        │
        └── history[] ──► insight.timeline() ──► latest.html / timeline.html
                                        └────► 详情页的「更新记录」

projects.py（手写）
  pitch / summary / tags / highlights / known_limits
        │
        ├── overview 卡片、商店行、详情页
        └── _short() 压成一行给对比表（按标点断，不硬截半个词）
```

`installable` 这一行是这一版之前最重要的一个修复：它从「手写字段」变成「证据」。
手写字段漏一处，那个应用在商店上就永远缺一个下载按钮——这才是「新项目只能后加」
的物理原因。现在由「Release 里到底有没有一个可下载的包」决定。

## 5. 页面外壳只有一个实现

所有页面都过 `build_site.page()`：`<head>`、导航、页脚、主题脚本、Service Worker 注册
都在这里出现一次。`pages.py` 只返回 `(title, body, meta)`，不碰外壳。

理由：一张页面漏了 `canonical`、或把主题脚本放到样式表之后，都是「只有某一张页面坏」
的那种问题。外壳只有一份，就不可能只坏一张。

导航高亮用 `aria-current="page"` 而不是只有 CSS 类——读屏用户靠它判断自己在哪，
颜色对他们不存在。`_emit()` 默认把当前页设为高亮，不传就等于「我在哪」没被表达。

## 6. 页面专属脚本必须在 `</body>` 之前

`page(extra_head=…)` 的命名有点误导：它渲染到 `</body>` 前，不是 `</head>`。

这是踩出来的：表头排序脚本一度被塞进 `<head>`，`querySelectorAll` 执行时 DOM
还不存在，于是「点表头没反应」，而静态检查只查了 `data-sort` 属性在不在，全绿。

## 7. 客户端 JavaScript 一共就这些

| 脚本 | 干什么 | 失效时 |
|---|---|---|
| `THEME_JS` | 把 `data-theme` 挂到 `<html>`，防首屏闪白 | 会闪一帧，功能不受影响 |
| `THEME_BTN_JS` | 三档主题循环，存 localStorage | 按钮没反应，默认跟随系统 |
| `REVEAL_JS` | 卡片淡入 | CSS 有 1.2s 兜底动画，内容一定可见 |
| `SEARCH_JS` | 预生成索引 + 前端过滤，中文二元切分 | 显示「索引没加载到」并给出标签索引入口 |
| `STORE_JS` | 按地区选源、多源轮转、并行下载 | 退回官方直连 |
| `INSTALL_JS` | 装到桌面 + 离线条 + 注册 SW | 什么都不显示，页面照常 |
| `COMPARE_JS` | 表头排序 | 表头不可点 |

没有框架、没有构建步骤、没有 polyfill。全部内联进 HTML 的 `<script>`，
由 `js_syntax.py` 用 `node --check` 逐段验语法——这条守卫的由来见 [CHECKS](CHECKS.md)。

## 8. 三个层次的检查

| 脚本 | 问的问题 | 需要网络 | 什么时候跑 |
|---|---|---|---|
| `check_site.py` | 本地产物对不对 | 可选（`--skip-links`） | 每次构建后 |
| `mutate_test.py` / `mutate_v2.py` | 守卫自己会不会红 | 否 | CI 的 `guards` job |
| `live_check.py` | 线上那份对不对 | 是 | 部署后 / 每周定时 |

第三个是这一版新增的，理由很直接：这个仓库的两次事故都是「本地全绿、线上过期」。
本地检查抓不到这一类，因为它手里那份本来就是对的。
