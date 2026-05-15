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

:: Poll using curl (built into Windows 10/11).
:: curl starts instantly — no 2-3s PowerShell startup overhead per iteration.
:: --max-time 2 handles IPv6-first dual-stack without false timeouts.
:: Each iteration is ~2s worst-case; 150 iterations = 5 minutes maximum wait.
set MAX=150
set W=0

:poll
set STATUS=000
for /f %%s in ('curl -s -o nul -w "%%{http_code}" --max-time 2 http://localhost:8501 2^>nul') do set STATUS=%%s
if "%STATUS%"=="200" goto ready
set /a W+=1
if %W% geq %MAX% (
    echo  WARNING: still not up after %MAX% attempts - opening browser anyway.
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
