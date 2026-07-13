param(
    [ValidateSet("rust", "python", "rust_python")]
    [string]$Engine = "python",
    [string]$TradeDate = "",
    [string]$InputDir = "",
    [string]$OutputDir = "C:\level-2-ana\output",
    [string]$StockListFile = "",
    [int]$StockLimit = 0,
    [int]$StockOffset = 0,
    [switch]$NoProfile,
    [switch]$DryRun,
    [string]$PythonExe = "python",
    [string]$CargoExe = "cargo",
    [string]$Config = ".\configs\dev.yaml",
    [string]$LabelConfig = ".\configs\label_dict.yaml"
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

function Resolve-LatestTradeDate {
    param([string]$DataRoot)

    if (-not (Test-Path -LiteralPath $DataRoot)) {
        return ""
    }

    $latest = Get-ChildItem -LiteralPath $DataRoot -Directory |
        Where-Object { $_.Name -match "^20\d{6}$" } |
        Sort-Object -Property Name -Descending |
        Select-Object -First 1 -ExpandProperty Name

    if ([string]::IsNullOrWhiteSpace($latest)) {
        return ""
    }
    return $latest
}

function Add-CommonArguments {
    param([string[]]$Arguments)

    $args = $Arguments + @(
        "--mode", "batch",
        "--date", $TradeDate,
        "--input-dir", $InputDir,
        "--output-dir", $OutputDir,
        "--config", $Config,
        "--label-config", $LabelConfig
    )

    if (-not [string]::IsNullOrWhiteSpace($StockListFile)) {
        $args += @("--stock-list-file", $StockListFile)
    }

    if ($StockLimit -gt 0) {
        $args += @("--stock-limit", [string]$StockLimit)
    }

    if ($StockOffset -gt 0) {
        $args += @("--stock-offset", [string]$StockOffset)
    }

    $args += "--build-zip"

    if (-not $NoProfile) {
        $args += "--profile"
    }

    return $args
}

function Show-RunInfo {
    param(
        [string]$Name,
        [string]$WorkDir
    )

    Write-Host "Analysis engine    : $Name"
    Write-Host "Work directory     : $WorkDir"
    Write-Host "Trade date         : $TradeDate"
    Write-Host "Input directory    : $InputDir"
    Write-Host "Output base        : $OutputDir"
    Write-Host "Runtime config     : $Config"
    Write-Host "Label config       : $LabelConfig"
    if ([string]::IsNullOrWhiteSpace($StockListFile)) {
        Write-Host "Stock list         : auto"
    }
    else {
        Write-Host "Stock list         : $StockListFile"
    }
    Write-Host ""
}

function Invoke-PythonAnalysis {
    $mainPy = Join-Path $PythonDir "main.py"
    if (-not (Test-Path -LiteralPath $mainPy)) {
        throw "Cannot find Python entrypoint: $mainPy"
    }

    Show-RunInfo -Name "python" -WorkDir $PythonDir
    $arguments = Add-CommonArguments -Arguments @($mainPy)

    if ($DryRun) {
        Write-Host "Command           : $PythonExe $($arguments -join ' ')"
        return
    }

    Push-Location $PythonDir
    try {
        & $PythonExe @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Python analysis failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-RustAnalysis {
    $cargoToml = Join-Path $RustDir "Cargo.toml"
    if (-not (Test-Path -LiteralPath $cargoToml)) {
        throw "Cannot find Rust Cargo.toml: $cargoToml"
    }

    Show-RunInfo -Name "rust" -WorkDir $RustDir
    $arguments = @("run", "--release", "--") + (Add-CommonArguments -Arguments @())

    if ($DryRun) {
        Write-Host "Command           : $CargoExe $($arguments -join ' ')"
        return
    }

    Push-Location $RustDir
    try {
        & $CargoExe @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Rust analysis failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $ScriptDir
$AutomationRoot = Split-Path -Parent $ScriptsDir
$RustDir = Join-Path $AutomationRoot "src-rust"
$PythonDir = Get-ChildItem -LiteralPath $AutomationRoot -Directory |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName "main.py")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "configs")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "src"))
    } |
    Select-Object -First 1 -ExpandProperty FullName

if (-not (Test-Path -LiteralPath $RustDir)) {
    throw "Cannot find Rust system directory: $RustDir"
}

if ([string]::IsNullOrWhiteSpace($PythonDir) -or -not (Test-Path -LiteralPath $PythonDir)) {
    throw "Cannot find Python system directory: $PythonDir"
}

if ([string]::IsNullOrWhiteSpace($TradeDate) -and -not [string]::IsNullOrWhiteSpace($InputDir)) {
    $TradeDate = Resolve-TradeDateFromPath -PathText $InputDir
}

if ([string]::IsNullOrWhiteSpace($TradeDate)) {
    $TradeDate = Resolve-LatestTradeDate -DataRoot "C:\level-2-ana\data"
}

if ([string]::IsNullOrWhiteSpace($TradeDate)) {
    throw "Cannot infer TradeDate. Pass -TradeDate 20260707 or put date folders under C:\level-2-ana\data."
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

switch ($Engine) {
    "rust" {
        Invoke-RustAnalysis
    }
    "python" {
        Invoke-PythonAnalysis
    }
    "rust_python" {
        Invoke-RustAnalysis
        Invoke-PythonAnalysis
    }
}
