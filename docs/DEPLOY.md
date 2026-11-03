# 部署

## 一句话流程

**日常发版不需要动这个仓库。** 新仓库、新 Release 由 `sync.yml` 每小时同步，
提交 `data/registry.json` 后自动触发发布。

人只在这两种情况下改代码：动文案（`data/projects.py`）、动渲染（`scripts/`）。

## 0 同步一次快照

```bash
GH_TOKEN=<你的 token> python3 scripts/sync.py   # 写 data/registry.json
python3 scripts/sync.py --check                # 只比对快照与线上是否一致
```

不带 token 也能跑，但会撞 GitHub 的匿名限额（60 次/小时）。CI 里传
`secrets.SYNC_PAT || secrets.GITHUB_TOKEN`。

## 1 本地构建

```bash
python3 scripts/build_site.py            # 产物在 site/
open site/index.html                     # 双击就能看，不用起服务
python3 scripts/check_site.py            # 上线前自检（含外链）
```

`site/` 不入库（`.gitignore` 里拉黑了）。真相源只有 `data/` 与 `scripts/`，
所以仓库克隆体积一直是几十 KB。

> 用 `file://` 直接打开时搜索框会提示「索引没加载到」——那是 `fetch` 不能读本地文件，
> 不是 bug。想验搜索，`python3 -m http.server 8000 -d site` 起来再看。

## 2 发布路径

```text
schedule（每小时 17 分）
  → sync.yml：sync.py → 有变化就提交 registry.json → 触发 deploy
push to main（data/ 或 scripts/ 变化）
  → deploy.yml：构建 → 断言产物 → check_site.py → upload-pages-artifact → deploy-pages
  → https://ice-wocker.github.io/icesuite/
repository_dispatch(release)
  → sync.yml：其它仓库发版时秒级同步
```

### 两个坑

1. **默认 token 推的提交不会触发 `deploy.yml`。** GitHub 防递归会掐掉这个链，
   表现是「同步成功、站点没更新」，而且日志全是绿的。所以 `sync.yml` 优先用
   `secrets.SYNC_PAT`；没配时显式 `gh workflow run deploy.yml` 兜底。
2. **想让发版秒级同步**，得去**每个应用仓库**配 webhook：
   `https://api.github.com/repos/ice-wocker/icesuite/dispatches`，
   Content type `application/json`，Body `{"event_type":"release"}`。
   不配也能用，最多晚一小时。

`deploy.yml` 的触发路径限定在 `data/**`、`scripts/**` 与它自己。改 README 不会触发发布，
改清单必触发。发布前会再跑一次 `check_site.py`（含外链）——**宁可不上线，也不让坏产物出去**。

concurrency group 是 `pages`：同一时刻只跑一个发布，避免两个 commit 抢 Pages 锁。

## 3 Pages 配置（一次性）

仓库 Settings → Pages：

- Source 选 **GitHub Actions**（不是分支）
- 不需要填自定义域名——`build_site.py` 每次都产出一份 `CNAME`，`configure-pages` 会读它

`.nojekyll` 也会产出。没有它，Jekyll 会吞掉下划线开头的文件与目录。

## 4 域名

当前 `base_url` 是 `https://ice-wocker.github.io/icesuite`（`data/projects.py` 里唯一一处）。

自定义域名 `icesuite.eu.org` 的 DNS 还没配好（eu.org 侧没 zone，公共 DNS 上是 NODATA），
所以暂时用 `github.io`。等 DNS 通了，改 `base_url` 一处即可：

```python
SITE = {
    "domain": "icesuite.eu.org",
    "base_url": "https://icesuite.eu.org",    # ← 只改这一行
    ...
}
```

`CNAME` 文件会跟着变，`deploy.yml` 里的断言（域名在 `data/` 里只出现一次）也仍然成立。
完整 DNS 步骤见 [DNS.md](DNS.md)。

> 为什么不把域名的两处（`domain` 与 `base_url`）合并成一个？
> 因为它们回答的是两个不同问题：`domain` 是「CNAME 文件里写什么」，
> `base_url` 是「页面里的绝对链接指向哪」。DNS 没通时这两个值必然不同——
> 合并只会逼你在两个错答案里选一个。CI 只断言 `domain` 在 `data/` 里出现一次。

## 5 回滚

站点没有「版本」，只有 commit。回滚两步：

```bash
git revert <bad-commit> && git push      # 改回内容
# 或
git checkout <good-commit> -- data/ scripts/ && git commit -m "rollback" && git push
```

Pages 会在部署成功后立刻切过去。**不要在 Pages 后台手动操作**——下次部署会覆盖。

## 6 发新版应用之后

站点不感知各仓库的发版，它读的是入库快照。所以：

```bash
GH_TOKEN=... python3 scripts/sync.py          # 重新同步快照
git add data/releases.json && git commit -m "chore: 刷新 Release 快照"
```

忘了会怎样？`ci.yml` 的 `releases` job 会联网比对，**CI 直接红**。
这条就是在 `v2.5.0` 上线后补的：那次商店页挂了两天旧版本，没人发现。

## 7 常见故障

| 症状 | 原因 | 处理 |
|---|---|---|
| 页面 404 | `deploy.yml` 没跑（改了 README 不触发） | 手动 `workflow_dispatch` |
| 样式丢失、页面变纯文本 | CSS 大括号不配平 | `check_site.py` 会报；修完重发 |
| 首页卡片缺标题/多出方块 | 卡片被写成整块 `<a>` 且内部有链接 | 见 [CHECKS.md](CHECKS.md) 第五条 |
| 自定义域名被重置成 github.io | `CNAME` 产物丢了 | 构建产物里必须有 `CNAME` |
| 商店页版本号是旧的 | `registry.json` 快照过期 | 跑一次 `sync.py`（正常情况下每小时自动跑）|
