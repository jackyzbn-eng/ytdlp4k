@echo off
rem ytdlp4k 打包脚本：双击运行，生成 dist\ytdlp4k.exe
setlocal
echo 打包 ytdlp4k...
python -m PyInstaller --onefile --noconsole --name ytdlp4k ytdlp4k.pyw
if %errorlevel%==0 (
  echo 打包完成: dist\ytdlp4k.exe
) else (
  echo 打包失败，请确认已安装 pyinstaller: pip install pyinstaller
)
pause
