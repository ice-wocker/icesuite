# ice 工坊 · 站点源码

> 一个作品集站点 + 应用商店，零第三方依赖，只用 Python 标准库从结构化数据渲染出纯静态 HTML。

**在线**：<https://ice-wocker.github.io/icesuite/> ·
**商店**：<https://ice-wocker.github.io/icesuite/store.html>

这个仓库是 [ice-wocker](https://github.com/ice-wocker) 全部项目的统一入口，
也是它自己的一个作品——因为它遵守同一套原则：**零第三方依赖、离线可用、体积可验证**。

它有两种用法，取决于你是谁：

- **访客**：直接打开商店页，一键下齐全部 8 个安装包。
- **开发者**：Fork 下来，改 `data/projects.py`，30 秒后得到一个属于你自己的同类站点。

---

## 为什么不用 MkDocs / VitePress

因为它们会给一个「主张零依赖」的账号加上一套会过期的构建链。

这个站的全部需求就是「把结构化数据渲染成 HTML，再放一份搜索索引」——
Python 标准库足够，产物是纯静态的：克隆下来双击 `index.html` 就能看，换任何托管都不用改代码。

代价是没有插件生态。以下功能都是手写的，因为它们都不需要依赖：

| 能力 | 实现 |
|---|---|
| 全站搜索 | 构建时预生成 `search.json`，运行时前端过滤 |
| 站点图标 | 直接用 `zlib` 手拼 PNG chunk，没引 Pillow |
| 死链检查 | `urllib` + 自己实现的重试策略 |
| 下载加速 | 按地区选源 + 并行建连（不测速、不多线程，见下） |

---

## 快速开始

```bash
python3 scripts/build_site.py     # 渲染出 site/，不需要装任何东西
open site/index.html              # 双击就能看，不用起服务
```

想改成自己的：

```bash
# 1. data/projects.py 里的 SITE["author"] 改成你的 GitHub 用户名
# 2. PROJECTS 换成你的仓库列表
# 3. 拉一份你自己的 Release 快照
python3 scripts/fetch_releases.py --write
# 4. 重新构建
python3 scripts/build_site.py
```

发布：把它推到 GitHub，在 Settings → Pages 里选 GitHub Actions，
`deploy.yml` 会自动接管。合并进 `main` 即上线。

---

## 结构

```
data/projects.py              内容源：站点文案、项目清单、亮点、已知限制
data/releases.json            Release 快照：版本号/体积/下载地址（脚本生成，勿手改）
data/mirrors.py               下载源清单 + 地区判定规则（加速可默认开，官方永远兜底）
scripts/fetch_releases.py     从 GitHub API 冻结 Release 元数据；--check 用于 CI 防过期
scripts/build_site.py         渲染器：把清单投影成 site/ 下的静态 HTML
scripts/check_site.py         自检：产物完整性、站内死链、下载链接可达、商店页一致性
site/                         构建产物（不入库）
```

**唯一真相源是 `data/projects.py`**，站点只是它的投影。
改内容只改这一个文件，不碰 HTML。

构建过程**不联网**：Release 事实读的是入库的快照文件，所以同一个 commit 永远产出同一份站点。
联网只发生在 `fetch_releases.py` 和 `check_site.py` 里。

---

## 应用商店

`store.html` 是本账号全部可安装应用的下载页，支持**一键下载全部**（8 个，66.8 MB）。

设计上有三条硬约束，每条都对应一个具体踩过的坑。

### 一、体积和版本号不手写

它们来自 `data/releases.json`，由 `scripts/fetch_releases.py` 从 GitHub Release 元数据冻结。
文案里要提体积就用 `{size}` 占位，构建时替换成真实值。

理由很实在：这类数字写死在文案里，**发一次版就变成假的，而且页面看起来一切正常**。
CI 里有个 job 专门对比快照与线上 Release——仓库发了新版却忘了重新生成快照，构建直接红。
这个 job 上线第一次跑就报错了，因为我自己测试时留了个假版本号在文件里。

### 二、一键下载不是打 ZIP

GitHub Pages 是纯静态托管，没有服务端可以打包。前端打包只有两条路，都不通：
引 JSZip 破了零依赖的口径，把 66.8 MB 读进内存手机上直接崩。

所以是**并行触发 8 个独立下载**。好处是单个失败不影响其他，
用户在系统通知栏里看到 8 个独立下载，断哪个重下哪个。

### 三、「从哪下」按地区自动选，「怎么下」靠并行建连

两件事分开看，因为一件有可靠的本地信号，另一件没有。

**「从哪下」：按地区选，不测速。**

直连 GitHub 的体验是**按地区两极分化**的，而且这个差异**稳定**：大陆普遍几百 KB/s
甚至断流，海外接近满速。既然稳定，就能在本地推断，一个请求都不用发：

| 信号 | 例子 | 来源 |
|---|---|---|
| 时区（主要） | `Asia/Shanghai` | `Intl.DateTimeFormat().resolvedOptions().timeZone` |
| 语言 / 地区 | `zh-CN` → `CN` | `navigator.language(s)` |
| 网络类型 | `2g` / `3g` | `navigator.connection.effectiveType`（若有） |

命中 → 默认启用加速；否则默认官方直连（海外直连本来就不慢，套反代只是多一跳）。
默认走加速的前提是**它完全透明**：页面顶部有状态条显示当前源，一点就能切回官方，
选择存 `localStorage`。加速源打不开时会显式回退并在界面说明，不静默降级。

**「怎么下」：并行建连；下面两条都是实测后否掉的。**

| 想法 | 实测 | 结论 |
|---|---|---|
| 多线程分块下载大文件 | 同一文件开 1 / 2 / 4 条连接，总吞吐都是 ~6.2 MB/s | ❌ 单连接吞吐固定，加连接不增带宽 |
| fetch 并发测速、自动选最快镜像 | 四个候选**全部读不到数据** | ❌ 下载响应不带 `Access-Control-Allow-Origin`，计时恒为 0 |
| 并行发起多个安装包 | 单连接速度依赖文件大小：58 MB = 2.4 MB/s，0.07 MB = 0.78 MB/s | ✅ 小包慢在建连（TTFB 0.3~1.3s），并行后总吞吐是各连接之和 |

第二条那个实现**已经写过、也撤掉了**，因为它失败得很安静：
GitHub Release 会 302 到 `release-assets.githubusercontent.com`，
那一跳不带 `Access-Control-Allow-Origin`，三个反代同样不带——浏览器拿不到字节数。
探针全失败后会自动退回官方直连，页面照常下完，用户不会察觉，
区别只是白花 4 次请求而「智能选源」从未生效。

`check_site.py` 里因此有两条守卫：**禁止 `fetch` 出现在商店页的下载脚本里**，
以及**必须存在地区判断函数且真的被调用、有状态条、有持久化**——防止有人
把「按地区选源」退化成「永远直连」或「永远某个反代」。

镜像清单在 `data/mirrors.py`。加速源之间的快慢是随机的（实测差 50 倍以上），
没有可靠的本地信号，所以那部分不猜，交给用户手动切。

---

## 自检

```bash
python3 scripts/check_site.py            # 完整检查（含外链 HEAD）
python3 scripts/check_site.py --skip-links   # 只查本地结构与一致性
python3 scripts/fetch_releases.py --check    # 快照是否过期（CI 用）
```

`check_site.py` 盯的是**「构建成功但站点坏掉」**这类问题，因为这类错不会自己浮出来：

- 站内链接指向不存在的页面（拼错 id 就白给一个 404）
- 商店页的体积/版本/可下载集合与 `releases.json` 不一致
- 一键下载的并行数被改回 1、或者实现与文案对不上
- 下载脚本里又出现了 `fetch`
- 外链 404（5xx 判为「存疑」并重试，只有 404/410 才算死链）

每条守卫都做过**变异测试**——注入对应缺陷确认会变红。
第一版里有两条是橡皮图章：只搜关键字，而注释里也有这个词，于是永远为真。
现在改成断言「被赋值 + 真的进了循环条件」，并在查找前先剥掉注释。

---

## 部署

合并进 `main` 后由 `.github/workflows/deploy.yml` 自动构建并发布到 GitHub Pages。
`build_site.py` 会同时产出 `CNAME`，自定义域名靠它。

换域名只需要改 `data/projects.py` 里的 `SITE["domain"]` 一处，
CI 有 job 专门校验它只出现一次。完整步骤见 `docs/DNS.md`。

---

## 许可

[MIT](LICENSE)。站点内容（项目文案）随仓库一并授权。
