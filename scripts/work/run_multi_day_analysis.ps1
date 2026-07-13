param(
    [ValidateSet("python", "rust", "rust_python")]
    [string]$Engine = "rust_python",
    [string]$OutputRoot = "C:\level-2-ana\output\multi_day",
    [switch]$NoProfile,
    [string]$PythonExe = "python",
    [string]$CargoExe = "cargo"
)

$ErrorActionPreference = "Stop"

$TradeDateCandidates = @(
    @{ TradeDate = "20260708"; Candidates = @("C:\level-2-ana\data\20260708\20260708", "C:\level-2-ana\data\20260708") },
    @{ TradeDate = "20260707"; Candidates = @("C:\level-2-ana\data\20260707\20260707", "C:\level-2-ana\data\20260707") },
    @{ TradeDate = "20260706"; Candidates = @("C:\level-2-ana\data\20260706\20260706", "C:\level-2-ana\data\20260706") },
    @{ TradeDate = "20260130"; Candidates = @("C:\level-2-ana\data\20260130\20260130", "C:\level-2-ana\data\20260130") },
    @{ TradeDate = "20260129"; Candidates = @("C:\level-2-ana\data\20260129\20260129", "C:\level-2-ana\data\20260129") }
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RunAna = Join-Path $ScriptDir "run_ana.ps1"

if (-not (Test-Path -LiteralPath $RunAna)) {
    throw "Cannot find run_ana.ps1: $RunAna"
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$engines = switch ($Engine) {
    "python" { @("python") }
    "rust" { @("rust") }
    default { @("rust", "python") }
}

foreach ($item in $TradeDateCandidates) {
    $tradeDate = $item.TradeDate
    $inputDir = $null
    foreach ($candidate in $item.Candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $inputDir = $candidate
            break
        }
    }

    if ([string]::IsNullOrWhiteSpace($inputDir)) {
        Write-Host "Skip $tradeDate : input directory not found"
        continue
    }

    foreach ($eng in $engines) {
        $baseOutputDir = Join-Path (Join-Path $OutputRoot $tradeDate) $eng
        New-Item -ItemType Directory -Force -Path $baseOutputDir | Out-Null

        Write-Host ""
        Write-Host "=== $tradeDate / $eng ==="

        $args = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $RunAna,
            "-Engine", $eng,
            "-TradeDate", $tradeDate,
            "-InputDir", $inputDir,
            "-OutputDir", $baseOutputDir,
            "-PythonExe", $PythonExe,
            "-CargoExe", $CargoExe
        )

        if ($NoProfile) {
            $args += "-NoProfile"
        }

        & powershell.exe @args
        if ($LASTEXITCODE -ne 0) {
            throw "Analysis failed for $tradeDate / $eng with exit code $LASTEXITCODE"
        }
    }
}
