@echo off
rem Build WorkbenchInstaller.exe (onefile, windowed)
rem 内嵌 Workbench-v1.0.0.zip 作为资源；任何 Win10/11 64 位可运行，无需 Python。
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found. Run: uv venv .venv --python 3.11
    pause
    exit /b 1
)
if not exist "dist\Workbench-v1.0.0.zip" (
    echo [ERROR] dist\Workbench-v1.0.0.zip not found. Run build.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WorkbenchInstaller ^
  --add-data "dist\Workbench-v1.0.0.zip;." ^
  --hidden-import win32com.client ^
  installer.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo Build OK: dist\WorkbenchInstaller.exe
pause
