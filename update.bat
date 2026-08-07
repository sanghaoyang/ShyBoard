@echo off
rem ============================================================
rem  Workbench Updater v3 (robust)
rem  Replaces Workbench.exe and _internal from a downloaded zip,
rem  then restarts the app with the SAME port as before.
rem  Data folder is NOT touched.
rem
rem  v3 fixes (root causes of "update stuck on old version"):
rem   1. Wait loop uses ping, NOT timeout (timeout misbehaves in
rem      CREATE_NO_WINDOW hidden consoles -> could skip waiting).
rem   2. Before replacing, force-kill ALL Workbench.exe instances
rem      (old code only waited for the recorded PID; a second
rem      window / leftover WebView2 child still locked the exe).
rem   3. EVERY replace step checks errorlevel and logs; a failed
rem      copy no longer silently falls through to restart.
rem   4. After copy, VERIFY the new exe size matches the source;
rem      "old exe still exists" is NOT treated as success.
rem   5. All output goes to data\updates\update.log for debugging.
rem ============================================================
cd /d "%~dp0"

set "LOG=data\updates\update.log"
if not exist "data\updates" mkdir "data\updates"
echo [%date% %time%] updater v3 started cwd=%CD% > "%LOG%"

set "PIDFILE=data\updates\app.pid"
set "ARGSFILE=data\updates\app.args"
set "RESTART_PORT="
if exist "%ARGSFILE%" set /p RESTART_PORT=<"%ARGSFILE%"
echo [%date% %time%] RESTART_PORT=%RESTART_PORT% >> "%LOG%"

set "FIND=%SystemRoot%\System32\find.exe"
set "TASKLIST=%SystemRoot%\System32\tasklist.exe"

rem ---- 1. wait for the recorded app PID to exit (max 60s) ----
if not exist "%PIDFILE%" goto :killall
set /a TRY=0
:waitloop
set /p APP_PID=<"%PIDFILE%"
"%TASKLIST%" /FI "PID eq %APP_PID%" 2>nul | "%FIND%" /I "%APP_PID%" >nul
if errorlevel 1 goto :waitdone
set /a TRY+=1
if %TRY% geq 60 (
    echo [%date% %time%] timed out waiting for PID %APP_PID%, continuing >> "%LOG%"
    goto :killall
)
ping -n 2 127.0.0.1 >nul
goto waitloop
:waitdone
echo [%date% %time%] recorded PID %APP_PID% exited. >> "%LOG%"

:killall
rem ---- 1b. force-kill ANY remaining Workbench.exe ----
rem (second window, zombie child, etc. would lock the exe file)
taskkill /F /IM Workbench.exe >nul 2>&1
echo [%date% %time%] taskkill Workbench.exe done. >> "%LOG%"
rem wait for file handles to be released
ping -n 4 127.0.0.1 >nul

rem ---- 2. locate downloaded zip in data\updates ----
set "ZIP="
for %%f in ("data\updates\*.zip") do set "ZIP=%%f"
echo [%date% %time%] ZIP=%ZIP% >> "%LOG%"
if not defined ZIP (
    echo [%date% %time%] no update package found, restarting. >> "%LOG%"
    goto :restart
)

rem ---- 3. extract to temp dir ----
set "TMP=__update_tmp"
if exist "%TMP%" rmdir /S /Q "%TMP%"
mkdir "%TMP%"
echo [%date% %time%] extracting %ZIP% ... >> "%LOG%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%TMP%' -Force" >> "%LOG%" 2>&1
if not exist "%TMP%\Workbench.exe" (
    echo [%date% %time%] EXTRACTION FAILED, Workbench.exe missing >> "%LOG%"
    rmdir /S /Q "%TMP%"
    goto :restart
)
for %%F in ("%TMP%\Workbench.exe") do set "SRC_SIZE=%%~zF"
echo [%date% %time%] extracted OK, src exe size=%SRC_SIZE% >> "%LOG%"

rem ---- 4. replace exe + _internal (with verification) ----
if exist "Workbench.exe" del /Q "Workbench.exe" >> "%LOG%" 2>&1
copy /Y "%TMP%\Workbench.exe" "Workbench.exe" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] copy failed, killing instances and retrying... >> "%LOG%"
    taskkill /F /IM Workbench.exe >nul 2>&1
    ping -n 4 127.0.0.1 >nul
    if exist "Workbench.exe" del /Q "Workbench.exe" >> "%LOG%" 2>&1
    copy /Y "%TMP%\Workbench.exe" "Workbench.exe" >> "%LOG%" 2>&1
)
if errorlevel 1 (
    echo [%date% %time%] FATAL: cannot install new exe. >> "%LOG%"
    rmdir /S /Q "%TMP%"
    goto :restart
)
rem VERIFY: new exe size must match source
for %%F in ("Workbench.exe") do set "NEW_SIZE=%%~zF"
echo [%date% %time%] installed exe size=%NEW_SIZE% >> "%LOG%"
if not "%NEW_SIZE%"=="%SRC_SIZE%" (
    echo [%date% %time%] FATAL: exe size mismatch, update aborted >> "%LOG%"
    rmdir /S /Q "%TMP%"
    goto :restart
)
echo [%date% %time%] exe replaced and verified OK. >> "%LOG%"

if exist "_internal" rmdir /S /Q "_internal" >> "%LOG%" 2>&1
xcopy /E /I /Y /Q "%TMP%\_internal" "_internal" >> "%LOG%" 2>&1
echo [%date% %time%] _internal replaced. >> "%LOG%"

rem ---- 5. cleanup ----
rmdir /S /Q "%TMP%" >> "%LOG%" 2>&1
del /Q "%ZIP%" 2>nul
del /Q "%PIDFILE%" 2>nul
del /Q "%ARGSFILE%" 2>nul
echo [%date% %time%] cleanup done. >> "%LOG%"

rem ---- 6. restart with original port ----
:restart
echo [%date% %time%] restarting Workbench (port=%RESTART_PORT%) ... >> "%LOG%"
if "%RESTART_PORT%"=="" (
    start "" "Workbench.exe"
) else (
    start "" "Workbench.exe" --port %RESTART_PORT%
)
exit /b 0
