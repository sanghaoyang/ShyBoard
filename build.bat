@echo off
rem Build Workbench.exe with PyInstaller (for sharing with friends)
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run: uv venv .venv --python 3.11 ^&^& uv pip install --python .venv/Scripts/python.exe flask pywebview
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing pyinstaller...
    uv pip install --python .venv/Scripts/python.exe pyinstaller
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name Workbench ^
  --add-data "static;static" ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import webview.platforms.winforms ^
  app.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo Build OK: dist\Workbench\Workbench.exe
echo Share the whole dist\Workbench folder with your friend.
pause
