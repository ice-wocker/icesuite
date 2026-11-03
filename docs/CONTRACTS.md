# 机器可读产物：四个对外契约

站点不只是给人看的。它同时输出四个 JSON，任何人都可以只下载其中几十 KB
就拿到「这个账号里有哪些项目、现在是什么版本、包能不能信、这份数据是哪次构建的」。

它们各自的存在理由不同，字段的语义也不同。**把它们的边界写清楚，是为了避免
以后有人拿 `update.json` 去做统计、或者拿 `stats.json` 去做更新检查** ——
那种混用不会立刻出错，只会在某次发版后悄悄不对。

| 文件 | 一句话 | 会不会受构建时间影响 |
|---|---|---|
| `update.json` | 应用查更新用 | 否（`generated_at` 取快照时间） |
| `stats.json` | 站点统计的出处 | 否（同上） |
| `graph.json` | 项目之间怎么连 | 否 |
| `content.json` | 产物完整性清单 | **刻意没有时间字段** |

---

## 1. `update.json`

给**应用自己**的检查更新逻辑用。一个 3 KB 的 JSON 就能回答
「我是不是最新版、新版多大、从哪下、下完对不对得上」。

```jsonc
{
  "_note": "由 scripts/build_site.py 从 data/registry.json 生成；sha256 来自 GitHub Release 资产元数据，取不到就是 null（不推算）。",
  "generated_at": "2026-11-03T11:38:40Z",   // 快照时间，不是构建时间
  "count": 12,
  "apps": {
    "ModelScopeBrowser": {
      "name": "魔搭模型库",
      "version": "v2.7.1",
      "prerelease": false,
      "published_at": "2026-11-02",
      "size": 8423941,                       // 字节，不是「约 8 MB」
      "file": "ModelScope-Models-2.7.1.apk",
      "sha256": "1692baa7…118",              // 取不到就是 null
      "url": "https://github.com/…/download/v2.7.1/…",
      "page": "https://ice-wocker.github.io/icesuite/modelscopebrowser.html",
      "min_android": "7.0",
      "abi": "arm64-v8a + armeabi-v7a"
    }
  }
}
```

三条使用约定：

1. **`version` 是 Git tag 的原文**，没有规整过（有的是 `v2.7.1`，有的是 `v13`）。
   想比较大小自己解析；本站不给「语义化版本」的保证，因为作者不保证。
2. **`sha256` 为 `null` 的意思是「拿不到」，不是「没算」**。GitHub 有的资产没有
   `digest` 元数据，本站不推算、不猜。
3. **`prerelease: true` 的包能用但不是正式版**。`npu-chat` 就是这种情况：
   它唯一的包只在 prerelease 里，跳过它等于这个项目在商店上一格都没有。

---

## 2. `stats.json`

`stats.html` 上的每个数字都来自这里，两边不是各算一遍——**页面就是它的排版**。

```jsonc
{
  "generated_at": "2026-11-03T11:38:40Z",
  "totals": {
    "projects": 22, "installable": 12, "release_bytes": 174551915,
    "releases": 40, "releases_with_notes": 40, "tags": 88, "languages": 5,
    "handwritten": 13, "auto": 9, "downloads": 767, "sha_covered": 12
  },
  "by_month": {"2026-09": 16, "2026-10": 19, "2026-11": 5},
  "by_year":  {"2026": 40},
  "by_language": {"Java": 11, "Python": 7, …},
  "by_tags": {…},
  "sizes":     [{"repo": "MusicFusionAI", "size": 41387, …}, …],   // 升序
  "downloads": [{"repo": "iceScribe", "downloads": 125, …}, …],     // 降序
  "newest_release": "2026-11-02",
  "oldest_repo": "2026-09-01"
}
```

需要特别说明的口径，因为它们**都只会偏小、不会偏大**：

- `downloads` 是 GitHub Release 资产的计数器。**不含**镜像站转发的下载量，
  也不含别人 clone 之后自己重新打包发出去的量。所以它是个下界。
- `by_language` 是仓库的 **primary language**（GitHub 按字节数判定），
  不是代码行数——后者要 clone 才能算，而本站构建时不许联网。
- `releases_with_notes` 只统计 Release 正文非空的。**空正文不会被补写**：
  把「没写」装成「有内容」比留空更糟。

---

## 3. `graph.json`

```jsonc
{
  "_note": "…节点=项目，边=同分组或同标签；weight 只由共享标签数决定，不含任何行为数据。",
  "nodes": [{"id": "icescribe", "name": "iceScribe · 冰记", "group": "on-device-ai",
             "kind": "android", "installable": true, "version": "v0.1.1",
             "size": 61130620, "tags": ["离线", …], "url": "icescribe.html"}],
  "edges": [{"a": "icescribe", "b": "npu-chat", "kind": "tag",
             "tags": ["离线"], "weight": 1}]
}
```

一条自我约束写在这里，免得以后被"优化"掉：**边只有两种，同分组与同标签。**
没有「用户也看了」这类共现边，因为这个站点没有埋点、没有 Cookie、没有统计，
也就不该有一张假装懂行为的图。想要更丰富的图，得先破掉站点的立身之本，
那是另一个取舍，不该悄悄发生。

`kind: "tag"` 的边保证 `tags` 非空、`kind: "group"` 的边保证同分组。
自检里有断言：出现任何悬空节点或空标签边就红。

---

## 4. `content.json`

这是一份**产物自索引**，也是「同一 commit 同一产物」这句话唯一的证据。

```jsonc
{
  "_note": "…build.id 是全部文件内容的结构哈希 —— 同一份输入必然得到同一个 id，与构建时间无关。",
  "base_url": "https://ice-wocker.github.io/icesuite",
  "build": {"id": "ebc02c48…", "files": 45, "bytes": 665197, "pages": 31},
  "files": {
    "index.html": {"bytes": 33045, "sha256": "…"},
    …
  }
}
```

三个设计决定：

- **没有 `generated_at`。** 这一份是完整性凭据。带上时间就不再可复现，
  那条承诺当场作废。要「数据什么时候新鲜」，看 `stats.json` / `update.json` 的 `generated_at`。
- **`build.id` 只由文件内容决定。** 内容一样，id 就一样，跟在哪台机器、什么时候构建无关。
  反过来，id 变了就一定是内容变了。
- **必须最后写。** `content.json` 要索引包括 `CNAME`、`sitemap.xml`、`sw.js` 在内的全部产物，
  所以它在构建流程的**最后**一步生成。早写一步就会漏文件——这个错本版犯过一次，
  是自检里那条「产物里有文件没进 content.json」抓出来的。

### 怎么用它核对自己下载的站点

```bash
# 拿一份产物，逐个文件比对
python3 - <<'PY'
import json, hashlib, pathlib
d = json.load(open("site/content.json"))
bad = []
for name, meta in d["files"].items():
    raw = pathlib.Path("site", name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta["sha256"] or len(raw) != meta["bytes"]:
        bad.append(name)
print("不一致：", bad or "无")
PY
```

---

## 版本与向后兼容

`update.json` 的字段只增不减；`verify` 是本版新增的顶层字段（见下）。
真要破坏性改动时，会在这里写明并保留一个过渡期——本站的其他承诺
（体积可验证、零依赖）都要求「别人写的检查不会因为我改版就悄悄失效」。

```jsonc
"verify": {
  "sha256_covered": 12,            // 有校验值的应用数
  "size_covered": 12,              // 有字节数的应用数
  "note": "…取不到写 null，不推算"
}
```
