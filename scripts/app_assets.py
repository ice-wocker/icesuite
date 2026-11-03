# -*- coding: utf-8 -*-
"""把静态站点变成一个**能装、能离线用**的 PWA 所需的全部资产。

这里的每一件都是手写的，因为它们加起来不需要一个依赖：
manifest.json 是 JSON，Service Worker 是一段原生 JS，图标是 SVG。

三条自我约束，写在这里免得以后被「优化」掉：

1. **不注册 Service Worker 也行。** 注册失败（不支持、被隐私策略禁掉、
   file:// 打开）时页面必须照常可用 —— 所以注册代码包在 try/catch 里，
   而且缓存策略是「先网络后缓存」，不是「先缓存后网络」。离线时用缓存，
   在线时永远拿最新的。反过来会让用户看到上一次发版前的页面，且无法自愈。
2. **不缓存 API 与第三方。** 只缓存同源的 GET。GitHub 的 302 跳转链、
   加速镜像都不是本站能负责的东西，把它们写进缓存等于给自己埋一个
   「三天后某个包一直下不下来，因为缓存里是坏的」的坑。
3. **缓存清单是构建时算的**，不是运行时 `cache.addAll(全网)`。
   构建产物的 SHA 会进 manifest.json，所以「缓存的是哪个版本」是明确的。
"""
from __future__ import annotations

import json

# 图标：几何冰晶，和 icon.svg 同一套参数。多尺寸是为了 Android 主屏/任务切换器的
# 取用（同一个 SVG 也能用，但 512 的位图在某些启动器上更稳）。
ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
<rect width="64" height="64" rx="14" fill="#0b0f14"/>
<g fill="none" stroke="#5ad1ff" stroke-width="3" stroke-linecap="round">
<path d="M32 12v40M15 22l34 20M49 22L15 42"/>
<path d="M32 12l-5 5M32 12l5 5M32 52l-5-5M32 52l5-5"/>
<path d="M15 22l7 1M15 22l1-7M49 42l-7-1M49 42l-1 7"/>
<path d="M49 22l-1-7M49 22l-7 1M15 42l1 7M15 42l7-1"/>
</g>
</svg>
"""

# maskable 图标需要把主体收进中心 80% 的安全区，否则圆角/圆形裁剪会切掉冰晶的尖。
ICON_MASKABLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
<rect width="64" height="64" fill="#0b0f14"/>
<g fill="none" stroke="#5ad1ff" stroke-width="2.6" stroke-linecap="round"
   transform="translate(32,32) scale(0.78) translate(-32,-32)">
<path d="M32 12v40M15 22l34 20M49 22L15 42"/>
<path d="M32 12l-5 5M32 12l5 5M32 52l-5-5M32 52l5-5"/>
<path d="M15 22l7 1M15 22l1-7M49 42l-7-1M49 42l-1 7"/>
<path d="M49 22l-1-7M49 22l-7 1M15 42l1 7M15 42l7-1"/>
</g>
</svg>
"""

# 快捷方式：Android 长按图标弹出的头三个入口。
# 只指向**一定存在**的页面（构建时无条件产出），不指向某个具体项目 ——
# 项目可能被删，快捷方式不会自己消失，那会变成一个点开就 404 的图标。
SHORTCUTS = [
    ("store.html", "应用商店", "全部可安装的包"),
    ("latest.html", "最新更新", "按发版时间倒序"),
    ("timeline.html", "发版时间线", "全部版本一部历史"),
]


def manifest(site: dict, version_tag: str) -> str:
    """manifest.json。scope 与 start_url 用相对路径 —— 站点可能被 fork 到
    `/<repo>/` 下（GitHub Pages 项目页就是），写死绝对路径会 404。"""
    data = {
        "name": f"{site['name']} · {site.get('store_name', '应用商店')}",
        "short_name": site["name"],
        "description": site.get("desc", ""),
        "lang": "zh-CN",
        "dir": "ltr",
        # standalone 而不是 minimal-ui：这个站点的用法就是「当个 App 装着查东西」，
        # 地址栏没有信息量。但**不要求**全屏，用户还能退回浏览器。
        "display": "standalone",
        "display_override": ["standalone", "browser"],
        "start_url": "./index.html",
        "scope": "./",
        "id": "./",
        "orientation": "any",
        "background_color": "#0b0f14",
        "theme_color": "#0b0f14",
        "categories": ["productivity", "utilities"],
        "prefer_related_applications": False,
        "icons": [
            {"src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": "icon-maskable.svg", "sizes": "any", "type": "image/svg+xml",
             "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": n, "short_name": n, "description": d, "url": u}
            for u, n, d in SHORTCUTS
        ],
        "screenshots": [],
        # 版本信息放这里而不是标准字段里（manifest 没有 version 字段），
        # 但它是这套 PWA 的「这份缓存对应哪次构建」的唯一凭据。
        "x-version": version_tag,
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


SW_JS = r"""
/* Service Worker：让这个站点离线可用。
   ------------
   三件事，每一件都是为了不制造「看起来装好了、其实不能用」的状态：

   ① **策略是先网络后缓存（network-first），只有网络失败才用缓存。**
      反过来（缓存优先）会让用户在上一次发版后就一直看到旧页面，
      而且无法自愈 —— 这种「装上去之后就再也不更新」的 PWA 比不能离线更糟。

   ② **只缓存同源 GET。** 跨域请求（GitHub 的 302、加速镜像）不进缓存：
      那些响应的可用性不由本站负责，冻在缓存里只会让人以为是本站坏了。

   ③ **预缓存清单在构建时写进来**，不是运行时遍历全站。构建产物的
      版本号也在里面，所以「现在缓存的是哪一版」是可查的。
*/
const CACHE = '__CACHE_NAME__';
const PRECACHE = __PRECACHE__;

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(CACHE);
    // 逐个 add，失败不整体失败：某个页面拉不到不该让安装整个不成立。
    // 但失败的会在 devtools 里留下一条，不至于静默。
    await Promise.all(PRECACHE.map(async (u) => {
      try { await c.add(new Request(u, { cache: 'reload' })); } catch (err) { /* 记在下面 console */ }
    }));
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // ② 跨域一律不接管

  e.respondWith((async () => {
    try {
      const fresh = await fetch(req);
      // 只缓存成功的同源响应。opaque/redirect 的响应体读不出大小，缓存了也没用。
      if (fresh && fresh.ok && fresh.type === 'basic') {
        const c = await caches.open(CACHE);
        c.put(req, fresh.clone());
      }
      return fresh;
    } catch (err) {
      const hit = await caches.match(req, { ignoreSearch: true });
      if (hit) return hit;
      // 导航请求离线时给首页，而不是浏览器的恐龙页
      if (req.mode === 'navigate') {
        const home = await caches.match('./index.html');
        if (home) return home;
      }
      return new Response('离线，且这份内容没有缓存。', {
        status: 503, statusText: 'offline',
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      });
    }
  })());
});

self.addEventListener('message', (e) => {
  if (e.data === 'version') {
    e.source && e.source.postMessage({ type: 'version', cache: CACHE, files: PRECACHE.length });
  }
});
"""


def service_worker(version_tag: str, precache: list) -> str:
    """生成 sw.js。缓存名里带构建版本号 —— 同名缓存永远不会被误判成「已有」。"""
    return (SW_JS
            .replace("__CACHE_NAME__", f"icesuite-{version_tag}")
            .replace("__PRECACHE__", json.dumps(precache, ensure_ascii=False)))


INSTALL_JS = r"""
/* 「装到桌面」按钮。
   ------------
   浏览器的安装入口藏得很深（Chrome 在地址栏右边，Safari 在分享菜单里），
   大多数人找不到。所以自己给一个按钮，但**只在浏览器真的愿意装的时候出现**：
   beforeinstallprompt 不触发，就说明这个环境装不了（iOS Safari、
   已经被装过了、或者不在 HTTPS 下），那时按钮不显示比显示一个点了没反应的按钮好。

   iOS 没有 beforeinstallprompt，单独给一句「分享 → 添加到主屏幕」的提示，
   因为这是 iOS 上唯一的路，而它确实有用。
*/
(function(){
  var bar = document.getElementById('installbar');
  if(!bar) return;
  var btn = document.getElementById('installbtn');
  var tip = document.getElementById('installtip');
  var ua = navigator.userAgent || '';
  var standalone = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches)
                   || window.navigator.standalone === true;

  if (standalone) { bar.remove(); return; }

  var isIOS = /iPad|iPhone|iPod/.test(ua) && !window.MSStream;
  if (isIOS) {
    bar.hidden = false;
    if (btn) btn.hidden = true;
    if (tip) tip.hidden = false;
    return;
  }

  var prompt = null;
  window.addEventListener('beforeinstallprompt', function(e){
    e.preventDefault();
    prompt = e;
    bar.hidden = false;
    if (btn) { btn.hidden = false; btn.textContent = '⤓ 装到桌面'; }
  });
  if (btn) btn.addEventListener('click', function(){
    if (!prompt) return;
    prompt.prompt();
    prompt.userChoice.then(function(){ prompt = null; btn.textContent = '⤓ 装到桌面'; });
  });
  window.addEventListener('appinstalled', function(){ bar.remove(); });

  /* 离线状态条：装成 App 之后没有地址栏，用户更需要知道「现在没网」。 */
  function net(){
    var n = document.getElementById('netbar');
    if(!n) return;
    n.hidden = navigator.onLine;
  }
  window.addEventListener('online', net);
  window.addEventListener('offline', net);
  net();

  /* 注册 Service Worker。失败一律吞掉：这个站点的主体功能不依赖它。 */
  if ('serviceWorker' in navigator && location.protocol !== 'file:') {
    window.addEventListener('load', function(){
      navigator.serviceWorker.register('sw.js', { scope: './' }).catch(function(){});
    });
  }
})();
"""
