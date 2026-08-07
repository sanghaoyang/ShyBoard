@echo off
rem Build WorkbenchInstaller-v<版本>.exe (onefile, windowed)
rem 版本号自动从 app.py 的 APP_VERSION 读取；内嵌同版本 zip。
rem 发版流程：build.bat -> pack_release.py <版本> -> build_installer.bat -> gh release create
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run: uv venv .venv --python 3.11
    pause
    exit /b 1
)

rem 读取 APP_VERSION（app.py 内 "APP_VERSION = "X.Y.Z""）
for /f "tokens=2 delims==" %%v in ('findstr /c:"APP_VERSION" app.py') do set "APP_VERSION=%%v"
set "APP_VERSION=%APP_VERSION: =%"
set "APP_VERSION=%APP_VERSION:"=%"
if "%APP_VERSION%"=="" (
    echo [ERROR] Cannot read APP_VERSION from app.py
    pause
    exit /b 1
)
echo APP_VERSION=%APP_VERSION%

set "ZIP=dist\Workbench-v%APP_VERSION%.zip"
if not exist "%ZIP%" (
    echo [ERROR] %ZIP% not found. Run build.bat + pack_release.py first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "WorkbenchInstaller-v%APP_VERSION%" ^
  --add-data "%ZIP%;." ^
  --hidden-import win32com.client ^
  installer.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo Build OK: dist\WorkbenchInstaller-v%APP_VERSION%.exe

rem 复制安装包到桌面（本地留存，避免每次重新下载）
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%d"
if exist "%DESKTOP%" (
    copy /Y "dist\WorkbenchInstaller-v%APP_VERSION%.exe" "%DESKTOP%\" >nul
    if errorlevel 1 (
        echo [WARN] Copy to desktop failed.
    ) else (
        echo Copied to Desktop: %DESKTOP%\WorkbenchInstaller-v%APP_VERSION%.exe
    )
) else (
    echo [WARN] Desktop path not found, skip copy.
)

pause
