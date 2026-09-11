# ytdlp4k

YouTube 视频下载器（tkinter GUI），专注高质量下载：原画 / 4K / 1080P / 720P、智能帧率（30/24fps）、GPU 加速转码。

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 内核，提供图形界面、一键下载、播放、属性查看、帧率转换。

**免 Python、绿色分发**：内置环境自动检测与一键安装，拿到手双击即用，适合直接发给别人。

## 功能

- 🎬 **分辨率档位**：原画（取可读取的最高） / 4K / 1080P / 720P，所选档位高于视频实际最高时**自动降级**到可用最高
- 🗂️ **保存分类**：分类名可自定义（电影 / 音乐 / 1080P …），每个分类各绑一个文件夹，下载前按分类归档
- 📺 **播放按钮**：下载完成后直接用系统播放器打开
- 📋 **属性查看**：ffprobe 显示分辨率 / 时长 / 帧率 / 编码 / 码率，不用打开视频
- ⏱️ **智能帧率**：选 30/24fps 时**优先下载 YouTube 原版流**（零损失）；没有对应帧率原版时自动用 ffmpeg 转码兜底
- 🚀 **GPU 优先转码**：检测到 NVIDIA NVENC 用硬件编码（快 5-10 倍），无 GPU 自动回退 CPU
- 📜 **实时进度日志**：下载 / 转码进度实时滚动
- 🌍 **代理支持**：下载页直接填代理地址，即时保存（国内访问 YouTube 必填）
- 🧩 **环境自检页**：侧边栏「必需环境检测」逐项检测 yt-dlp / ffmpeg / deno，缺失点「一键安装」自动下载配置，全程免手动装软件

## 安装

**绿色版（推荐，发给别人也能用）**：把 `ytdlp4k.exe` 和 `tools/` 文件夹放在同一目录，整个目录拷走即可。

首次运行到侧边栏「必需环境检测」页，缺失的组件点「一键安装缺失组件」自动下载：

| 组件 | 作用 | 体积 | 落地位置 |
|------|------|------|----------|
| yt-dlp | 下载内核（官方独立版，已内置 EJS 反爬脚本） | 约 30 MB | `tools/yt-dlp.exe` |
| ffmpeg / ffprobe | 合并音视频流、转码、读属性 | 约 80 MB | `tools/ffmpeg/bin/` |
| deno | JS 运行时，解 YouTube 的 n challenge | 约 40 MB | `tools/deno.exe` |

也可手动下载放好：

- yt-dlp: <https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe> → `tools/`
- ffmpeg: <https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip> → 解压取 `bin/ffmpeg.exe`、`bin/ffprobe.exe` → `tools/ffmpeg/bin/`
- deno: <https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip> → 解压取 `deno.exe` → `tools/`

> **为什么必须要 deno**：YouTube 2025 年起强制校验 JS challenge（n signature），yt-dlp 必须调用外部 JS 运行时执行校验脚本，否则报
> `n challenge solving failed` / `The page needs to be reloaded`。deno 是 yt-dlp 官方推荐（默认启用）的运行时；已装 Node 22+ 也能用（程序会自动识别）。

**源码运行**（开发）：需要 Python 3.9+ 与 tkinter：

```bash
python ytdlp4k.pyw
```

## 使用

1. 侧边栏「下载」页：粘贴视频链接 → 选保存分类 + 分辨率档位 → 点「开始下载」
2. 侧边栏「必需环境检测」页：查看三个组件状态 / 一键安装 / 重新检测

`config.json` 与 exe 同目录，程序会自动生成并维护：

```json
{
  "proxy": "http://127.0.0.1:7897",
  "cookies_browser": "firefox",
  "lastdir_file": "~/.ytdlp4k_lastdir.txt",
  "default_fps": "0",
  "quality": "4K",
  "dirs": [
    {"name": "1080P", "path": "D:\\Videos\\1080p"},
    {"name": "4K", "path": "D:\\Videos\\4K"}
  ]
}
```

| 配置项 | 说明 |
|--------|------|
| `proxy` | HTTP 代理地址（如 `http://127.0.0.1:7897`），留空 = 直连。**国内必填**，yt-dlp 不读系统代理 |
| `cookies_browser` | 读取登录态的浏览器（`firefox` / `chrome` / `edge`），留空禁用。**下载会员/年龄限制视频需要** |
| `quality` | 分辨率档位：`原画` / `4K` / `1080P` / `720P` |
| `dirs` | 保存分类：`name` 分类名，`path` 保存路径 |
| `default_fps` | 帧率模式：`0` 不转换 / `30` / `24` |

> Cookie 说明：程序对 Firefox 会自动挑选 cookie 库最新鲜的 profile（`profiles.ini` 里的默认 profile 可能是空的，直接交给 yt-dlp 会报找不到 cookie 库）。用 Chrome / Edge 时需**完全退出浏览器**，否则 cookie 库被锁会读取失败。

## 打包为 exe（开发）

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean ytdlp4k.spec
```

产物在 `dist/ytdlp4k.exe`，也可直接双击 `build.bat`。

> **分发要点**：打包版 = 图形外壳，**不含**下载内核。分发时把 `ytdlp4k.exe` + `tools/` 整个目录拷给对方；或者只发 exe，让对方首次运行时点「一键安装缺失组件」自动补齐（需能访问 GitHub）。

## 常见问题

**报 `n challenge solving failed` 或 `The page needs to be reloaded`？**
- 没装 JS 运行时。到「必需环境检测」页看 deno 是否「就绪」，缺失就一键安装
- 若环境显示就绪但仍报错，检查是不是用错了内核（程序只用自带 `tools/yt-dlp.exe`，不会用系统 PATH 上的 pip 版 yt-dlp）

**报 `could not find firefox cookies database`？**
- 程序已自动挑选有效 profile；若仍失败，确认 Firefox 至少登录过一次 YouTube
- Chrome / Edge 需先完全退出浏览器

**下载只有 1080P，没有 4K？**
- 检查视频源本身是否提供 4K
- 分辨率档位选「原画」再试
- 走代理时，YouTube 会根据节点特征降级格式列表（Hysteria2 等 UDP 协议节点通常能拿到完整 4K 列表）

**转码提示未找到 ffmpeg？**
- 到「必需环境检测」页一键安装，或手动放到 `tools/ffmpeg/bin/`

**下载失败 / 403？**
- 更新内核：到「必需环境检测」页，把 `tools/yt-dlp.exe` 删掉后重新一键安装（会拉最新版）
- 更新 `cookies_browser` 为已登录的浏览器
- 换节点 / 检查代理

## 许可证

[MIT](LICENSE)
