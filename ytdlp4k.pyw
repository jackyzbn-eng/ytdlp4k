# -*- coding: utf-8 -*-
"""
ytdlp4k - YouTube 4K 视频下载器（tkinter GUI）

功能：
  - 多目录快捷选择 + 自定义保存路径
  - 下载进度实时显示
  - 播放按钮：下载完成后直接播放
  - 属性按钮：ffprobe 查看分辨率/时长/帧率/编码
  - 智能帧率：优先下载目标帧率原版流，无则 ffmpeg 转码兜底
  - GPU 优先转码（NVENC），无 GPU 自动回退 CPU

依赖（绿色分发，免 Python）：
  - yt-dlp.exe：下载内核，首次运行在“必需环境检测”页一键自动下载
  - ffmpeg/ffprobe：音视频合并与转码，同样自动下载
  - tkinter（Windows 官方 Python 自带）

运行：python ytdlp4k.pyw    （或打包为 exe，见 README）
"""
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

import envcheck

APP_NAME = "ytdlp4k"
# exe/pyw 所在目录（打包后 = exe 目录，config/tools 持久化在这里，而非 _MEIPASS）
APP_DIR = envcheck.app_dir()
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "proxy": "",                       # 代理，如 "http://127.0.0.1:7897"，留空 = 不走代理
    "cookies_browser": "firefox",      # 浏览器 Cookie 来源：firefox / chrome / edge / 留空禁用
    "lastdir_file": "~/.ytdlp4k_lastdir.txt",
    "default_fps": "0",                # 0=不转换 30=转30fps 24=转24fps
    "quality": "4K",                   # 下载分辨率档位（见 QUALITY）
    "dirs": [
        {"name": "1080P", "path": ""},
        {"name": "4K",    "path": ""},
    ],
}

# 下载分辨率档位：值是 yt-dlp 格式选择器，用"上限约束"实现自动降级——
# 选了 4K 但视频最高只有 1080P 时，[height<=2160] 自动取可用最高流(1080P)；
# “原画”不设上限，取该视频可读取的最高分辨率。
QUALITY = {
    "原画": "bv*+ba/b",
    "4K":   "bv*[height<=2160]+ba/b[height<=2160]",
    "1080P": "bv*[height<=1080]+ba/b[height<=1080]",
    "720P": "bv*[height<=720]+ba/b[height<=720]",
}
QUALITY_ORDER = ["原画", "4K", "1080P", "720P"]


def load_config():
    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        # 兼容旧版 dirs（label 字段 → name），并保证每个分类都有 name/path
        for i, d in enumerate(cfg.get("dirs", [])):
            if "label" in d and "name" not in d:
                d["name"] = d.pop("label")
            d.setdefault("name", "分类%d" % (i + 1))
            d.setdefault("path", "")
        # 兼容旧版：分类曾自带 fmt（画质选择已独立为 quality 档位，忽略旧 fmt）
        return cfg
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def expand_path(p):
    if not p:
        return p
    return os.path.expanduser(os.path.expandvars(p))


class App:
    """下载页：保存目录 / 链接 / 帧率 / 按钮 / 日志（嵌入主窗口内容区）"""

    def __init__(self, root, parent):
        self.root = root          # 主窗口 Tk：用于 after / messagebox / Toplevel
        self.cfg = load_config()
        self.last_file = None
        p = parent                # UI 全部构建在该容器上

        # 保存目录（分类管理）
        self.dirs = self.cfg.get("dirs", [])
        self.dir_frame = ttk.LabelFrame(p, text="保存目录（分类）")
        self.dir_frame.pack(fill="x", padx=10, pady=6)
        self.choice = tk.IntVar(value=0)
        head = ttk.Frame(self.dir_frame)
        head.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(head, text="分类名可直接改，每个分类点“浏览”选一个下载文件夹",
                  foreground="#888").pack(side="left")
        ttk.Button(head, text="＋ 添加分类", command=self._add_dir).pack(side="right")
        self.dir_box = ttk.Frame(self.dir_frame)
        self.dir_box.pack(fill="x", padx=2, pady=(0, 6))
        self._rebuild_dirs()

        # 下载分辨率（全局档位，自动降级：所选档位高于视频实际最高时取可用最高）
        qframe = ttk.LabelFrame(p, text="下载分辨率")
        qframe.pack(fill="x", padx=10, pady=6)
        self.quality_var = tk.StringVar(value=self.cfg.get("quality", "4K"))
        for q in QUALITY_ORDER:
            ttk.Radiobutton(qframe, text=q, variable=self.quality_var,
                            value=q, command=self._on_quality).pack(side="left", padx=12, pady=4)
        ttk.Label(qframe, text="选了比视频实际更高的档位时会自动下载可用的最高画质",
                  foreground="#888").pack(side="left", padx=(16, 0))

        # 链接
        frame2 = ttk.LabelFrame(p, text="视频链接")
        frame2.pack(fill="x", padx=10, pady=6)
        self.url_var = tk.StringVar()
        ttk.Entry(frame2, textvariable=self.url_var, width=100).pack(padx=8, pady=6)

        # 代理：国内访问 YouTube 必须走代理（yt-dlp 不读系统代理设置，要显式传）
        prow = ttk.Frame(frame2)
        prow.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(prow, text="网络代理:").pack(side="left")
        self.proxy_var = tk.StringVar(value=self.cfg.get("proxy", ""))
        ttk.Entry(prow, textvariable=self.proxy_var, width=30).pack(side="left", padx=(4, 8))
        ttk.Label(prow, text="国内需填，如 http://127.0.0.1:7897（Clash 默认端口）；留空=直连",
                  foreground="#888").pack(side="left")

        # 帧率转换
        frame3 = ttk.LabelFrame(p, text="帧率转换（下载完成后自动执行，优先下载原版流）")
        frame3.pack(fill="x", padx=10, pady=6)
        self.fps_var = tk.StringVar(value=self.cfg.get("default_fps", "0"))
        ttk.Radiobutton(frame3, text="不转换", variable=self.fps_var,
                        value="0").pack(side="left", padx=10, pady=3)
        ttk.Radiobutton(frame3, text="转 30fps", variable=self.fps_var,
                        value="30").pack(side="left", padx=10, pady=3)
        ttk.Radiobutton(frame3, text="转 24fps", variable=self.fps_var,
                        value="24").pack(side="left", padx=10, pady=3)

        # 按钮
        btns = ttk.Frame(p)
        btns.pack(fill="x", padx=10, pady=4)
        self.btn = ttk.Button(btns, text="下载", command=self.start_download)
        self.btn.pack(side="left", padx=5)
        self.play_btn = ttk.Button(btns, text="播放", command=self.play_last, state="disabled")
        self.play_btn.pack(side="left", padx=5)
        self.prop_btn = ttk.Button(btns, text="属性", command=self.show_props, state="disabled")
        self.prop_btn.pack(side="left", padx=5)
        ttk.Button(btns, text="清空日志",
                   command=lambda: self.log.configure(state="normal") or self.log.delete("1.0", "end") or self.log.configure(state="disabled")).pack(side="left", padx=5)
        self.status = ttk.Label(btns, text="就绪")
        self.status.pack(side="right", padx=5)

        # 日志
        self.log = scrolledtext.ScrolledText(p, height=18, state="disabled")
        self.log.pack(fill="both", expand=True, padx=10, pady=6)

        self.load_last()

    # ---------- 配置与工具 ----------
    def load_last(self):
        lastfile = expand_path(self.cfg.get("lastdir_file", ""))
        if lastfile and os.path.exists(lastfile):
            with open(lastfile, encoding="utf-8", errors="ignore") as f:
                last = f.read().strip()
            if last:
                self.append_log("上次目录: %s" % last)

    # ---------- 分类（保存目录）管理 ----------
    def _rebuild_dirs(self):
        """按 self.dirs 重建分类行：◉ [分类名][路径][浏览][✕]"""
        for w in self.dir_box.winfo_children():
            w.destroy()
        self.dir_name_vars = []
        self.dir_path_vars = []
        for i, d in enumerate(self.dirs):
            row = ttk.Frame(self.dir_box)
            row.pack(fill="x", padx=4, pady=1)
            ttk.Radiobutton(row, variable=self.choice, value=i).pack(side="left")
            nv = tk.StringVar(value=d.get("name", ""))
            nv.trace_add("write", self._on_dir_edited)
            self.dir_name_vars.append(nv)
            ttk.Entry(row, textvariable=nv, width=13).pack(side="left", padx=(0, 6))
            pv = tk.StringVar(value=d.get("path", ""))
            self.dir_path_vars.append(pv)
            ttk.Entry(row, textvariable=pv, width=44, state="readonly").pack(side="left")
            ttk.Button(row, text="浏览", width=5,
                       command=lambda i=i: self._pick_dir(i)).pack(side="left", padx=4)
            ttk.Button(row, text="✕", width=2,
                       command=lambda i=i: self._del_dir(i)).pack(side="left")
        # 单选值越界时收回（删除分类导致）
        if self.choice.get() < 0:
            self.choice.set(0)
        elif self.choice.get() >= len(self.dirs):
            self.choice.set(max(0, len(self.dirs) - 1))

    def _sync_dirs(self):
        """把界面编辑结果写回 self.dirs 并持久化"""
        for i, d in enumerate(self.dirs):
            if i < len(self.dir_name_vars):
                nm = self.dir_name_vars[i].get().strip()
                d["name"] = nm or ("分类%d" % (i + 1))
            if i < len(self.dir_path_vars):
                d["path"] = self.dir_path_vars[i].get()
        self._save_cfg()

    def _on_dir_edited(self, *_):
        self._sync_dirs()

    def _save_cfg(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _pick_dir(self, i):
        name = self.dir_name_vars[i].get().strip() or ("分类%d" % (i + 1))
        path = filedialog.askdirectory(title="选择“%s”的下载文件夹" % name)
        if path:
            self.dir_path_vars[i].set(path)
            self.choice.set(i)
            self._sync_dirs()
            self.status.configure(text="分类“%s”目录: %s" % (name, path))

    def _add_dir(self):
        self.dirs.append({"name": "新分类", "path": ""})
        self.choice.set(len(self.dirs) - 1)
        self._rebuild_dirs()
        self._save_cfg()

    def _del_dir(self, i):
        if len(self.dirs) <= 1:
            messagebox.showinfo("提示", "至少保留一个分类")
            return
        del self.dirs[i]
        if self.choice.get() >= len(self.dirs):
            self.choice.set(max(0, len(self.dirs) - 1))
        self._rebuild_dirs()
        self._save_cfg()

    def _on_quality(self):
        self.cfg["quality"] = self.quality_var.get()
        self._save_cfg()

    def get_fmt(self):
        """按当前下载分辨率档位取格式选择器（档位是上限，视频不够高时自动取可用最高）"""
        return QUALITY.get(self.quality_var.get(), QUALITY["4K"])

    def resolve_target(self):
        self._sync_dirs()   # 以界面当前值为准（防 name/path var 已改未落盘）
        c = self.choice.get()
        if 0 <= c < len(self.dirs):
            d = self.dirs[c]
            path = expand_path(d.get("path", ""))
            if not path:
                raise ValueError("分类“%s”还没选下载文件夹，点它后面的“浏览”选一个"
                                 % (d.get("name") or "分类%d" % (c + 1)))
            return path
        raise ValueError("请先选一个分类")

    def append_log(self, text):
        def _ins():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _ins)

    @staticmethod
    def find_tool(name):
        return envcheck.find_tool(name)

    def has_nvenc(self):
        """检测 ffmpeg 是否支持 NVIDIA NVENC"""
        ffmpeg = self.find_tool("ffmpeg")
        if not ffmpeg:
            return False
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.check_output(
                [ffmpeg, "-hide_banner", "-encoders"],
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=flags)
            return "h264_nvenc" in out
        except Exception:
            return False

    @staticmethod
    def parse_fps(s):
        try:
            num, den = s.split("/")
            return round(float(num) / float(den), 2)
        except Exception:
            return "?"

    def get_file_fps(self, path):
        fp = self.find_tool("ffprobe")
        if not fp:
            return None
        import json as _json
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.check_output(
                [fp, "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=r_frame_rate", "-of", "json", path],
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=flags)
            data = _json.loads(out)
            streams = data.get("streams", [])
            if streams:
                return self.parse_fps(streams[0].get("r_frame_rate", "0/1"))
            return None
        except Exception:
            return None

    def convert_fps(self, src, fps):
        """用 ffmpeg 转帧率（GPU 优先），返回新文件路径；失败返回 None"""
        ffmpeg = self.find_tool("ffmpeg")
        if not ffmpeg:
            self.append_log("未找到 ffmpeg，跳过帧率转换")
            return None
        base, _ = os.path.splitext(src)
        dst = "%s_%sfps.mkv" % (base, fps)
        if self.has_nvenc():
            vcodec = ["-c:v", "h264_nvenc", "-preset", "p5", "-cq", "18", "-b:v", "0"]
            self.append_log(">>> 使用 GPU (NVENC) 转码")
        else:
            vcodec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
            self.append_log(">>> 未检测到 NVENC，使用 CPU (libx264) 转码")
        cmd = [ffmpeg, "-y", "-i", src, "-vf", "fps=%s" % fps] + vcodec + ["-c:a", "copy", dst]
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags)
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.append_log(line)
            proc.wait()
            if proc.returncode == 0 and os.path.exists(dst):
                return dst
            self.append_log("帧率转换失败 (exit %d)" % proc.returncode)
            return None
        except Exception as e:
            self.append_log("帧率转换错误: %s" % e)
            return None

    # ---------- 下载 ----------
    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请粘贴视频链接")
            return
        # 代理即时落盘，下次启动保留
        self.cfg["proxy"] = self.proxy_var.get().strip()
        self._save_cfg()
        try:
            folder = self.resolve_target()
            fmt = self.get_fmt()
            self.append_log(">>> 分辨率档位: %s" % self.quality_var.get())
        except ValueError as e:
            messagebox.showwarning("提示", str(e))
            return
        try:
            os.makedirs(folder, exist_ok=True)
            lastfile = expand_path(self.cfg.get("lastdir_file", ""))
            if lastfile:
                with open(lastfile, "w", encoding="utf-8") as f:
                    f.write(folder)
        except Exception as e:
            messagebox.showerror("错误", "无法创建目录: %s" % e)
            return
        self.btn.configure(state="disabled")
        self.status.configure(text="下载中...")
        threading.Thread(target=self.download_worker, args=(url, folder, fmt), daemon=True).start()

    def download_worker(self, url, folder, fmt):
        template = os.path.join(folder, "%(title)s.%(ext)s")
        fps = self.fps_var.get()
        fmt_arg = fmt
        if fps in ("30", "24"):
            if "+" in fmt and "/" in fmt:
                bv_part, rest = fmt.split("+", 1)
                ba_part = rest.split("/")[0]
                fmt_arg = "%s[fps<=%s]+%s[fps<=%s]/%s" % (bv_part, fps, ba_part, fps, fmt)
            self.append_log(">>> 帧率模式: 优先下载 %sfps 原版流，无则转码兜底" % fps)

        # 下载内核：只用自带 tools/ 的官方独立版。
        # pip 安装的 yt-dlp 不含 yt-dlp-ejs 反爬脚本且版本滞后，会导致
        # YouTube 报 "n challenge solving failed / The page needs to be reloaded"，
        # 所以绝不回退到 PATH 上的其它 yt-dlp。
        ytdlp_exe = envcheck.find_ytdlp_kernel()
        if not ytdlp_exe:
            self.append_log(">>> 错误：未找到下载内核 tools/yt-dlp.exe")
            self.append_log(">>> 请切换到左侧「必需环境检测」页，点「一键安装缺失组件」")
            self.status.configure(text="缺少内核")
            self.btn.configure(state="normal")
            self.root.after(0, lambda: messagebox.showwarning(
                "缺少下载内核",
                "未找到 tools/yt-dlp.exe。\n请到左侧「必需环境检测」页点「一键安装缺失组件」。"))
            return

        cmd = [ytdlp_exe, "-o", template, "-f", fmt_arg,
               "--merge-output-format", "mkv", "--no-update"]
        ffmpeg_exe = envcheck.find_tool("ffmpeg")
        if ffmpeg_exe:
            cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg_exe)]
        self.append_log(">>> 内核: %s" % ytdlp_exe)

        # JS 运行时：YouTube 现在强制要求解 n challenge（YouTube 2025 起）
        rt = envcheck.find_js_runtime()
        if rt:
            rt_name, rt_exe = rt
            cmd += ["--js-runtimes", "%s:%s" % (rt_name, rt_exe)]
            self.append_log(">>> JS 运行时: %s (%s)" % (rt_name, rt_exe))
        else:
            self.append_log(">>> 警告：未检测到 deno/node，YouTube 可能报"
                            "「n challenge solving failed」，请到环境检测页安装 deno")

        proxy = self.cfg.get("proxy", "")
        if proxy:
            cmd += ["--proxy", proxy]
            self.append_log(">>> 代理: %s" % proxy)

        cookies = self.cfg.get("cookies_browser", "")
        if cookies:
            if cookies == "firefox":
                # 主动挑 cookie 库最新的 profile：profiles.ini 里的 Default 可能指向空 profile
                prof = envcheck.find_firefox_profile()
                if prof:
                    cmd += ["--cookies-from-browser", "firefox:%s" % prof]
                    self.append_log(">>> Cookies: firefox profile %s" % os.path.basename(prof))
                else:
                    self.append_log(">>> 警告：未找到含 cookies.sqlite 的 Firefox profile，跳过 cookies")
            elif cookies == "chrome" or cookies == "edge":
                cmd += ["--cookies-from-browser", cookies]
                self.append_log(">>> Cookies: %s（浏览器需完全退出，否则可能读取失败）" % cookies)
            else:
                cmd += ["--cookies-from-browser", cookies]
        cmd.append(url)

        self.append_log(">>> 开始下载: %s" % url)
        self.append_log(">>> 保存到: %s" % folder)
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags)
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.append_log(line)
            proc.wait()
            if proc.returncode == 0:
                exts = (".mkv", ".mp4", ".webm")
                candidates = []
                try:
                    for fn in os.listdir(folder):
                        if fn.lower().endswith(exts):
                            p = os.path.join(folder, fn)
                            if os.path.isfile(p):
                                candidates.append((os.path.getmtime(p), p))
                except OSError:
                    pass
                if candidates:
                    self.last_file = max(candidates)[1]
                    fps = self.fps_var.get()
                    if fps not in ("", "0"):
                        cur = self.get_file_fps(self.last_file)
                        if cur and cur <= float(fps) + 0.5:
                            self.append_log(">>> 下载的已是 %sfps，无需转换" % cur)
                        else:
                            self.append_log(">>> 开始转换帧率到 %sfps ..." % fps)
                            self.status.configure(text="转换帧率中...")
                            new_path = self.convert_fps(self.last_file, fps)
                            if new_path:
                                self.last_file = new_path
                                self.append_log("=== 帧率转换完成: %s ===" % new_path)
                            else:
                                self.append_log("=== 帧率转换失败，保留原文件 ===")
                    self.play_btn.configure(state="normal")
                    self.prop_btn.configure(state="normal")
                    self.append_log("=== 下载完成: %s ===" % self.last_file)
                    self.status.configure(text="完成")
                else:
                    self.append_log("=== 下载完成（未找到文件）===")
                    self.status.configure(text="完成")
            else:
                self.append_log("=== 下载失败 (exit %d) ===" % proc.returncode)
                self.status.configure(text="失败")
        except Exception as e:
            self.append_log("错误: %s" % e)
            self.status.configure(text="错误")
        self.btn.configure(state="normal")
        self.root.after(0, lambda: messagebox.showinfo("完成", "下载流程已结束，请查看日志确认结果"))

    # ---------- 播放 / 属性 ----------
    def play_last(self):
        if self.last_file and os.path.exists(self.last_file):
            try:
                os.startfile(self.last_file)
            except Exception as e:
                messagebox.showerror("错误", "无法打开: %s" % e)
        else:
            messagebox.showwarning("提示", "还没有已下载的视频")

    def show_props(self):
        if not self.last_file or not os.path.exists(self.last_file):
            messagebox.showwarning("提示", "还没有已下载的视频")
            return
        fp = self.find_tool("ffprobe")
        if not fp:
            messagebox.showerror("错误", "未找到 ffprobe（ffmpeg 套件），请安装 ffmpeg")
            return
        import json as _json
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.check_output(
                [fp, "-v", "error",
                 "-show_entries", "format=duration,size,bit_rate:stream=codec_name,codec_type,width,height,r_frame_rate",
                 "-of", "json", self.last_file],
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                creationflags=flags)
            data = _json.loads(out)
        except Exception as e:
            messagebox.showerror("错误", "读取属性失败: %s" % e)
            return
        fmt = data.get("format", {})
        dur = float(fmt.get("duration", 0) or 0)
        size = int(fmt.get("size", 0) or 0)
        br = int(fmt.get("bit_rate", 0) or 0)
        streams = data.get("streams", [])
        vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
        astream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        mm, ss = int(dur // 60), int(dur % 60)
        lines = [
            "文件: %s" % os.path.basename(self.last_file),
            "大小: %.2f MB" % (size / 1048576.0),
            "时长: %d 分 %02d 秒" % (mm, ss),
            "分辨率: %s x %s" % (vstream.get("width", "?"), vstream.get("height", "?")),
            "视频编码: %s" % vstream.get("codec_name", "?"),
            "帧率: %s fps" % self.parse_fps(vstream.get("r_frame_rate", "0/1")),
            "音频编码: %s" % astream.get("codec_name", "无"),
            "总码率: %d kbps" % (br / 1000) if br else "总码率: ?",
        ]
        win = tk.Toplevel(self.root)
        win.title("视频属性")
        win.geometry("520x300")
        txt = tk.Text(win, font=("Microsoft YaHei", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")


class EnvPage:
    """必需环境检测页：yt-dlp / ffmpeg / deno 状态检测 + 一键安装（嵌入主窗口内容区）"""

    STATE_COLORS = {"ok": "#1a7f37", "miss": "#c62828", "busy": "#b26a00", "idle": "#888"}

    def __init__(self, root, parent):
        self.root = root          # 主窗口 Tk：用于 after / messagebox
        self.cfg = load_config()
        self.info = envcheck.component_info()
        self.results = {}
        self.status_var = {}
        self.status_lbl = {}
        self.bar = {}
        self.installing = False

        pad = ttk.Frame(parent, padding=24)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text="必需环境检测",
                  font=("Microsoft YaHei", 15, "bold")).pack(anchor="w")
        ttk.Label(pad, text="ytdlp4k 需要三个组件：yt-dlp（下载内核）、ffmpeg（音视频合并/转码）、"
                            "deno（YouTube 反爬校验的 JS 运行时）。"
                            "缺失的组件点“一键安装缺失组件”即可自动下载配置，无需手动装软件、无需 Python。",
                  foreground="#666", wraplength=700).pack(anchor="w", pady=(4, 12))

        for key in envcheck.COMPONENTS:
            self._build_row(pad, key)

        # 进度区
        self.progress_bar = ttk.Progressbar(pad, mode="determinate", maximum=1000)
        self.progress_bar.pack(fill="x", pady=(16, 4))
        self.progress_var = tk.StringVar(value="")
        ttk.Label(pad, textvariable=self.progress_var, foreground="#555").pack(anchor="w")

        # 按钮区
        btns = ttk.Frame(pad)
        btns.pack(fill="x", pady=(18, 0))
        self.install_btn = ttk.Button(btns, text="一键安装缺失组件", command=self.install_missing)
        self.install_btn.pack(side="left")
        ttk.Button(btns, text="重新检测", command=self.refresh).pack(side="right")

        self.hint_var = tk.StringVar()
        ttk.Label(pad, textvariable=self.hint_var, foreground="#c55",
                  wraplength=700).pack(anchor="w", pady=(10, 0))

        # 后台线程 → 主线程消息队列（避免跨线程直接调 tkinter）
        self._q = queue.Queue()
        self._pump()

        self.refresh()

    def _post(self, fn):
        """后台线程安全地向主线程投递回调"""
        self._q.put(fn)

    def _pump(self):
        try:
            while True:
                fn = self._q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    # ---------- UI 构建 ----------
    def _build_row(self, parent, key):
        info = self.info[key]
        card = ttk.Frame(parent, padding=(12, 10), relief="groove")
        card.pack(fill="x", pady=6)
        head = ttk.Frame(card)
        head.pack(fill="x")
        ttk.Label(head, text=info["name"], font=("Microsoft YaHei", 11, "bold")).pack(side="left")
        sv = tk.StringVar(value="检测中...")
        st = ttk.Label(head, textvariable=sv, foreground=self.STATE_COLORS["idle"])
        st.pack(side="right")
        self.status_var[key] = sv
        self.status_lbl[key] = st
        ttk.Label(card, text=info["desc"], foreground="#888").pack(anchor="w", pady=(2, 0))
        bar = ttk.Progressbar(card, mode="determinate", maximum=1000)
        self.bar[key] = bar

    # ---------- 检测 ----------
    def refresh(self):
        self.installing = False
        for key in self.status_var:
            self.status_var[key].set("检测中...")
            self.status_lbl[key].configure(foreground=self.STATE_COLORS["idle"])
        self.progress_bar["value"] = 0
        self.progress_var.set("正在检测本机环境...")
        threading.Thread(target=self._detect_worker, daemon=True).start()

    def _detect_worker(self):
        results = envcheck.check_all()
        self._post(lambda: self._apply_results(results))

    def _apply_results(self, results):
        self.results = results
        missing = [k for k, st in results.items() if not st["ok"]]
        for key, st in results.items():
            sv = self.status_var[key]
            if st["ok"]:
                sv.set("就绪 · %s" % st["version"])
                self.status_lbl[key].configure(foreground=self.STATE_COLORS["ok"])
            else:
                sv.set("未安装")
                self.status_lbl[key].configure(foreground=self.STATE_COLORS["miss"])
        if missing:
            self.install_btn.configure(state="normal")
            self.hint_var.set("缺少: " + "、".join(self.info[k]["name"] for k in missing) +
                              "。点击“一键安装缺失组件”自动下载（首次约需 150 MB）。" +
                              "若下载缓慢，可在 config.json 中配置 proxy 后点“重新检测”重试。")
        else:
            self.install_btn.configure(state="disabled")
            self.hint_var.set("环境就绪，可直接在“下载”页使用")
        self.progress_var.set("")

    # ---------- 一键安装 ----------
    def install_missing(self):
        if self.installing:
            return
        missing = [k for k, st in self.results.items() if not st["ok"]]
        if not missing:
            return
        self.installing = True
        self.install_btn.configure(state="disabled")
        self.hint_var.set("")
        for key in missing:
            self.status_var[key].set("安装中...")
            self.status_lbl[key].configure(foreground=self.STATE_COLORS["busy"])
            self.bar[key].pack(fill="x", pady=(8, 0))
        threading.Thread(target=self._install_worker, args=(missing,), daemon=True).start()

    def _install_worker(self, missing):
        proxy = self.cfg.get("proxy", "") or None
        ok_all = True
        for key in envcheck.COMPONENTS:
            if key not in missing:
                continue
            name = self.info[key]["name"]

            def _mark(text, frac, key=key, name=name):
                def _up():
                    if frac is None:
                        self.bar[key]["value"] = 0
                    else:
                        self.bar[key]["value"] = int(frac * 1000)
                    self.progress_var.set("%s: %s" % (name, text))
                self._post(_up)

            ok, msg = envcheck.install_component(
                key, proxy=proxy,
                progress=lambda t, f, key=key: _mark(t, f, key))
            if not ok:
                ok_all = False
                def _fail(key=key, msg=msg):
                    self.status_var[key].set("安装失败")
                    self.status_lbl[key].configure(foreground=self.STATE_COLORS["miss"])
                    self.hint_var.set(msg)
                self._post(_fail)
                break
        self._post(lambda: self._install_finished(ok_all))

    def _install_finished(self, ok_all):
        self.installing = False
        if ok_all:
            self.progress_var.set("全部安装完成，正在确认...")
            self.refresh()
        else:
            self.install_btn.configure(state="normal")


class MainWindow:
    """主窗口：左侧导航栏（下载 / 必需环境检测）+ 右侧内容区"""

    NAV = [("download", "下载"), ("env", "必需环境检测")]

    def __init__(self, root):
        self.root = root
        root.title("ytdlp4k - YouTube 4K 视频下载器")
        root.geometry("960x620")
        root.resizable(False, False)

        # ---------- 左侧导航栏 ----------
        side_bg = "#eceff1"
        self.side = tk.Frame(root, bg=side_bg, width=176)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)

        tk.Label(self.side, text="ytdlp4k", font=("Microsoft YaHei", 16, "bold"),
                 bg=side_bg, fg="#333").pack(anchor="w", padx=18, pady=(20, 22))

        self.nav_btns = {}
        for key, text in self.NAV:
            b = tk.Button(self.side, text=text, font=("Microsoft YaHei", 10),
                          relief="flat", bd=0, anchor="w", padx=14, pady=9,
                          bg=side_bg, fg="#333",
                          activebackground="#d7dce0",
                          command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=10, pady=3)
            self.nav_btns[key] = b

        # ---------- 右侧内容区 ----------
        content = tk.Frame(root)
        content.pack(side="left", fill="both", expand=True)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self.pages = {}
        self.pages["download"] = self._make_page(content, App)
        self.pages["env"] = self._make_page(content, EnvPage)
        self.show("download")

    def _make_page(self, content, page_cls):
        f = tk.Frame(content)
        f.grid(row=0, column=0, sticky="nsew")
        inst = page_cls(self.root, f)
        inst.frame = f
        return inst

    def show(self, key):
        """切换右侧页面并高亮侧边栏当前项"""
        self.pages[key].frame.tkraise()
        sel_bg = "#bcd6ee"
        for k, b in self.nav_btns.items():
            if k == key:
                b.configure(bg=sel_bg, fg="#0d47a1")
            else:
                b.configure(bg="#eceff1", fg="#333")


def main():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
