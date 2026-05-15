# TB Personal Stock Guru - Desktop Shortcut Creator
#
# Creates a proper .lnk on the Desktop that launches the dashboard.
# Double-clicking opens the browser automatically; the server runs
# minimized in the taskbar (click it to see logs, close it to stop).
#
# Usage (run once from the project root):
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1

$projectRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$vbsPath      = Join-Path $projectRoot "launch_dashboard_silent.vbs"
$desktopPath  = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Stock Guru.lnk"

# shell32.dll index 277: bar-chart icon
$iconPath  = "$env:SystemRoot\System32\shell32.dll"
$iconIndex = 277

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)

# wscript.exe runs the VBS with no console of its own.
# The VBS then launches the bat minimized (windowStyle 7).
$shortcut.TargetPath       = "$env:SystemRoot\System32\wscript.exe"
$shortcut.Arguments        = "`"$vbsPath`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description      = "Stock Guru Dashboard"
$shortcut.IconLocation     = "$iconPath,$iconIndex"
$shortcut.Save()

Write-Host ""
Write-Host "  Shortcut created : $shortcutPath"
Write-Host ""
Write-Host "  Double-click 'Stock Guru' on your Desktop to launch."
Write-Host "  The browser opens automatically. The server runs minimized"
Write-Host "  in the taskbar -- click it to see logs, close it to stop."
Write-Host ""
Write-Host "  To pin to taskbar:"
Write-Host "    Right-click 'Stock Guru' on your Desktop -> Pin to taskbar"
Write-Host ""
