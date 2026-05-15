' TB Personal Stock Guru - Dashboard Launcher (minimized)
'
' Runs launch_dashboard.bat minimized so no full window pops up.
' A "Stock Guru Server" entry appears in the taskbar while the server runs.
' Click it to see logs. Close it (or Ctrl+C) to stop the server.
'
' windowStyle 7 = minimized, not focused (window goes straight to taskbar)

Dim shell
Set shell = CreateObject("WScript.Shell")

Dim scriptDir
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

Dim batPath
batPath = scriptDir & "launch_dashboard.bat"

shell.Run Chr(34) & batPath & Chr(34), 7, False

Set shell = Nothing
