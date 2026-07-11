param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $ScriptDir
$AutomationRoot = Split-Path -Parent $ScriptsDir
$SystemDir = Get-ChildItem -LiteralPath $AutomationRoot -Directory |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName "analysis_gui.py")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "main.py")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "src"))
    } |
    Select-Object -First 1 -ExpandProperty FullName

if ([string]::IsNullOrWhiteSpace($SystemDir)) {
    throw "Cannot find competition system GUI under: $AutomationRoot"
}

Push-Location $SystemDir
try {
    & $PythonExe "analysis_gui.py"
    if ($LASTEXITCODE -ne 0) {
        throw "GUI exited with code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
