@echo off
rem Build ShyboardInstaller-v<版本>.exe (onefile, windowed) + ShyboardUninstall.exe
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

set "ZIP=dist\Shyboard-v%APP_VERSION%.zip"
if not exist "%ZIP%" (
    echo [ERROR] %ZIP% not found. Run build.bat + pack_release.py first.
    pause
    exit /b 1
)

rem 1) 打包卸载器（onefile, windowed，无额外资源）
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "ShyboardUninstall" ^
  uninstaller.py
if errorlevel 1 (
    echo [ERROR] Uninstaller build failed.
    pause
    exit /b 1
)

rem 2) 打包安装器（内嵌 zip + 卸载器）
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "ShyboardInstaller-v%APP_VERSION%" ^
  --add-data "%ZIP%;." ^
  --add-data "dist\ShyboardUninstall.exe;." ^
  --hidden-import win32com.client ^
  installer.py

if errorlevel 1 (
    echo [ERROR] Installer build failed.
    pause
    exit /b 1
)

echo.
echo Build OK: dist\ShyboardInstaller-v%APP_VERSION%.exe + dist\ShyboardUninstall.exe

rem 复制安装包到桌面（本地留存，避免每次重新下载）
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%d"
if exist "%DESKTOP%" (
    copy /Y "dist\ShyboardInstaller-v%APP_VERSION%.exe" "%DESKTOP%\" >nul
    if errorlevel 1 (
        echo [WARN] Copy to desktop failed.
    ) else (
        echo Copied to Desktop: %DESKTOP%\ShyboardInstaller-v%APP_VERSION%.exe
    )
) else (
    echo [WARN] Desktop path not found, skip copy.
)

pause
