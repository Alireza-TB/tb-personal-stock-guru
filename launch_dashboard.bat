@echo off
:: TB Personal Stock Guru - Dashboard Launcher
:: Starts the Streamlit server, polls until it responds 200, then opens
:: the browser. Ctrl+C in this window stops the server.

cd /d "%~dp0"

echo ============================================================
echo  TB Personal Stock Guru
echo ============================================================
echo  Starting Streamlit server...
echo  URL : http://localhost:8501
echo  Stop: Ctrl+C in this window
echo ============================================================
echo.

:: Use the full path to uv so this works when launched via wscript.exe
:: (which runs with a minimal system PATH that excludes user-local installs).
set UV=%USERPROFILE%\.local\bin\uv.exe
if not exist "%UV%" (
    echo  ERROR: uv not found at %UV%
    echo  Try running launch_dashboard.bat from a terminal instead.
    pause
    exit /b 1
)

:: Start Streamlit headless in the background.
:: --server.headless=true suppresses Streamlit's own browser-open attempt.
start "" /b "%UV%" run streamlit run ui/app.py --server.headless=true

:: -- Health-check poll ------------------------------------------
:: Poll every second until HTTP 200 or 15s elapsed.
:: PowerShell exits with the HTTP status code (200) on success, 0 on error.
set MAX_WAIT=15
set WAITED=0

:poll
powershell -NoProfile -Command ^
  "try{$r=Invoke-WebRequest -Uri 'http://localhost:8501' -TimeoutSec 1 -UseBasicParsing -EA Stop;exit $r.StatusCode}catch{exit 0}" ^
  >nul 2>&1

if %ERRORLEVEL% equ 200 goto ready

set /a WAITED+=1
if %WAITED% geq %MAX_WAIT% (
    echo  WARNING: server did not respond after %MAX_WAIT%s - opening browser anyway.
    goto open_browser
)
ping -n 2 127.0.0.1 >nul 2>&1
goto poll

:ready
echo  Server ready ^(waited %WAITED%s^).

:open_browser
start "" http://localhost:8501

echo.
echo  Dashboard open. Press Ctrl+C to stop the server.
echo.

:: Keep the window alive so logs stream and Ctrl+C propagates to uv/streamlit.
:loop
ping -n 61 127.0.0.1 >nul 2>&1
goto loop
