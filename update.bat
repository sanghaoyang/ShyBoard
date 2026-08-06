@echo off
rem ============================================================
rem  Workbench Updater
rem  Auto-replaces Workbench.exe and _internal from a downloaded
rem  zip, then restarts the app. Data folder is NOT touched.
rem  Runs automatically after clicking the update button.
rem ============================================================
cd /d "%~dp0"

rem ---- 1. wait until Workbench.exe is closed ----
:waitloop
tasklist /FI "IMAGENAME eq Workbench.exe" 2>nul | find /I "Workbench.exe" >nul
if %errorlevel%==0 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)

rem ---- 2. locate downloaded zip in data\updates ----
set "ZIP="
for %%f in ("data\updates\*.zip") do set "ZIP=%%f"
if not defined ZIP (
    echo [UPDATE] no update package found.
    start "" "Workbench.exe"
    exit /b 1
)
echo [UPDATE] found package: %ZIP%

rem ---- 3. extract to temp dir ----
set "TMP=__update_tmp"
if exist "%TMP%" rmdir /S /Q "%TMP%"
mkdir "%TMP%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TMP%' -Force" >nul 2>&1
if not exist "%TMP%\Workbench.exe" (
    echo [UPDATE] extraction failed.
    rmdir /S /Q "%TMP%"
    start "" "Workbench.exe"
    exit /b 1
)

rem ---- 4. replace exe + _internal (keep data) ----
if exist "Workbench.exe" del /Q "Workbench.exe"
if exist "_internal" rmdir /S /Q "_internal"
copy /Y "%TMP%\Workbench.exe" "Workbench.exe" >nul
xcopy /E /I /Y /Q "%TMP%\_internal" "_internal" >nul

rem ---- 5. cleanup ----
rmdir /S /Q "%TMP%"
del /Q "%ZIP%"

rem ---- 6. restart ----
start "" "Workbench.exe"
exit /b 0
