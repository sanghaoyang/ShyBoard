@echo off
rem ============================================================
rem  Workbench Updater
rem  Replaces Workbench.exe and _internal from a downloaded zip,
rem  then restarts the app with the SAME port as before.
rem  Data folder is NOT touched.
rem  Waits for the exact app PID (data\updates\app.pid) to exit,
rem  NOT any other Workbench.exe instance (multi-instance safe).
rem ============================================================
cd /d "%~dp0"

set "PIDFILE=data\updates\app.pid"
set "ARGSFILE=data\updates\app.args"
set "RESTART_PORT="
if exist "%ARGSFILE%" set /p RESTART_PORT=<"%ARGSFILE%"

rem ---- 1. wait for the exact app process (max 60s) ----
set "FIND=%SystemRoot%\System32\find.exe"
set "TASKLIST=%SystemRoot%\System32\tasklist.exe"
if not exist "%PIDFILE%" goto :skipwait
set /a TRY=0
:waitloop
set /p APP_PID=<"%PIDFILE%"
"%TASKLIST%" /FI "PID eq %APP_PID%" 2>nul | "%FIND%" /I "%APP_PID%" >nul
if errorlevel 1 goto :waitdone
set /a TRY+=1
if %TRY% geq 60 (
    echo [UPDATE] timed out waiting for app to exit, aborting.
    del /Q "%PIDFILE%" 2>nul
    exit /b 2
)
timeout /t 1 /nobreak >nul
goto waitloop
:waitdone
echo [UPDATE] app exited.
:skipwait

rem ---- 2. locate downloaded zip in data\updates ----
set "ZIP="
for %%f in ("data\updates\*.zip") do set "ZIP=%%f"
if not defined ZIP (
    echo [UPDATE] no update package found.
    goto :restart
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
    goto :restart
)

rem ---- 4. replace exe + _internal (keep data) ----
if exist "Workbench.exe" del /Q "Workbench.exe"
if exist "_internal" rmdir /S /Q "_internal"
copy /Y "%TMP%\Workbench.exe" "Workbench.exe" >nul
xcopy /E /I /Y /Q "%TMP%\_internal" "_internal" >nul

rem ---- 5. cleanup ----
rmdir /S /Q "%TMP%"
del /Q "%ZIP%" 2>nul
del /Q "%PIDFILE%" 2>nul
del /Q "%ARGSFILE%" 2>nul

rem ---- 6. restart with original port ----
:restart
if "%RESTART_PORT%"=="" (
    start "" "Workbench.exe"
) else (
    start "" "Workbench.exe" --port %RESTART_PORT%
)
exit /b 0
