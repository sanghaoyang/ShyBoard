@echo off
rem ShyBoard source-mode launcher for development and testing.
rem Port 17892 keeps the source server separate from the portable app.
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py --port 17892
) else (
    echo [ERROR] .venv not found.
    echo Run: uv venv .venv --python 3.11
    echo Then: uv pip install --python .venv/Scripts/python.exe -r requirements.txt
    pause
    exit /b 1
)
