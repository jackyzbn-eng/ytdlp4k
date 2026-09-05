# ytdlp4k

YouTube 视频下载器（tkinter GUI），专注高质量下载：4K / 1080P、智能帧率（30/24fps）、GPU 加速转码。

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 内核，提供图形界面、一键下载、播放、属性查看、帧率转换。

**免 Python、绿色分发**：内置环境自动检测与一键安装，拿到手双击即用，适合直接发给别人。

## 功能

- 🎬 **多清晰度一键下载**：预设目录 + 清晰度组合（1080P / 4K / 自定义），保存路径可配置
- 📺 **播放按钮**：下载完成后直接用系统播放器打开
- 📋 **属性查看**：ffprobe 显示分辨率 / 时长 / 帧率 / 编码 / 码率，不用打开视频
- ⏱️ **智能帧率**：选 30/24fps 时**优先下载 YouTube 原版流**（零损失）；视频没有对应帧率原版时自动用 ffmpeg 转码兜底
- 🚀 **GPU 优先转码**：检测到 NVIDIA NVENC 用硬件编码（快 5-10 倍），无 GPU 自动回退 CPU
- 📜 **实时进度日志**：下载 / 转码进度实时滚动
- 🌍 **代理支持**：可配置 HTTP 代理（走代理下载时需配合 Clash 等）
- 🧩 **环境自检引导页**：首次运行自动检测 yt-dlp / ffmpeg，缺失时点“一键安装”自动下载配置，全程免手动装软件

## 安装

**绿色版（推荐，发给别人也能用）**：整个文件夹拷走即可，无需安装任何东西。

- 首次运行自动检测两个组件，缺失时点“一键安装”自动下载：
  - **yt-dlp**（下载内核，官方独立版）→ 存到 `tools/yt-dlp.exe`
  - **ffmpeg**（合并/转码，官方构建）→ 存到 `tools/ffmpeg/bin/`
- 也可手动下载放好（跳过引导）：
  - yt-dlp: <https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe> → `tools/`
  - ffmpeg: <https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip> → 解压后取 `bin/ffmpeg.exe`、`bin/ffprobe.exe` 放 `tools/ffmpeg/bin/`

**源码运行**（开发）：需要 Python 3.9+，可选 `pip install yt-dlp`（下载内核会优先用独立版，无需 pip 安装也可运行）：

```bash
python ytdlp4k.pyw
```

## 使用

```bash
python ytdlp4k.pyw
```

首次运行会生成 `config.json`，编辑它配置你的目录 / 代理 / 浏览器 Cookie：

```json
{
  "proxy": "http://127.0.0.1:7897",
  "cookies_browser": "firefox",
  "lastdir_file": "~/.ytdlp4k_lastdir.txt",
  "default_fps": "0",
  "dirs": [
    {"label": "1080P", "path": "D:\\Videos\\1080p", "fmt": "bv*[height<=1080]+ba/b[height<=1080]"},
    {"label": "4K", "path": "D:\\Videos\\4K", "fmt": "bv*[height<=2160]+ba/b[height<=2160]"}
  ]
}
```

| 配置项 | 说明 |
|--------|------|
| `proxy` | HTTP 代理地址，留空 = 不走代理 |
| `cookies_browser` | 从哪个浏览器读取登录态 Cookie（`firefox` / `chrome` / `edge`），留空禁用。**下载会员/年龄限制视频需要** |
| `dirs` | 预设保存目录：`label` 显示名，`path` 保存路径，`fmt` yt-dlp 格式选择器 |
| `default_fps` | 默认帧率模式：`0` 不转换 / `30` / `24` |

> 提示：Cookie 方式下载 YouTube 时，建议在对应浏览器中保持已登录状态。

## 打包为 exe（可选）

```bash
pip install pyinstaller
python -m PyInstaller --onefile --noconsole --name ytdlp4k ytdlp4k.pyw
```

产物在 `dist/ytdlp4k.exe`。也可直接双击 `build.bat`。

> 打包版 = 图形外壳 + 内置下载内核。首次运行同样会自动检测/一键安装 yt-dlp 与 ffmpeg 到 exe 同目录 `tools/`，**无需目标电脑安装 Python**。分发给别人时整个文件夹（exe + tools）拷走即可，或只发 exe（首次运行自动下载组件）。

## 依赖（运行时自动准备，也可手动预置）

- **yt-dlp**（下载内核，官方独立版）→ `tools/yt-dlp.exe`
- **ffmpeg / ffprobe**（合并、转码、属性）→ `tools/ffmpeg/bin/`
- 开发/源码运行时才需要 Python 3.9+ 与 `pip install yt-dlp`（可选）

## 常见问题

**下载只有 1080P，没有 4K？**
- 检查视频源本身是否提供 4K
- 检查 `config.json` 中 `dirs` 的 `fmt` 是否包含 `[height<=2160]`
- 走代理时，YouTube 会根据节点特征降级格式列表（Hysteria2 等 UDP 协议节点通常能拿到完整 4K 列表）

**转码提示未找到 ffmpeg？**
- 确认 ffmpeg 已安装并加入 PATH，或放到常见位置（`C:\Program Files\ffmpeg\bin` 等）

**下载失败 / 403？**
- YouTube 反爬频繁更新，先升级 yt-dlp：`pip install -U --pre "yt-dlp[default]"`（nightly 版通常最先适配）
- 更新 `cookies_browser` 为已登录的浏览器
- 换节点 / 检查代理

## 许可证

[MIT](LICENSE)
