@echo off
rem Build ShyBoardInstaller-v<版本>.exe (onefile, windowed) + ShyBoardUninstall.exe
rem 版本号自动从 app.py 的 APP_VERSION 读取；内嵌同版本 zip。
rem 发版流程：build.bat -> pack_release.py <版本> -> build_installer.bat -> gh release create
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run: uv venv .venv --python 3.11
    pause
    exit /b 1
)

rem 从 dist 里找 release zip（ShyBoard-*.zip），版本号从 zip 文件名推导（与内嵌资源同源，杜绝错位）
rem 注意：for /f 结束后变量是最后一次迭代的值（=最旧），必须取第一个就 goto 跳出
for /f "delims=" %%z in ('dir /b /o-d "dist\ShyBoard-*.zip" 2^>nul') do (
    set "ZIPFILE=%%z"
    goto :zipfound
)
:zipfound
if "%ZIPFILE%"=="" (
    echo [ERROR] dist\ShyBoard-*.zip not found. Run build.bat + pack_release.py first.
    pause
    exit /b 1
)
set "APP_VERSION=%ZIPFILE:ShyBoard-=%"
set "APP_VERSION=%APP_VERSION:.zip=%"
set "APP_VERSION=%APP_VERSION:v=%"
echo APP_VERSION=%APP_VERSION% (from %ZIPFILE%)

set "ZIP=dist\%ZIPFILE%"
if not exist "%ZIP%" (
    echo [ERROR] %ZIP% not found. Run build.bat + pack_release.py first.
    pause
    exit /b 1
)

rem 1) 打包卸载器（onefile, windowed，无额外资源）
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "ShyBoardUninstall" ^
  --icon "assets\ShyBoard.ico" ^
  uninstaller.py
if errorlevel 1 (
    echo [ERROR] Uninstaller build failed.
    pause
    exit /b 1
)

rem 2) 打包安装器（内嵌 zip + 卸载器）
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "ShyBoardInstaller-v%APP_VERSION%" ^
  --icon "assets\ShyBoard.ico" ^
  --add-data "%ZIP%;." ^
  --add-data "dist\ShyBoardUninstall.exe;." ^
  --hidden-import win32com.client ^
  installer.py

if errorlevel 1 (
    echo [ERROR] Installer build failed.
    pause
    exit /b 1
)

echo.
echo Build OK: dist\ShyBoardInstaller-v%APP_VERSION%.exe + dist\ShyBoardUninstall.exe

rem 复制安装包到桌面（本地留存，避免每次重新下载）
for /f "usebackq delims=" %%d in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%d"
if exist "%DESKTOP%" (
    copy /Y "dist\ShyBoardInstaller-v%APP_VERSION%.exe" "%DESKTOP%\" >nul
    if errorlevel 1 (
        echo [WARN] Copy to desktop failed.
    ) else (
        echo Copied to Desktop: %DESKTOP%\ShyBoardInstaller-v%APP_VERSION%.exe
    )
) else (
    echo [WARN] Desktop path not found, skip copy.
)

pause