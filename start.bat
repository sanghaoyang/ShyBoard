@echo off
rem ShyBoard 源码模式启动器（开发/测试用）
rem 使用 .venv 里的 pythonw.exe 无窗口后台运行，不依赖打包 exe。
rem ⚠️ 固定 --port 17892：源码版与安装版（默认 17890）端口隔离，
rem    避免源码版占 17890 后安装版复用端口显示源码内容（用户规则：安装版只在手动更新时更新）。
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py --port 17892
) else (
    echo [ERROR] .venv not found. Run: uv venv .venv --python 3.11 ^&^& uv pip install --python .venv/Scripts/python.exe flask pywebview
    pause
    exit /b 1
)