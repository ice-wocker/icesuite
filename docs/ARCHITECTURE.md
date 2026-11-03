# 架构与数据流

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
