# ice 工坊 · 站点源码

`https://icesuite.eu.org` 的生成器与内容源。零依赖，只用 Python 标准库。

## 结构

```
data/projects.py              内容源：站点文案、项目清单、亮点、已知限制
data/releases.json            Release 快照：各项目的版本号/体积/下载地址（由脚本生成，勿手改）
data/mirrors.py               下载源清单（默认只有官方直连；第三方前缀是显式备选）
scripts/fetch_releases.py     从 GitHub API 拉 Release 元数据；--check 用于 CI 防过期
scripts/build_site.py         渲染器：把清单投影成 site/ 下的静态 HTML
scripts/check_site.py         自检：产物完整性、站内死链、下载链接可达、商店页一致性
site/                         构建产物（不入库）
```

## 应用商店

站点带一个 `store.html`——本账号全部可安装应用的下载页，支持**一键下载全部**。

设计上有三条硬约束：

**一、体积和版本号不手写。** 它们来自 `data/releases.json`，
由 `scripts/fetch_releases.py` 从 GitHub Release 元数据冻结。
清单文案里要提体积就用 `{size}` 占位，构建时替换成真实值。
理由很实在：这类数字写死在文案里，发一次版就变成假的，
而且页面看起来一切正常。CI 里有个 job 专门对比快照与线上 Release，
仓库发了新版却忘了重新生成快照，构建会直接红。

**二、一键下载不是打 ZIP。** GitHub Pages 是纯静态托管，没有服务端可以打包；
前端打包要么引 JSZip（破了零依赖的口径），要么把几十 MB 的 APK 读进内存
（手机上会直接崩）。所以就是**并行触发 8 个下载**，中间有进度条、可以停。
好处是单个失败不影响其他，用户在系统通知栏里看到 8 个独立下载，断哪个重下哪个。

**三、下载速度靠「并行建连」，不是靠「多线程」或「换镜像」。**
这两条都是实测之后被否掉的，结论值得留在仓库里：

| 想法 | 实测 | 结论 |
|---|---|---|
| 多线程分块下载大文件 | 同一文件开 1 / 2 / 4 条连接，总吞吐都是 ~6.2 MB/s | ❌ 单连接吞吐固定，加连接不增带宽 |
| fetch 并发测速、自动选最快镜像 | 四个候选**全部读不到数据** | ❌ 下载响应不带 `Access-Control-Allow-Origin`（含 GH 302 之后的 release-assets 与三个反代），计时恒为 0 |
| 并行发起多个安装包 | 单连接速度依赖文件大小：58 MB = 2.4 MB/s，0.07 MB = 0.78 MB/s | ✅ 小包慢在建连（TTFB 0.3~1.3s），并行后总吞吐是各连接之和 |

那个 fetch 测速的实现**已经写过、也撤掉了**——因为它失败得很安静：
探针全部失败后会自动退回官方直连，页面照常下完，用户不会察觉，
区别只是白花 4 次请求而「智能选源」从未生效。
`check_site.py` 里因此有一条守卫，禁止 `fetch` 出现在商店页的下载脚本里。

镜像清单在 `data/mirrors.py`，默认只走 GitHub 官方。

## 本地使用

```bash
python3 scripts/build_site.py                              # 生成 site/
python3 scripts/check_site.py                              # 自检（含外链 HEAD）
python3 scripts/fetch_releases.py --write                  # 发了新版本后刷新 Release 快照
open site/index.html                                       # 双击就能看，不需要起服务
```

构建过程**不联网**：Release 事实读的是入库的快照文件，
所以同一个 commit 永远产出同一份站点。联网只发生在 `fetch_releases.py` 和 `check_site.py` 里。

## 为什么又造了一个静态站生成器

因为它必须和这个账号的主张一致：**零依赖**。

引 MkDocs 或 VitePress 意味着多一套 Python/Node 依赖、多一个会过期的构建链。
这里的全部需求只是「把结构化数据渲染成 HTML + 放一份搜索索引」，
标准库足够，而且产物是纯静态的——克隆下来双击就能看，换任何托管都不用改一行代码。

站点本身也是 `frontier-knowledge-base` 那套 `build_site.py` 的同门实现，
两个站共享同一套设计取舍。

## 换域名

只需要改 `data/projects.py` 里的 `SITE["domain"]` 一处。
`build_site.py` 会据此生成 `site/CNAME`，CI 里有 job 专门校验它只出现一次。
完整步骤见 `docs/DNS.md`。

## 发布

合并进 `main` 后由 `.github/workflows/deploy.yml` 自动构建并发布到 GitHub Pages。
`scripts/build_site.py` 会同时产出 `CNAME`，自定义域名就靠它。
