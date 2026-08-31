@echo off
rem Build the portable, unzip-and-run ShyBoard directory.
rem Output: dist\ShyBoard-Portable\ShyBoard.exe
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found.
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean ShyBoardPortable.spec
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean ShyBoardMCP.spec
if errorlevel 1 exit /b 1

copy /Y "dist\ShyBoard-MCP.exe" "dist\ShyBoard-Portable\ShyBoard-MCP.exe" >nul
copy /Y "update.ps1" "dist\ShyBoard-Portable\update.ps1" >nul
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "scripts\sign_release.ps1"
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "scripts\package_release.ps1"
if errorlevel 1 exit /b 1
echo Build OK: dist\ShyBoard-Portable\ShyBoard.exe
