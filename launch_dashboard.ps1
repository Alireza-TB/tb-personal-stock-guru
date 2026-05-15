# TB Personal Stock Guru - Dashboard Launcher
# Starts Streamlit, polls until ready, opens the browser.
# Designed to run hidden via the desktop shortcut.
#
# If something goes wrong, check the log at:
#   %TEMP%\stock_guru_launch.log

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$UV          = "$env:USERPROFILE\.local\bin\uv.exe"

$LogFile = "$env:TEMP\stock_guru_launch.log"
function Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    "$ts  $msg" | Out-File -FilePath $LogFile -Append -Encoding UTF8
}

"" | Out-File -FilePath $LogFile -Encoding UTF8   # clear previous log
Log "Starting Stock Guru Dashboard"
Log "Project root : $ProjectRoot"
Log "uv path      : $UV"

# -- If port 8501 is already in use, just bring the browser to the front -----
$portBusy = (netstat -ano 2>$null | Select-String ":8501 .*LISTENING").Count -gt 0
if ($portBusy) {
    Log "Port 8501 already occupied - focusing existing server"
    Start-Process "http://localhost:8501"
    exit 0
}

# -- uv sanity check ---------------------------------------------------------
if (-not (Test-Path $UV)) {
    Log "ERROR: uv not found at $UV"
    exit 1
}

# -- Start Streamlit via WScript.Shell ---------------------------------------
# WScript.Shell.Run(cmd, 0, false) reliably spawns a hidden process from any
# context (hidden window, no console, scheduled task) — unlike Start-Process
# or [Diagnostics.Process]::Start which need an attached console for hidden
# child-process creation to work correctly.
Log "Launching Streamlit via WScript.Shell..."
$sh = New-Object -ComObject WScript.Shell
$sh.CurrentDirectory = $ProjectRoot
$cmd = "`"$UV`" run streamlit run ui/app.py --server.headless=true"
$sh.Run($cmd, 0, $false)   # windowStyle=0 (hidden), bWaitOnReturn=false
Log "Launch command sent"

# -- Poll until HTTP 200 or 90s elapsed --------------------------------------
# Cold-start (uv resolving venv + importing Python deps) takes 30-60s.
$maxWait = 90
$waited  = 0
$ready   = $false

Log "Polling http://localhost:8501 (max ${maxWait}s)..."

while ($waited -lt $maxWait) {
    Start-Sleep -Seconds 1
    $waited++
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8501" `
             -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) {
            Log "Server ready after ${waited}s"
            $ready = $true
            break
        }
    } catch { <# still starting #> }
}

if (-not $ready) {
    Log "WARNING: no response after ${maxWait}s - opening browser anyway"
}

# -- Open default browser ----------------------------------------------------
Log "Opening browser"
Start-Process "http://localhost:8501"
Log "Done"
