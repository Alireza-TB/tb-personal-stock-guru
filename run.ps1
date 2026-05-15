# Workaround for uv shim breakage on paths containing apostrophes.
# Usage: .\run.ps1 agents/test_graph.py
#        .\run.ps1 -m pytest tests/
param([Parameter(Mandatory=$true, ValueFromRemainingArguments=$true)][string[]]$Args)

$python = "$env:APPDATA\uv\python\cpython-3.12.11-windows-x86_64-none\python.exe"
$env:PYTHONPATH = (Resolve-Path ".venv\Lib\site-packages").Path

& $python @Args
