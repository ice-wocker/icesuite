# 开发指南

> 🌐 语言 / Language: 中文 · [English](DEVELOPING.en.md)

从零把这仓库跑起来、改一处代码、加一个页面、加一个机器可读产物。
假设你会 Python，但不了解这个项目。

> **这个仓库里同时有两个项目**：
> 根目录的 `scripts/` + `data/` 是**站点**（本文件讲的）；
> `app/` 是 Android 应用 **ModelScopeBrowser** 的源码（它的工具链是 JDK 17 + SDK 36 + NDK 27，
> 见文末「如果我只是想改云应用」一节）。两者互不依赖：站点构建不需要 JDK，
> 应用构建不需要 Python。

## 0. 站点：三分钟跑起来

```bash
python3 scripts/build_site.py      # 渲染 site/，零依赖，不需要 pip install 任何东西
open site/index.html               # 双击就能看，不用起服务
```

就这样。没有 `npm install`、没有虚拟环境、没有构建缓存。
唯一的可选依赖是 `node`（内联 JS 语法检查用；没有它会明确说跳过）。

| 命令 | 用途 | 需要网络 |
|---|---|---|
| `python3 scripts/sync.py` | 刷新 `data/registry.json` | 是（`GH_TOKEN`） |
| `python3 scripts/build_site.py` | 渲染 `site/` | 否 |
| `python3 scripts/check_site.py` | 自检（结构 + 一致性 + 38 条外链） | 外链部分需要 |
| `python3 scripts/check_site.py --skip-links` | PR 上用的快检查 | 否 |
| `python3 scripts/check_site.py --reproducible` | 再构建一次逐字节比对 | 否 |
| `python3 scripts/js_syntax.py` | 内联 JS 语法检查 | 否 |
| `python3 scripts/mutate_test.py` | 老守卫自证（15 条） | 否 |
| `python3 scripts/mutate_v2.py` | 新守卫自证（29 条） | 否 |
| `python3 scripts/live_check.py` | 核对线上那份 | 是 |

### 0.1 加一个页面

1. 在 `scripts/pages.py` 里写一个函数，返回 `(title, body_html, meta_dict)`。
   **不要在这里写 `<head>`、导航、页脚**——外壳只有 `build_site.page()` 一份。
2. 在 `build_site.build()` 里调 `_emit("xxx.html", pages.xxx_page(...), desc=..., active="xxx.html")`。
   `_emit` 会自动补 `canonical` 和导航高亮。
3. 如果要进导航，改 `nav_items()`；窄屏导航只显示品牌与主题按钮，靠首页入口与页脚进。
4. 在 `check_site.py` 里加一条「页面生成了但内容是空的」的断言，并在 `mutate_v2.py` 里
   加一条「把它删掉 → 必须红」的用例。**没有后者，前者就是没人验过的守卫。**
5. `sitemap.xml` 会自动收录（它遍历 `projects` + 固定列表，固定列表在 `write_sitemap` 里补）。

### 0.2 加一个机器可读产物

1. 想清楚它是给谁用的、`generated_at` 该取什么。
   **只要这个文件进了 `site/`，它就必须可复现**——不许出现 `time.time()` 或随机数。
   「数据什么时候新鲜」用 `util.source_stamp()`（快照时间）。
2. 生成顺序：如果它要索引其它产物（像 `content.json`），必须最后写。
3. 在 `check_site.py` 里断言「它和模型一致」，而不是「它存在」。后者是橡皮图章。

### 0.3 改文案

只改 `data/projects.py`，别抄版本号。

合并规则在 `scripts/overlay.py`，`MACHINE_FIELDS` 列出的字段手写层一律不生效。
想覆盖机器字段 = 想重新制造「页面写着 v2.6.0、线上已经 v2.7.1」那起事故。

### 0.4 加一个下载源

改 `data/mirrors.py`。这个文件是手写的，因为镜像站是别人家的服务，
**没有任何自动机制能保证它活着**。加之前先用三个包实测：

```bash
for f in <三个不同大小的包>; do
  time curl -sSL -o /dev/null "https://<镜像前缀>https://github.com/..."
done
```

实测口径写进 `note` 字段。做不到就别加——一个连不上的源排进候选，
用户看到的就是「链接经常失效」。

## 1. 应用侧环境（只有改 `app/` 才需要）

| 组件 | 版本 | 说明 |
|---|---|---|
| JDK | 17 | AGP 8.13 要求；JDK 21 也能编，但 CI 用 17 |
| Android SDK Platform | 36 | `compileSdk` / `targetSdk` |
| Build Tools | 36.0.0 | |
| NDK | 27.2.12479018 | `app/build.gradle` 里锁定 |
| CMake | 3.22.1 | llama.cpp 构建脚本要求 ≥ 3.14 |
| Gradle | 8.14.5 | 由 wrapper 提供，不要改成本地版本 |

### 1.1 安装

Android Studio 从 Ladybug 起自带 SDK Manager。命令行的话：

```bash
export ANDROID_HOME=$HOME/Android/Sdk
export PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$PATH

sdkmanager "platforms;android-36" "build-tools;36.0.0" \
           "ndk;27.2.12479018" "cmake;3.22.1" \
           "platform-tools"
```

### 1.2 本地配置

```bash
cd ModelScopeBrowser
echo "sdk.dir=$ANDROID_HOME" > local.properties
```

`local.properties` 已被 `.gitignore` 排除，不要提交。

## 2. 第一次构建

```bash
./gradlew assembleDebug
```

首次会经历：

1. 下载 Gradle 发行版（约 130 MB，看网速）；
2. 拉取 llama.cpp（`FetchContent`，约 50 MB）；
3. 编 arm64-v8a 的 7 份 CPU 后端 + armeabi-v7a 的静态库。

全程 20~40 分钟，取决于机器。之后增量构建只要几十秒，除非改了 `cpp/` 下的东西。

### 2.1 加速：用本地 llama.cpp

```bash
git clone --depth 1 --branch b11205 https://github.com/ggerganov/llama.cpp ~/llama.cpp
./gradlew assembleDebug -PllamaCppDir=$HOME/llama.cpp
```

`CMakeLists.txt` 里判断了 `LLAMA_CPP_DIR` 有 `CMakeLists.txt` 就直接 `add_subdirectory`，跳过下载。

### 2.2 只编一个 ABI（更快）

临时改 `app/build.gradle` 的 `abiFilters`：

```gradle
ndk { abiFilters "arm64-v8a" }   // 去掉 armeabi-v7a，省约 1/3 时间
```

注意别提交这个改动——32 位真机还需要它。

## 3. 项目结构速览

```text
app/src/main/java/com/mscope/browser/
├── MainActivity.java          列表页
├── DetailActivity.java        详情页
├── WebActivity.java           网页兜底
├── ModelApi.java              接口 + 降级
├── ModelItem / ModelFile / Format / Ui
├── core/            ★ 纯逻辑，无 Android 依赖，有单测
├── agent/           智能体：协议、工具、shell、工作区、检索、预览
├── llama/           引擎、桥接声明、对话页、历史
└── local/           下载中心、前台服务、索引、模型库
```

改动前先看 [模块深入](MODULES.md)，那里每个类都写了「要解决什么 / 怎么做的 / 容易写错」。

## 4. 改一处代码

拿一个真实需求举例：**让上下文上限从 32768 提到 65536**。

### 4.1 找到所有相关处

```bash
grep -rn "32768" app/src/main/java app/src/main/res
```

会找到：

| 位置 | 作用 |
|---|---|
| `Validators.CTX_MAX` | 参数收敛上限 |
| `MemoryBudget.STEPS` | 候档位列表 |
| `ChatActivity` 的输入校验 | 已改为走 Validators |
| `strings.xml` 的 `p_ctx_tip` | 提示文案 |

### 4.2 改

```java
public static final int CTX_MAX = 65536;

private static final int[] STEPS = {512, ..., 32768, 49152, 65536};
```

### 4.3 补测试

```java
@Test
public void normalize_acceptsLargeCtx() {
    Validators.Sampling s = new Validators.Sampling(8192, 0.7f, 0.9f, 40, 40000);
    Validators.normalize(s);
    assertEquals(40000, s.nCtx);
}
```

### 4.4 验证

```bash
./gradlew testDebugUnitTest   # 逻辑对
./gradlew assembleDebug       # 能编
# 真机：参数弹窗里填 65536，看是否被压回、模型能不能加载
```

### 4.5 更新文档

`docs/BENCHMARKS.md` 的内存表要加一行 65536（并写清「不建议在手机上开」）。

## 5. 加一个新工具

假设要加 `time`：返回手机当前时间，让模型知道「今天几号」——这是它回答「最近新闻」时最缺的信息。

### 5.1 注册名字

```java
// AgentTools.names()
return new HashSet<>(Arrays.asList(
        "shell", "web_search", "fetch_url", "time",     // ← 新增
        "read_file", "write_file", "list_files", "delete_file", "open_preview"));
```

### 5.2 实现

```java
case "time": {
    java.text.SimpleDateFormat f =
            new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss EEEE", java.util.Locale.CHINA);
    return "现在时间：" + f.format(new java.util.Date());
}
```

只读操作，不加进 `risky()`。

### 5.3 加进提示词

```java
// AgentTools.describe()
sb.append("- time：获取当前日期与时间。参数 {} 或无参\n");
```

### 5.4 补测试

`ToolCall` 的解析不需要改（格式通用）。但要测「`time` 不会被当普通文本漏掉」：

```java
@Test
public void parsesTimeCall() {
    String s = "<function name=\"time\"><param name=\"\"></param></function>";
    assertEquals(1, ToolCall.parse(s, AgentTools.names()).size());
}
```

### 5.5 验证

真机对话：「现在几点？」—— 应该看到一张 `time` 工具卡片，然后模型基于真实时间回答。

## 6. 调试技巧

### 6.1 日志

```bash
adb logcat -s LlamaEngine LlamaBridge DownloadCenter AgentTools ToolCall ChatActivity
```

每个关键类都有 TAG，方便单独过滤。

### 6.2 看 native 报错

```java
LlamaBridge.nativeLastError()   // 界面加载失败时会直接显示
```

常见值：`backendCount=0`（.so 没释放）、`failed to load model`（文件损坏或架构不支持）。

### 6.3 不重装应用就换代码

Android Studio 的 Apply Changes 对纯 Java 改动有效；改了 C++ 就必须重装（要重新编 native）。

### 6.4 检查 .so 是否落盘

```bash
adb shell run-as com.mscope.browser ls -l lib/
adb shell ls -l /data/app/*/com.mscope.browser-*/lib/arm64/
```

应该看到 7 个 `libggml-cpu-android_*.so`。

### 6.5 模拟低内存设备

```bash
# 开发者选项 → 后台进程限制；或直接改 meminfo 不可行，用低端真机更靠谱
adb shell settings put global activity_manager_constants max_cached_processes=2
```

## 7. 出包与发布

### 7.1 本地出 release 包

```bash
# 生成 keystore（只做一次，之后好好保存）
keytool -genkeypair -v -keystore release.keystore -alias mscope \
        -keyalg RSA -keysize 2048 -validity 10000

# 写 keystore.properties
cat > keystore.properties <<EOF
storeFile=/absolute/path/to/release.keystore
storePassword=******
keyAlias=mscope
keyPassword=******
EOF

./gradlew assembleRelease
# 产物：app/build/outputs/apk/release/app-release.apk
```

### 7.2 走 CI 发布

```bash
# 1. 确认版本号
grep versionCode app/build.gradle

# 2. 打 tag（必须 v 开头，CI 只认这个）
git tag v2.6.0
git push origin v2.6.0
```

CI 会：单测 → Lint → 构建 debug+release → 校验签名与 ABI → 创建 Release 并附 APK。

**前提**：仓库 Secrets 里配好四个签名变量，否则 tag 构建会直接失败（这是刻意的）。

### 7.3 版本号规则

| 位 | 规则 |
|---|---|
| `versionCode` | 单调递增整数，每次发版 +1 |
| `versionName` | 语义化：修 bug 改补丁位，加功能改次版本位，加模块层改主版本位 |

## 8. 提 PR

1. Fork / 新建分支（不要直接推 main）；
2. 改代码 + 改测试 + 改文档（三件一起）；
3. 本地跑 `./gradlew testDebugUnitTest lintDebug assembleDebug`；
4. 提交信息写清「为什么」，不写「改了什么」——后者看 diff 就知道；
5. 开 PR，描述里附上验证方式（真机截图 / 日志）。

### 8.1 提交信息风格

```text
fix: 修复并发下载时任务表残留导致的「永远下载中」

start() 先投递、后登记，单线程池可能在上半段执行前就跑完 run()，
把任务从表里摘掉，随后任务又被塞回去。改为先 putIfAbsent 再投递。
```

前缀：`feat` / `fix` / `docs` / `chore` / `ci` / `perf`。

## 9. 常见编译问题

| 错误 | 原因 | 处理 |
|---|---|---|
| `NDK not configured` | 没装指定版本 NDK | `sdkmanager "ndk;27.2.12479018"` |
| `CMake 3.22.1 not found` | 同上 | `sdkmanager "cmake;3.22.1"` |
| `Failed to resolve: androidx...` | 网络 / 镜像问题 | 配 `settings.gradle` 的仓库或代理 |
| `Unsupported class file major version` | 用了 JDK 21+ 编 AGP 要求的字节码 | 换 JDK 17 |
| `Task :app:buildCMakeDebug FAILED` 且报 `vld1q_f16` | `GGML_LLAMAFILE` 没关 | 检查 `CMakeLists.txt` |
| 编译通过但运行时 `UnsatisfiedLinkError` | ABI 过滤掉了真机架构 | 检查 `abiFilters` 与真机 ABI |

## 10. 代码地图（按「想改什么」索引）

| 想改 | 去这里 |
|---|---|
| 列表的排序 / 筛选项 | `MainActivity` + `ModelApi.facetLabel` |
| 卡片样式 | `res/layout/item_model.xml` + `ModelAdapter` |
| 下载行为 | `DownloadCenter` + `DownloadService` |
| 对话气泡 | `res/layout/item_chat_*.xml` + `ChatActivity.Adapter` |
| 工具协议 | `ToolCall` |
| 工具实现 | `AgentTools` |
| 提示词 | `PromptTemplate` |
| 推理参数 | `LlamaEngine.Params` + `Validators` |
| native 行为 | `llama_bridge.cpp` |
| 上下文默认值 | `MemoryBudget` + `ChatActivity.DEFAULT_CTX` |
| 存储判定 | `StorageGuard` |
| 文件操作 | `FsKit` / `Workspace` |
| 颜色 / 主题 | `res/values/colors.xml` / `themes.xml` |
| CI | `.github/workflows/android.yml` |

---

看完这一页还是不知道从哪下手？去 [模块深入](MODULES.md) 找到对应的类读一遍，
每个类开头都写了它解决的问题。
