# -*- coding: utf-8 -*-
"""
envcheck - ytdlp4k 环境检测与一键安装模块

目标：让"别人拿到手也能用"，全部组件免 Python、绿色化随包管理。
组件清单：
  1. yt-dlp.exe   —— 下载内核（官方独立 exe，约 30MB，已内置 EJS 反爬脚本）
  2. ffmpeg/ffprobe —— 合并音视频流 / 转码 / 属性查看（gyan.dev essentials 构建，约 80MB zip）
  3. deno         —— JS 运行时，解 YouTube 的 n challenge（YouTube 2025 起强制要求，约 40MB zip）

目录约定（exe/pyw 所在目录为 APP_DIR）：
  APP_DIR/tools/yt-dlp.exe
  APP_DIR/tools/ffmpeg/bin/ffmpeg.exe
  APP_DIR/tools/ffmpeg/bin/ffprobe.exe
  APP_DIR/tools/deno.exe

设计：
  - 检测三级查找：工具目录 > PATH > 常见固定位置
  - 安装全部走标准库 urllib（无第三方依赖），支持 HTTP 代理、断点续传式重写、自动重试、取消
  - 进度通过回调上报 (stage_text, fraction)，由 UI 在后台线程调用本模块
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile

# ---------------------------------------------------------------- 常量

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_MIRROR_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
# deno：yt-dlp 推荐（默认启用）的 JS 运行时，用于解 YouTube 的 n challenge。
# 官方独立版 yt-dlp.exe 自带 yt-dlp-ejs 脚本，但仍必须有 JS 运行时才能执行。
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"

COMPONENTS = ("ytdlp", "ffmpeg", "deno")


def app_dir():
    """exe/pyw 所在目录：打包后 sys.executable 目录，源码运行即源码目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """用户数据目录：装到 Program Files 等只读位置时，工具/配置放这里"""
    base = os.environ.get("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base, "ytdlp4k")


def _writable_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".~wtest")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
        return True
    except Exception:
        return False


def _tool_dirs():
    """工具搜索目录（按优先级）：
    1. exe 同目录 tools/   —— 安装包内置 / 绿色版
    2. %APPDATA%\\ytdlp4k\\tools —— 安装到只读位置时的用户级补充
    """
    return [os.path.join(app_dir(), "tools"),
            os.path.join(data_dir(), "tools")]


def tools_dir():
    """工具安装目标目录：exe 同目录可写就用它，否则用用户数据目录"""
    local = os.path.join(app_dir(), "tools")
    if os.path.isdir(local) or _writable_dir(app_dir()):
        return local
    d = os.path.join(data_dir(), "tools")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


# ---------------------------------------------------------------- 定位

def _win(name):
    return name + ".exe" if os.name == "nt" else name


def _find_in_path(name):
    p = shutil.which(name)
    return os.path.abspath(p) if p else None


def _find_fixed(name):
    """PATH 之外扫常见固定位置"""
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "ffmpeg", "bin"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "ffmpeg", "bin"),
        r"C:\ffmpeg\bin", r"D:\ffmpeg\bin",
        os.path.join(app_dir(), "tools", "ffmpeg", "bin"),
    ]
    for base in candidates:
        cand = os.path.join(base, _win(name))
        if os.path.isfile(cand):
            return cand
    return None


def find_tool(name):
    """查找顺序：自带工具目录（exe 同目录 > 用户数据目录）> PATH > 固定位置"""
    for td in _tool_dirs():
        for base in (os.path.join(td, "ffmpeg", "bin"), td):
            cand = os.path.join(base, _win(name))
            if os.path.isfile(cand):
                return cand
    p = _find_in_path(name)
    if p:
        return p
    return _find_fixed(name)


def find_local(name):
    """只在自带工具目录内查找（不含 PATH / 系统目录）"""
    for td in _tool_dirs():
        for base in (os.path.join(td, "ffmpeg", "bin"), td):
            cand = os.path.join(base, _win(name))
            if os.path.isfile(cand):
                return cand
    return None


def find_ytdlp_kernel():
    """下载内核只用自带 tools/ 的官方独立版。

    原因：PATH 上常有 pip 安装的 yt-dlp，pip 版**不含** yt-dlp-ejs 反爬脚本，
    且版本往往滞后，会导致 YouTube 报 "n challenge solving failed /
    The page needs to be reloaded"。绿色版必须用版本可控的自带内核。
    """
    return find_local("yt-dlp")


def find_js_runtime():
    """找可用的 JS 运行时（解 YouTube JS challenge 用）。返回 (名字, 路径) 或 None。

    优先自带 tools/deno.exe，其次 PATH 上的 deno / node。
    """
    local_deno = find_local("deno")
    if local_deno:
        return ("deno", local_deno)
    for name in ("deno", "node"):
        p = _find_in_path(name)
        if p:
            return (name, p)
    return None


def find_firefox_profile():
    """返回最近使用的、含 cookies.sqlite 的 Firefox profile 目录。

    不能只写 --cookies-from-browser firefox 让 yt-dlp 自己挑：profiles.ini 里
    带 Default=1 的 profile 可能是空的（无 cookies.sqlite），yt-dlp 会直接报
    "could not find firefox cookies database"。这里主动挑 cookie 库最新鲜的那个。
    """
    home = os.path.expanduser("~")
    roaming = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    bases = [
        os.path.join(roaming, "Mozilla", "Firefox", "Profiles"),
        os.path.join(local, "Packages",
                     "Mozilla.Firefox_n80bbvh6b1yt2", "LocalCache", "Roaming",
                     "Mozilla", "Firefox", "Profiles"),
    ]
    cands = []
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        try:
            for name in os.listdir(base):
                d = os.path.join(base, name)
                ck = os.path.join(d, "cookies.sqlite")
                if os.path.isfile(ck):
                    cands.append((os.path.getmtime(ck), d))
        except OSError:
            continue
    if not cands:
        return None
    cands.sort(reverse=True)
    return cands[0][1]


def tool_version(exe, args=None):
    """运行 exe 拿版本号，失败返回 None"""
    if not exe or not os.path.isfile(exe):
        return None
    args = args or ["--version"]
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output(
            [exe] + args, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            timeout=15, creationflags=flags)
        m = re.search(r"(\d{4}\.\d{2}\.\d+|[0-9.]+)", out.strip().splitlines()[0] if out.strip() else "")
        return m.group(1) if m else out.strip().splitlines()[0][:40]
    except Exception:
        return None


def check_component(key, need_ffprobe=False):
    """检测单个组件，返回 dict：ok/path/version/detail"""
    if key == "ytdlp":
        exe = find_ytdlp_kernel()
        if not exe:
            return {"ok": False, "path": None, "version": None,
                    "detail": "未找到 yt-dlp（下载内核）"}
        ver = tool_version(exe)
        return {"ok": True, "path": exe, "version": ver or "已安装",
                "detail": "%s\n%s" % (exe, ("版本 %s" % ver) if ver else "")}
    if key == "ffmpeg":
        ff = find_tool("ffmpeg")
        fp = find_tool("ffprobe")
        if ff and fp:
            ver = tool_version(ff, ["-version"])
            return {"ok": True, "path": ff, "version": ver or "已安装",
                    "detail": "%s\n%s" % (ff, ("版本 %s" % ver) if ver else "")}
        if not ff and not fp:
            return {"ok": False, "path": None, "version": None,
                    "detail": "未找到 ffmpeg / ffprobe（合并与转码）"}
        return {"ok": False, "path": None, "version": None,
                "detail": "ffmpeg 与 ffprobe 不完整，请重装"}
    if key == "deno":
        rt = find_js_runtime()
        if not rt:
            return {"ok": False, "path": None, "version": None,
                    "detail": "未找到 JS 运行时（deno / node）"}
        name, exe = rt
        ver = tool_version(exe, ["--version"])
        return {"ok": True, "path": exe, "version": ver or "已安装",
                "detail": "%s\n%s%s" % (exe, name, (" %s" % ver) if ver else "")}
    return {"ok": False, "path": None, "version": None, "detail": "未知组件"}


def check_all():
    """返回 {key: check_component(...)} 与 summary"""
    result = {}
    for k in COMPONENTS:
        result[k] = check_component(k)
    return result


# ---------------------------------------------------------------- 下载

class DownloadCancel(Exception):
    pass


def _build_opener(proxy):
    if proxy:
        handler = urllib.request.ProxyHandler({
            "http": proxy, "https": proxy})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.0f %s" % (n, unit)
        n /= 1024.0
    return "%.0f GB" % n


def download(url, dest, proxy=None, progress=None, cancel=None, retries=2,
             chunk=128 * 1024):
    """流式下载 url 到 dest。progress(stage_text, fraction)；cancel() 返回 True 则中止。
    失败重试 retries 次。返回 True/False。"""
    opener = _build_opener(proxy)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ytdlp4k/1.0"})
    last_err = None
    for attempt in range(retries + 1):
        if cancel and cancel():
            raise DownloadCancel()
        tmp = dest + ".part"
        try:
            if progress:
                progress("连接 %s (第 %d 次尝试)..." % (url.split("/")[2], attempt + 1), 0.0)
            with opener.open(req, timeout=30) as resp:
                total = resp.headers.get("Content-Length")
                total = int(total) if total and total.isdigit() else None
                done = 0
                with open(tmp, "wb") as f:
                    while True:
                        if cancel and cancel():
                            raise DownloadCancel()
                        buf = resp.read(chunk)
                        if not buf:
                            break
                        f.write(buf)
                        done += len(buf)
                        if progress:
                            frac = (done / total) if total else None
                            if frac is None:
                                progress("下载中... %s" % _human(done), None)
                            else:
                                progress("下载中... %s / %s" % (_human(done), _human(total)), frac)
            os.replace(tmp, dest)
            if progress:
                progress("下载完成", 1.0)
            return True
        except DownloadCancel:
            raise
        except Exception as e:
            last_err = e
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            if attempt < retries:
                if progress:
                    progress("下载失败(%s)，%d 秒后重试..." % (getattr(e, "reason", e), 1), None)
                import time
                time.sleep(1)
    if progress:
        progress("下载失败: %s" % last_err, None)
    return False


# ---------------------------------------------------------------- 安装

def _run_ver(exe, args=None):
    """运行 exe 校验可执行；yt-dlp 用 --version，ffmpeg 用 -version"""
    args = args or ["--version"]
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.check_output([exe] + args, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace",
                                      timeout=15, creationflags=flags)
        return True
    except Exception:
        return False


def install_ytdlp(proxy=None, progress=None, cancel=None):
    """下载官方独立 yt-dlp.exe 到 tools/"""
    td = tools_dir()
    os.makedirs(td, exist_ok=True)
    dest = os.path.join(td, _win("yt-dlp"))
    if progress:
        progress("准备下载 yt-dlp（官方独立版，约 30MB）...", 0.0)
    ok = download(YTDLP_URL, dest, proxy=proxy, progress=progress, cancel=cancel)
    if not ok or not os.path.isfile(dest):
        return False, "yt-dlp 下载失败，请检查网络（必要时在配置中填写代理）"
    if not _run_ver(dest):
        try:
            os.remove(dest)
        except OSError:
            pass
        return False, "yt-dlp 文件不完整，请重试"
    ver = tool_version(dest)
    if progress:
        progress("yt-dlp %s 安装完成" % (ver or ""), 1.0)
    return True, ver or "ok"


def install_ffmpeg(proxy=None, progress=None, cancel=None):
    """下载 gyan.dev essentials zip，解压出 ffmpeg.exe/ffprobe.exe 到 tools/ffmpeg/bin/"""
    dest_dir = os.path.join(tools_dir(), "ffmpeg", "bin")
    os.makedirs(dest_dir, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="ytdlp4k_ffmpeg_")
    zip_path = os.path.join(tmpdir, "ffmpeg.zip")
    try:
        if progress:
            progress("准备下载 ffmpeg（gyan.dev 官方构建，约 80MB）...", 0.0)
        ok = download(FFMPEG_URL, zip_path, proxy=proxy, progress=progress, cancel=cancel)
        if not ok or not os.path.isfile(zip_path):
            # 尝试备用源
            if progress:
                progress("gyan.dev 下载失败，改用 GitHub 备用源...", None)
            try:
                os.remove(zip_path)
            except OSError:
                pass
            ok = download(FFMPEG_MIRROR_URL, zip_path, proxy=proxy,
                          progress=progress, cancel=cancel)
        if not ok:
            return False, "ffmpeg 下载失败，请检查网络（必要时在配置中填写代理）"
        if progress:
            progress("解压中...", 0.95)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            ffmpeg_src = next((n for n in names if n.endswith("bin/ffmpeg.exe")), None)
            ffprobe_src = next((n for n in names if n.endswith("bin/ffprobe.exe")), None)
            if not ffmpeg_src or not ffprobe_src:
                return False, "ffmpeg 压缩包结构异常，请手动安装"
            for src, dst in ((ffmpeg_src, os.path.join(dest_dir, "ffmpeg.exe")),
                             (ffprobe_src, os.path.join(dest_dir, "ffprobe.exe"))):
                with zf.open(src) as fin, open(dst, "wb") as fout:
                    shutil.copyfileobj(fin, fout, 1024 * 1024)
        if not _run_ver(os.path.join(dest_dir, "ffmpeg.exe"), ["-version"]):
            return False, "ffmpeg 校验失败，请重试"
        if progress:
            progress("ffmpeg 安装完成", 1.0)
        return True, "ok"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def install_deno(proxy=None, progress=None, cancel=None):
    """下载 deno release zip，解压出 deno.exe 到 tools/"""
    td = tools_dir()
    os.makedirs(td, exist_ok=True)
    dest = os.path.join(td, _win("deno"))
    tmpdir = tempfile.mkdtemp(prefix="ytdlp4k_deno_")
    zip_path = os.path.join(tmpdir, "deno.zip")
    try:
        if progress:
            progress("准备下载 deno（JS 运行时，约 40MB）...", 0.0)
        ok = download(DENO_URL, zip_path, proxy=proxy, progress=progress, cancel=cancel)
        if not ok or not os.path.isfile(zip_path):
            return False, "deno 下载失败，请检查网络（必要时在配置中填写代理）"
        if progress:
            progress("解压中...", 0.95)
        with zipfile.ZipFile(zip_path) as zf:
            src = next((n for n in zf.namelist() if n.lower().endswith("deno.exe")), None)
            if not src:
                return False, "deno 压缩包结构异常，请手动安装"
            with zf.open(src) as fin, open(dest, "wb") as fout:
                shutil.copyfileobj(fin, fout, 1024 * 1024)
        if not _run_ver(dest, ["--version"]):
            try:
                os.remove(dest)
            except OSError:
                pass
            return False, "deno 校验失败，请重试"
        ver = tool_version(dest, ["--version"])
        if progress:
            progress("deno %s 安装完成" % (ver or ""), 1.0)
        return True, ver or "ok"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def install_component(key, proxy=None, progress=None, cancel=None):
    """统一安装入口。返回 (ok, msg)"""
    if key == "ytdlp":
        return install_ytdlp(proxy=proxy, progress=progress, cancel=cancel)
    if key == "ffmpeg":
        return install_ffmpeg(proxy=proxy, progress=progress, cancel=cancel)
    if key == "deno":
        return install_deno(proxy=proxy, progress=progress, cancel=cancel)
    return False, "未知组件: %s" % key


# ---------------------------------------------------------------- 便捷信息

def component_info():
    return {
        "ytdlp": {
            "name": "yt-dlp 下载内核",
            "desc": "YouTube 下载的核心引擎（官方独立版，免 Python）",
            "size": "约 30 MB",
            "what": "没有它无法下载任何视频",
        },
        "ffmpeg": {
            "name": "ffmpeg 音视频工具",
            "desc": "负责合并音视频流、帧率转换、视频属性读取",
            "size": "约 80 MB（首次下载，解压后免安装）",
            "what": "没有它 4K/1080P 高清视频无法合并出最终文件",
        },
        "deno": {
            "name": "deno JS 运行时",
            "desc": "运行 YouTube 反爬校验脚本（n challenge），YouTube 目前强制要求",
            "size": "约 40 MB（解压后单文件）",
            "what": "没有它 YouTube 会报「n challenge solving failed / 页面需要重新加载」",
        },
    }


if __name__ == "__main__":
    # 命令行自检：python envcheck.py
    print("APP_DIR :", app_dir())
    print("TOOLS   :", tools_dir())
    for key, st in check_all().items():
        print("[%s] ok=%s path=%s ver=%s" % (key, st["ok"], st["path"], st["version"]))
        if not st["ok"]:
            print("        ", st["detail"])
