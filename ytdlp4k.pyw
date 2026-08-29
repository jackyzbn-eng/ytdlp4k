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

依赖：
  - Python 3.9+，pip install yt-dlp
  - ffmpeg/ffprobe（PATH 中），转码与属性查看需要
  - tkinter（Windows 官方 Python 自带）

运行：python ytdlp4k.pyw    （或打包为 exe，见 README）
"""
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

APP_NAME = "ytdlp4k"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

DEFAULT_CONFIG = {
    "proxy": "",                       # 代理，如 "http://127.0.0.1:7897"，留空 = 不走代理
    "cookies_browser": "firefox",      # 浏览器 Cookie 来源：firefox / chrome / edge / 留空禁用
    "lastdir_file": "~/.ytdlp4k_lastdir.txt",
    "default_fps": "0",                # 0=不转换 30=转30fps 24=转24fps
    "dirs": [
        {"label": "1080P", "path": "", "fmt": "bv*[height<=1080]+ba/b[height<=1080]"},
        {"label": "4K",    "path": "", "fmt": "bv*[height<=2160]+ba/b[height<=2160]"},
    ],
}


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
        return cfg
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def expand_path(p):
    if not p:
        return p
    return os.path.expanduser(os.path.expandvars(p))


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.last_file = None
        root.title("ytdlp4k - YouTube 视频下载器")
        root.geometry("780x600")
        root.resizable(False, False)

        # 保存目录
        frame = ttk.LabelFrame(root, text="保存目录")
        frame.pack(fill="x", padx=10, pady=6)
        self.choice = tk.IntVar(value=0)
        self.dirs = self.cfg.get("dirs", [])
        for i, d in enumerate(self.dirs):
            label = d.get("label", "目录%d" % (i + 1))
            path = d.get("path", "")
            text = "[%d] %s  %s" % (i + 1, label, path if path else "(未配置，见 config.json)")
            ttk.Radiobutton(frame, text=text, variable=self.choice,
                            value=i).pack(anchor="w", padx=8, pady=2)
        ttk.Radiobutton(frame, text="[%d] 自定义路径" % (len(self.dirs) + 1),
                        variable=self.choice, value=len(self.dirs)).pack(anchor="w", padx=8, pady=2)
        self.custom_path = tk.StringVar()
        ttk.Entry(frame, textvariable=self.custom_path, width=95).pack(anchor="w", padx=24, pady=2)

        # 链接
        frame2 = ttk.LabelFrame(root, text="视频链接")
        frame2.pack(fill="x", padx=10, pady=6)
        self.url_var = tk.StringVar()
        ttk.Entry(frame2, textvariable=self.url_var, width=100).pack(padx=8, pady=6)

        # 帧率转换
        frame3 = ttk.LabelFrame(root, text="帧率转换（下载完成后自动执行，优先下载原版流）")
        frame3.pack(fill="x", padx=10, pady=6)
        self.fps_var = tk.StringVar(value=self.cfg.get("default_fps", "0"))
        ttk.Radiobutton(frame3, text="不转换", variable=self.fps_var,
                        value="0").pack(side="left", padx=10, pady=3)
        ttk.Radiobutton(frame3, text="转 30fps", variable=self.fps_var,
                        value="30").pack(side="left", padx=10, pady=3)
        ttk.Radiobutton(frame3, text="转 24fps", variable=self.fps_var,
                        value="24").pack(side="left", padx=10, pady=3)

        # 按钮
        btns = ttk.Frame(root)
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
        self.log = scrolledtext.ScrolledText(root, height=18, state="disabled")
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

    def resolve_target(self):
        c = self.choice.get()
        if 0 <= c < len(self.dirs):
            path = expand_path(self.dirs[c].get("path", ""))
            fmt = self.dirs[c].get("fmt", "bv*[height<=2160]+ba/b[height<=2160]")
            if not path:
                raise ValueError("目录 %d 未配置路径，请编辑 config.json" % (c + 1))
            return path, fmt
        p = self.custom_path.get().strip()
        if not p:
            raise ValueError("请选择目录或输入自定义路径")
        return p, "bv*[height<=2160]+ba/b[height<=2160]"

    def append_log(self, text):
        def _ins():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _ins)

    @staticmethod
    def find_tool(name):
        import shutil
        p = shutil.which(name)
        if p:
            return p
        for base in (r"C:\Program Files\ffmpeg\bin", r"D:\ffmpeg\bin", r"C:\ffmpeg\bin",
                     "/usr/bin", "/usr/local/bin"):
            cand = os.path.join(base, name + (".exe" if os.name == "nt" else ""))
            if os.path.isfile(cand):
                return cand
        return None

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
        try:
            folder, fmt = self.resolve_target()
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

        cmd = [sys.executable, "-u", "-m", "yt_dlp",
               "-o", template,
               "-f", fmt_arg,
               "--merge-output-format", "mkv"]
        proxy = self.cfg.get("proxy", "")
        if proxy:
            cmd += ["--proxy", proxy]
        cookies = self.cfg.get("cookies_browser", "")
        if cookies:
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


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
