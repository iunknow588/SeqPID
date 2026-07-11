param(
    [string]$TradeDate = "",
    [string]$InputDir = "",
    [string]$OutputDir = "C:\level-2-ana\output",
    [string]$StockListFile = "",
    [int]$StockLimit = 0,
    [int]$StockOffset = 0,
    [switch]$NoProfile,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

function Resolve-TradeDateFromPath {
    param([string]$PathText)
    $matches = [regex]::Matches($PathText, "(20\d{6})")
    if ($matches.Count -gt 0) {
        return $matches[$matches.Count - 1].Value
    }
    return ""
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $ScriptDir
$AutomationRoot = Split-Path -Parent $ScriptsDir
$SystemDir = Get-ChildItem -LiteralPath $AutomationRoot -Directory |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName "main.py")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "configs")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "src"))
    } |
    Select-Object -First 1 -ExpandProperty FullName

if ([string]::IsNullOrWhiteSpace($SystemDir)) {
    throw "Cannot find competition system directory under: $AutomationRoot"
}

$MainPy = Join-Path $SystemDir "main.py"

if (-not (Test-Path -LiteralPath $MainPy)) {
    throw "Cannot find competition entrypoint: $MainPy"
}

if ([string]::IsNullOrWhiteSpace($TradeDate) -and -not [string]::IsNullOrWhiteSpace($InputDir)) {
    $TradeDate = Resolve-TradeDateFromPath -PathText $InputDir
}

if ([string]::IsNullOrWhiteSpace($TradeDate)) {
    throw "TradeDate is required. Example: .\run_level2_analysis.ps1 -TradeDate 20260707"
}

if ([string]::IsNullOrWhiteSpace($InputDir)) {
    $InputDir = Join-Path (Join-Path "C:\level-2-ana\data" $TradeDate) $TradeDate
}

if (-not (Test-Path -LiteralPath $InputDir)) {
    throw "InputDir does not exist: $InputDir"
}

if (-not [string]::IsNullOrWhiteSpace($StockListFile) -and -not (Test-Path -LiteralPath $StockListFile)) {
    throw "StockListFile does not exist: $StockListFile"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$arguments = @(
    $MainPy,
    "--mode", "batch",
    "--date", $TradeDate,
    "--input-dir", $InputDir,
    "--output-dir", $OutputDir
)

if (-not [string]::IsNullOrWhiteSpace($StockListFile)) {
    $arguments += @("--stock-list-file", $StockListFile)
}

if ($StockLimit -gt 0) {
    $arguments += @("--stock-limit", [string]$StockLimit)
}

if ($StockOffset -gt 0) {
    $arguments += @("--stock-offset", [string]$StockOffset)
}

$arguments += "--build-zip"

if (-not $NoProfile) {
    $arguments += "--profile"
}

Write-Host "Competition system : $SystemDir"
Write-Host "Trade date         : $TradeDate"
Write-Host "Input directory    : $InputDir"
Write-Host "Output base        : $OutputDir"
if ([string]::IsNullOrWhiteSpace($StockListFile)) {
    Write-Host "Stock list         : auto"
}
else {
    Write-Host "Stock list         : $StockListFile"
}
Write-Host ""

Push-Location $SystemDir
try {
    & $PythonExe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Analysis failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
