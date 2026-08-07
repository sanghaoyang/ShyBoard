@echo off
rem ShyBoard 源码模式启动器（开发/测试用）
rem 使用 .venv 里的 pythonw.exe 无窗口后台运行，不依赖打包 exe。
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py
) else (
    echo [ERROR] .venv not found. Run: uv venv .venv --python 3.11 ^&^& uv pip install --python .venv/Scripts/python.exe flask pywebview
    pause
    exit /b 1
)
