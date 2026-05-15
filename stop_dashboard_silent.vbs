' TB's Personal Stock Guru — Silent Dashboard Stopper
' Runs stop_dashboard.bat with no visible terminal window.

Dim shell
Set shell = CreateObject("WScript.Shell")

Dim scriptDir
scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))

Dim batPath
batPath = scriptDir & "stop_dashboard.bat"

' windowStyle 0 = hidden window; bWaitOnReturn = False (fire and forget)
shell.Run Chr(34) & batPath & Chr(34), 0, False

Set shell = Nothing
