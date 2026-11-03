# 架构与数据流

<<<<<<< HEAD
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
=======
> 一次同步、一次构建、一次点击，分别发生了什么。
> 想改文案去 `data/projects.py`；想加项目、发新版，**什么都不用改**。

## 1 自动发现：站点自己去读 GitHub

```text
GitHub API                     （每小时 / webhook / 手动）
  ↓  scripts/sync.py
data/registry.json             （快照，入库：仓库清单、Release、包名、体积、sha256、语言、话题）
  ↓  scripts/build_site.py + data/projects.py（可选叠加：介绍、亮点、已知限制）
site/                          （纯静态产物，不入库）
```

**这是这一版最重要的结构变化。** 原来 `data/projects.py` 与
`scripts/fetch_releases.py` 里的 `WATCHED` 各有一份手写清单，两处都要人登记：

| 原来 | 后果 | 现在 |
|---|---|---|
| 新仓库不写进 `PROJECTS` / `WATCHED` | 站点永远看不到它，必须先推一次代码 | 自动发现，上线当天就在 |
| 发新版本不跑 `--write` 再推 | 商店页停在旧版本（真的发生过：挂着 v2.6.0 而线上是 v2.7.1） | 每小时自动同步 |
| 一个 Release 里多个 APK | 取「第一个 `.apk`」，于是 3.2 MB 的 debug 包冒充 622 KB 的正式包 | 按 `debug/unsigned` → `arm64` → 体积排序挑主包 |

`data/projects.py` 现在只写机器查不到的东西。它有两个作用：

1. **覆盖**：写 `repo` 的条目覆盖自动值的同名字段（文案、分组、标签、亮点…）。
   没写的字段继续用自动值 —— 版本号不需要在这里抄一遍。
2. **不写也行**：`registry.json` 里有、这里没有的仓库会自动生成一张卡，
   文案取仓库描述，并标「自动收录」。页面上的「关于这个项目」列的是
   Star / 最近提交 / 发版次数这类**能在 GitHub 上点开核实**的事实，不编。

`sync.py` 的三个原则：

- **单个仓库失败不毁整次同步**：网络抽风 ≠ 对方删了版本。
- **有变化才提交**：每小时跑一次也不会把仓库刷成空提交。
- **取不到就留 null**：例如拿不到 `sha256` 就写 `null`，从不从版本号推算 —— 猜错会让用户以为「已是最新」。

## 2 布局

```text
data/
  registry.json   自动同步的快照（勿手改）
  projects.py     手写叠加层：SITE / GROUPS / PROJECTS 文案
  mirrors.py      下载源清单 + 地区判定规则（手写：镜像站是别人家的服务，没有可靠信号）
scripts/
  sync.py         拉 GitHub → registry.json
  build_site.py   渲染 site/
  check_site.py   结构 / 一致性 / 外链自检
  mutate_test.py  往产物注入缺陷，确认自检会红
  assert_pages.py 断言每个仓库都有页面
```

没有插件、没有模板引擎、没有配置合并。`build_site.py` 用 f-string 拼 HTML，
`load()` 用 `exec()` 把 `data/*.py` 当配置读进来——这两件事在正经项目里都是坏味道，
在这里是刻意的：**依赖越少，三年后还能构建的概率越高**。

构建过程不联网：同一份输入永远产出同一份站点，CI 里有一条 job 专门验证这一点。

## 3 页面骨架：一件事只写一次

`page()` 是唯一的页面外壳。导航项由 `nav_items()` 生成——加一个导航项只需要改一处。
这条规则有代价：任何「某张页面想多一个导航项」的临时需求都变得麻烦。
值得，因为反过来（每页手写导航）的失败方式更糟：**总有几页会被忘掉，
而界面上完全看不出来，只是少一个入口**。

`<head>` 里的顺序是刻意的：

```text
charset → viewport → title → description → robots → color-scheme
        → 主题脚本（必须在样式表之前）→ 样式表 → canonical / og → JSON-LD
```

主题脚本提前是硬约束：晚一行，深色系统的用户就会先看到一帧浅色。
`check_site.py` 里那条守卫**比较的是脚本文本与样式表标签的先后**，
不是「`data-theme` 这个字符串在哪」——后者永远在第二行，是橡皮图章。

## 4 增量产物

| 产物 | 为什么要有 |
|---|---|
| `update.json` | 机器可读的版本清单（版本 / 体积 / sha256 / 直链）。客户端查更新不必解析 HTML |
| `search.json` | 构建期预生成索引，运行时前端过滤，中文按二元切分 |
| `feed.xml` | 按 Release 推送。文案微调不值得推给任何人 |
| `sitemap.xml` / `robots.txt` | 可被抓取；404 页 noindex，本就不该进 sitemap |

`update.json` 里的 `sha256` 来自 GitHub 的资产元数据（`digest` 字段），
详情页把它渲染成可整段复制的 `sha256sum` 命令。

## 5 自检与变异测试

`check_site.py` 二十来类检查。其中几条是踩出来的：

- **CSS 大括号配平**：一条没闭合的 `@media` 会让其后**所有规则失效**，
  页面变成无样式纯文本，而文件 HTTP 200、浏览器不报错。
- **`<a>` 不能嵌套 `<a>`**：卡片内既有详情链接又有标签链接。浏览器不报错，
  它当场把内层 `<a>` 提出来，卡片被拆成两半，页面上多出几个幽灵方块。
- **卡片数与项目数相等**：这一条把「新项目上不了站」变成构建期错误。
- **每个仓库都有页面**：`assert_pages.py`，registry 里的仓库一个都不能漏。

`mutate_test.py` 是这些守卫的自证：往产物里注入 15 种缺陷，逐条确认自检会红。
上一版有三条守卫是橡皮图章（注入缺陷后照样全绿），就是它抓出来的。

## 6 部署链路

```text
push（data/ 或 scripts/ 变化）
  └─→ deploy.yml   构建 → 断言产物 → 自检 → upload-pages-artifact → deploy-pages
schedule（每小时）
  └─→ sync.yml     sync.py → 有变化就提交 data/registry.json → 触发 deploy
repository_dispatch(release)
  └─→ sync.yml     其它仓库发版时秒级同步（需在各仓库配 webhook）
```

`sync.yml` 用 `SYNC_PAT`（如果配了）而不是默认 token 推提交：默认 token 推的提交
**不会触发** `deploy.yml`（GitHub 防递归），那样同步完站点更新不了，而且没有任何报错。
没配 `SYNC_PAT` 时它会显式 `gh workflow run deploy.yml` 兜底。
>>>>>>> f5839e68205838e0d618905335f067bec3fd5355
