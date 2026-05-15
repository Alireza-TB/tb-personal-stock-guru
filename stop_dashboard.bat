@echo off
:: TB Personal Stock Guru - Dashboard Stopper
:: Finds the process on port 8501 and kills it.

echo ============================================================
echo  TB Personal Stock Guru - Stop Dashboard
echo ============================================================
echo.

:: Collect all PIDs listening on port 8501
set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501 " 2^>nul') do (
    if not "%%p"=="0" (
        set FOUND=1
        echo  Stopping PID %%p ...
        taskkill /PID %%p /F >nul 2>&1
    )
)

if "%FOUND%"=="0" (
    echo  Dashboard is not running on port 8501.
) else (
    echo  Done.
)

echo.
:: ping as a portable sleep - works in non-interactive contexts unlike timeout
ping -n 2 127.0.0.1 >nul 2>&1
