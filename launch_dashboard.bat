@echo off
:: TB Personal Stock Guru - Dashboard Launcher
:: Starts Streamlit, waits until it responds, then opens the browser.
:: This window stays open as the server — minimize it, or Ctrl+C to stop.

title Stock Guru Server
cd /d "%~dp0"

set UV=%USERPROFILE%\.local\bin\uv.exe

echo ============================================================
echo  TB Personal Stock Guru
echo ============================================================
echo  URL : http://localhost:8501
echo  Stop: close this window or press Ctrl+C
echo ============================================================
echo.

if not exist "%UV%" (
    echo  ERROR: uv not found at %UV%
    pause
    exit /b 1
)

:: Start Streamlit in a new detached window so it survives if this bat exits.
:: /min = minimized, title "Streamlit" helps identify it in task manager.
start "Streamlit" /min "%UV%" run streamlit run ui/app.py --server.headless=true

echo  Waiting for server...

:: Poll every second for up to 90s
set MAX=90
set W=0

:poll
powershell -NoProfile -Command "try{$r=Invoke-WebRequest 'http://localhost:8501' -TimeoutSec 1 -UseBasicParsing -EA Stop;exit $r.StatusCode}catch{exit 0}" >nul 2>&1
if %ERRORLEVEL% equ 200 goto ready
set /a W+=1
if %W% geq %MAX% (
    echo  WARNING: still not up after %MAX%s - opening browser anyway.
    goto open
)
ping -n 2 127.0.0.1 >nul 2>&1
goto poll

:ready
echo  Server ready after %W%s.

:open
start "" http://localhost:8501
echo.
echo  Dashboard is open. Minimize this window to keep the server running.
echo  Close this window or press Ctrl+C to stop.
echo.

:loop
ping -n 61 127.0.0.1 >nul 2>&1
goto loop
