# ice 工坊 · 站点源码

`https://icesuite.eu.org` 的生成器与内容源。零依赖，只用 Python 标准库。

## 结构

```
data/projects.py        唯一内容源：站点文案、项目清单、指标、亮点、已知限制
scripts/build_site.py   渲染器：把清单投影成 site/ 下的静态 HTML
scripts/check_site.py   自检：产物完整性、站内死链、下载链接可达性
site/                   构建产物（不入库）
```

## 本地使用

```bash
python3 scripts/build_site.py     # 生成 site/
python3 scripts/check_site.py     # 自检（含外链 HEAD）
open site/index.html              # 双击就能看，不需要起服务
```

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
