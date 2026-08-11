@echo off
rem Build ShyBoardBeta.exe (测试版) with PyInstaller
rem 测试版：不同 exe 名 + 雾蓝 Beta 图标；app.py 检测 exe 名含 Beta 自动隐藏更新按钮。
rem 产物：dist\ShyBoardBeta\ShyBoardBeta.exe + _internal + update.ps1（拷贝自根目录）
rem 用法：先 build.bat 已有 dist\ShyBoard\（update.ps1 等随正式版一起构建），再跑本脚本。
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

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name ShyBoardBeta ^
  --icon "assets\ShyBoardBeta.ico" ^
  --add-data "static;static" ^
  --add-data "update.ps1;." ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import webview.platforms.winforms ^
  app.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

rem update.ps1 打到 _internal 后，根目录也放一份（与正式版 build.bat 行为一致）
if not exist "dist\ShyBoardBeta\update.ps1" (
    copy /Y "update.ps1" "dist\ShyBoardBeta\update.ps1" >nul
)

echo.
echo Build OK: dist\ShyBoardBeta\ShyBoardBeta.exe (Beta icon)
echo Share the whole dist\ShyBoardBeta folder.
pause
