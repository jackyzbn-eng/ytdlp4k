# ytdlp4k

YouTube 视频下载器（tkinter GUI），专注高质量下载：4K / 1080P、智能帧率（30/24fps）、GPU 加速转码。

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 内核，提供图形界面、一键下载、播放、属性查看、帧率转换。

## 功能

- 🎬 **多清晰度一键下载**：预设目录 + 清晰度组合（1080P / 4K / 自定义），保存路径可配置
- 📺 **播放按钮**：下载完成后直接用系统播放器打开
- 📋 **属性查看**：ffprobe 显示分辨率 / 时长 / 帧率 / 编码 / 码率，不用打开视频
- ⏱️ **智能帧率**：选 30/24fps 时**优先下载 YouTube 原版流**（零损失）；视频没有对应帧率原版时自动用 ffmpeg 转码兜底
- 🚀 **GPU 优先转码**：检测到 NVIDIA NVENC 用硬件编码（快 5-10 倍），无 GPU 自动回退 CPU
- 📜 **实时进度日志**：下载 / 转码进度实时滚动
- 🌍 **代理支持**：可配置 HTTP 代理（走代理下载时需配合 Clash 等）

## 安装

```bash
# 1. 安装 Python 3.9+（Windows 官方包自带 tkinter）
# 2. 安装 yt-dlp
pip install -U yt-dlp
# 3. 安装 ffmpeg（转码/属性查看需要），加入 PATH
#    Windows: https://www.gyan.dev/ffmpeg/builds/ 下载 essentials 版解压并加入 PATH
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

> 注意：打包版是 GUI 外壳，下载内核仍调用 `python -m yt_dlp`，**目标电脑需安装 Python + yt-dlp + ffmpeg** 才能使用。如需完全独立免 Python 的 exe，可参考 yt-dlp 的 PyInstaller 集成方案自行扩展。

## 依赖

- Python 3.9+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（下载内核，建议保持最新）
- ffmpeg / ffprobe（转码、属性查看；下载本身也建议安装用于合并音视频流）

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
