# 数据字典：一个项目的每个字段从哪来

站点上每张卡片、每行表格、每个数字，最终都来自 `overlay.load()` 返回的一份结构。
这份文档逐字段写清「它从哪来、谁能改它、取不到时是什么」。

写它的理由很实际：这一版把合并规则抽到了 `scripts/overlay.py`，
如果不同时写清字段来源，下一个人改文案时会不知道「版本号到底该不该在
`data/projects.py` 里写」——而这个问题答错的代价是这个站点最初的两起事故。

## 三个来源，优先级从高到低

```text
data/registry.json   ← scripts/sync.py 从 GitHub API 拉取，机器的事实
data/projects.py     ← 人写的叠加层，只管"怎么描述"
派生                  ← build_site / insight 从上面两份算出来的
```

合并规则只有一份，在 `overlay.load()` 里。`build_site.py` 和 `check_site.py` 都调它——
两份实现必然漂移，而漂移的表现是「页面和清单对不上，但两边都说自己对」。

## 机器字段：手写层不许覆盖

这几项由 `MACHINE_FIELDS` 明确列出。就算 `data/projects.py` 里抄了一份，也会被忽略：

| 字段 | 来源 | 取不到时 |
|---|---|---|
| `version` | Release 的 `tag_name` | `""`（页面显示「—」） |
| `published_at` | Release 的 `published_at` | `""` |
| `size_bytes` / `size_text` | 资产的 `size` | `0` / `""` |
| `asset_name` | 资产的 `name` | `""` |
| `dl_release` | 资产的 `browser_download_url` | `""` |
| `asset_sha256` | 资产的 `digest`（去掉 `sha256:` 前缀） | `""` → `update.json` 里写 `null` |
| `downloads` | 资产的 `download_count` | `0` |
| `prerelease` | Release 的 `prerelease` | `false` |

**为什么不许覆盖**：手抄的版本号过期，正是这个站点前两次事故的形状
（页面上 v2.6.0，线上已经是 v2.7.1）。字段一旦允许人写死，
那个错误就有了第二个发生位置。

## 手写字段：只有人能给的

| 字段 | 含义 | 缺省行为 |
|---|---|---|
| `pitch` | 一句话介绍，支持 `<b>` `<code>` 等白名单行内标签 | 取仓库描述 |
| `summary` | 两三句展开 | 取仓库描述（与 `pitch` 同源时页面**不重复渲染**） |
| `group` | 归到哪个分组 | 按形态：android → `apps`，site → `sites`，其余 `code` |
| `tags` | 标签 | 取 GitHub 的 `topics` |
| `metrics` | 详情页顶部的事实卡，`[(标签, 值)]` | 空 |
| `highlights` | 「技术亮点」清单，`[(标题, 说明)]` | 空 → 页面改成渲染「关于这个项目」的可核实事实 |
| `known_limits` | 「已知限制」清单 | 空（不显示该区块） |
| `status` | `mature` / `active` / `beta` | 有 Release → `mature`，否则 `beta` |
| `min_android` / `arch` | 最低系统 / ABI | `""`（页面显示「—」，不猜） |
| `installation` | 安装说明 | `""` |
| `store_note` | 商店页备注 | `""` |

文案里可以写 `{size}` 占位，构建时替换成 Release 里的真实字节数。
「70 KB」这种数字写死在文案里，发一次版就变成假的。

## 派生字段

| 字段 | 怎么算 | 为什么这么算 |
|---|---|---|
| `id` | 仓库名小写 | URL 用；大小写不敏感，避免 `/IceScan.html` 与 `/icescan.html` |
| `installable` | `bool(dl_release)` | **不看手写的 `platform`**：那个字段漏一处，这个应用在商店上就永远缺下载按钮 —— 这正是「新项目只能后加」的物理原因。现在由「Release 里到底有没有一个可下载的包」这个证据决定 |
| `url` | `<id>.html` | 同上 |
| `group_label` | 分组的显示名 | 从 `GROUPS` 里查；查不到就用 slug |
| `releases_url` | `github.com/<author>/<repo>/releases` | 不写死 |

## 体检（`insight.health`）

详情页的「体检」区块，四条判定，每条都能指回 GitHub 上的一次点击：

| 结论 | 判据 | 阈值/口径 |
|---|---|---|
| 已归档 | `archived == true` | — |
| 还没有发布过版本 | 没有 Release | — |
| 最新版本发布于 N 天前 | `pushed_at - published_at > 60` | 60 天。这个账号本来就是攒一批再发，低于 60 天报「停滞」会把正常节奏说成问题 |
| Android 仓库但没有可下载的包 | `kind == android && !asset_name` | 不伪造下载按钮 |
| N 次下载 | `download_count` | 只统计 Release 直链，**是个下界** |
| 仓库带许可证 | `license != null` | — |

`since_release_days` 与 `age_days` 用序数日相减（`util.days_between`），
**不 `import datetime`**：`datetime.now()` 一旦被误用，那条「同一 commit 同一产物」的承诺当场作废。

## 统计（`insight.stats`）

`stats.json` 与 `stats.html` 同源，页面就是它的排版。三条口径必须记住：

- `downloads` 是下界（不含镜像转发、不含别人重打包）
- `by_language` 是 primary language（按字节数判定），不是代码行数
- `releases_with_notes` 只数正文非空的，**空正文不会被补写**

## 集合（`insight.collection_catalog`）

十个集合，全部按当前快照算出来，规则写在页面上（`入选规则` 那行）：

| 集合 | 规则 |
|---|---|
| 装得上的 | `installable == true` |
| 还没发版的 | `latest == null` |
| 预发布中的 | `prerelease == true` |
| 只有源码的 | `installable == false && latest != null` |
| 标签：X | `tag == X`，且该标签下至少 2 个项目 |

手写清单一定会过期——某个项目改名/归档/停止发版之后还挂在「精选」里，
读者点进去发现是去年的事。这里的每一组都由当前字段决定，明天数据变了集合就变。

> 顺带一个实现细节：集合 id 用 `sha1(标签)[:8]` 而不是 Python 的 `hash()`。
> 后者带进程级随机种子，同一个标签在不同进程里得到不同的 id ——
> 那会让锚点链接在两次构建之间失效，而且构建就不再可复现了。

## 一个特例：`npu-chat`

它是自动收录的仓库，但补了一段手写文案——因为「GPU 一行代码都没有、
NPU 只到探测层、没在真机跑过一秒」这三件事必须由人写出来，
机器不会从仓库描述里读出这些。

这也说明自动收录不等于「放弃描述」：**能自动的自动，该人写的还是人写。**
缺省值是「取仓库描述」，不是「不写」。
