# TB's Personal Stock Guru — Desktop Shortcut Creator
#
# Creates a proper .lnk file on the Desktop so the launcher can be
# pinned to the taskbar cleanly (VBS files cannot be pinned directly).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1

$projectRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
$vbsPath      = Join-Path $projectRoot "launch_dashboard_silent.vbs"
$desktopPath  = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Stock Guru.lnk"

# shell32.dll index 277 is a bar-chart / graph icon
$iconPath  = "C:\Windows\System32\shell32.dll"
$iconIndex = 277

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)

# wscript.exe is the target so Windows treats this as a real executable
# shortcut (pinnable, icon-able) rather than a raw script file.
$shortcut.TargetPath       = "$env:SystemRoot\System32\wscript.exe"
$shortcut.Arguments        = "`"$vbsPath`""
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description      = "Stock Guru Dashboard"
$shortcut.IconLocation     = "$iconPath,$iconIndex"
$shortcut.Save()

Write-Host ""
Write-Host "  Shortcut created: $shortcutPath"
Write-Host ""
Write-Host "  To pin to taskbar:"
Write-Host "    Right-click 'Stock Guru' on your Desktop -> Pin to taskbar"
Write-Host ""
