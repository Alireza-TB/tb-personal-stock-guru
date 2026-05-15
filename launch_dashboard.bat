@echo off
:: TB's Personal Stock Guru — Dashboard Launcher
:: Starts the Streamlit server and opens the browser.
:: Ctrl+C in this window stops the server.

cd /d "%~dp0"

echo ============================================================
echo  TB's Personal Stock Guru
echo ============================================================
echo  Starting Streamlit server...
echo  URL : http://localhost:8501
echo  Stop: Ctrl+C in this window
echo ============================================================
echo.

:: Start Streamlit in the foreground (keeps this window alive for logs)
:: --server.headless=true suppresses Streamlit's own browser-open attempt
start "" /b uv run streamlit run ui/app.py --server.headless=true

:: Give the server a few seconds to bind the port
timeout /t 4 /nobreak >nul

:: Open the dashboard in the default browser
start "" http://localhost:8501

:: Keep the window open so logs are visible and Ctrl+C works
echo  Dashboard open. Press Ctrl+C to stop the server.
echo.

:: Wait indefinitely — the uv/streamlit process is a child of this shell,
:: so Ctrl+C here will propagate and kill it.
:loop
timeout /t 60 /nobreak >nul
goto loop
