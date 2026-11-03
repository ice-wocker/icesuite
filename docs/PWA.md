# 离线与可安装：这个站点是一个 App

站点现在能「装到桌面」，装完之后不联网也能翻。这不是加个 manifest 就有的效果，
它由三样东西共同成立，任何一样写错都会退化成「看起来装上了、其实不能用」。

## 三件套

| 文件 | 干什么 | 写错会怎样 |
|---|---|---|
| `manifest.json` | 告诉浏览器这个「App」叫什么、从哪开始、什么图标 | `start_url` 写成绝对路径，fork 到子路径就 404 |
| `sw.js` | 拦截同源 GET，先网络后缓存 | 策略反了，用户装完就再也看不到新版 |
| `icon-maskable.svg` | 被圆形/圆角裁剪时不出界 | 用普通图标当 maskable，尖角会被切掉 |

`app_assets.py` 里三条自我约束，写在这里免得以后被"优化"掉：

### 1. 注册失败必须不影响使用

```js
navigator.serviceWorker.register('sw.js', { scope: './' }).catch(function(){});
```

`.catch` 不是偷懒。`file://` 打开、隐私模式、某些 WebView 都会拒绝注册，
而这个站点的主体功能（看项目、查版本、复制 sha256）一样都不需要 Service Worker。
把注册失败变成错误提示，等于用一个附加能力去惩罚主要用途。

### 2. 策略是「先网络后缓存」，不是反过来

```js
try {
  const fresh = await fetch(req);        // 在线：永远拿最新的
  ...
  return fresh;
} catch (err) {
  const hit = await caches.match(req);   // 离线：退回缓存
  if (hit) return hit;
  ...
}
```

缓存优先会让用户在上一次发版之后一直看到旧页面，而且**无法自愈**——
这是最糟的一种 PWA 故障：它看起来正常工作，只是内容永远停在某一刻。
「装上去之后就再也不更新」比不能离线严重得多。

### 3. 只缓存同源 GET

```js
if (url.origin !== self.location.origin) return;   // 跨域一律不接管
```

跨域的是 GitHub 的 302 跳转链、加速镜像。它们的可用性不由本站负责，
冻进缓存只会制造「三天后某个包一直下不下来，因为缓存里是坏的」这种查不出来的问题。

## 缓存清单是构建时算的

```js
const CACHE = 'icesuite-9a222fd213f3';
const PRECACHE = ["./index.html", "./store.html", …, "./update.json", "./404.html"];
```

缓存名里带着**构建指纹的前 12 位**（来自 `content.json` 的 `build.id`）。
它由产物内容决定，所以：

- 内容变了 → 缓存名变了 → 旧缓存被 `activate` 清掉，用户拿到新版
- 内容没变 → 缓存名不变 → 不会无谓地重新下载

`PRECACHE` 里的每一项在构建时就确定，不是运行时遍历全站。
自检里有一条断言：`PRECACHE` 里任何一项在产物里不存在就红
（预缓存一个不存在的文件，装上去就是缺页，而且没有任何报错）。

## 装到桌面按钮：只在真的能装的时候出现

```js
window.addEventListener('beforeinstallprompt', function(e){ … });
```

`beforeinstallprompt` 不触发，就说明这个环境装不了（iOS Safari、已经装过、
不在 HTTPS 下）。那时**按钮不显示**，比显示一个点了没反应的按钮好。

iOS 是个例外：它没有这个事件，唯一的路是「分享 → 添加到主屏幕」。
所以 iOS 上单独给一行文字提示，按钮藏起来——因为那条路确实走得通。

## 离线时到底能用什么

| 能力 | 离线 | 说明 |
|---|---|---|
| 翻首页 / 商店 / 时间线 / 对比 / 集合 / 数据 | ✅ | 全部在 PRECACHE 里 |
| 看版本号、体积、sha256 | ✅ | 来自缓存的 HTML 与 `update.json` |
| 下载 APK | ❌ | 跨域资源，不进缓存。这是有意的 |
| 站内搜索 | ✅ | `search.json` 在 PRECACHE 里，纯前端过滤 |
| 检查更新 | ❌ | 需要网络（`update.json` 读的是缓存那份，会标出快照时间） |

离线时页面顶部会出现一条提示条（`navigator.onLine` 驱动）。
装成 App 之后没有地址栏，用户更需要知道「现在没网」——
否则他会以为是 App 卡了。

## 为什么不做「离线也能下 APK」

因为做不到，也不想假装做到。

一个 61 MB 的包要塞进 Cache Storage，需要用户主动触发一次下载并等它完成；
而 Release 资产是跨域的，浏览器不允许 SW 读它的响应体（CORS 缺失）。
写一段「已缓存」的代码只会在真正断网时暴露成另一个错误。
本站的选择是：**离线时把「不能下」明确说出来**，而不是制造一个假的确定感。
