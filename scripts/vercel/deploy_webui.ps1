param(
  [string]$ProjectDir = "",
  [string]$EnvFile = "",
  [string]$VercelToken = "",
  [string]$VercelCustomDomain = "",
  [string]$ApiBaseUrl = "",
  [switch]$Prod,
  [switch]$Build,
  [switch]$SyncEnv,
  [switch]$AutoLink,
  [switch]$Execute,
  [switch]$Smoke,
  [switch]$SmokeApi,
  [int]$DeployRetries = 2
)

$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot '_common.ps1')
Initialize-VercelScriptEnv

function Invoke-Preflight {
  param(
    [string]$FrontendRoot,
    [switch]$SkipLinkCheck
  )

  $rows = New-Object System.Collections.Generic.List[object]

  function Add-Check {
    param([string]$Name, [bool]$Ok, [string]$Value = '')
    $rows.Add([PSCustomObject]@{
      check = $Name
      status = if ($Ok) { 'ok' } else { 'failed' }
      value = $Value
    }) | Out-Null
  }

  Add-Check -Name 'dir:frontend-root' -Ok (Test-Path -LiteralPath $FrontendRoot) -Value $FrontendRoot
  Add-Check -Name 'file:package.json' -Ok (Test-Path -LiteralPath (Join-Path $FrontendRoot 'package.json')) -Value (Join-Path $FrontendRoot 'package.json')
  Add-Check -Name 'file:vercel.json' -Ok (Test-Path -LiteralPath (Join-Path $FrontendRoot 'vercel.json')) -Value (Join-Path $FrontendRoot 'vercel.json')
  Add-Check -Name 'file:env.example' -Ok (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env.example')) -Value (Join-Path $PSScriptRoot '.env.example')
  $hasNode = [bool](Get-Command node -ErrorAction SilentlyContinue)
  $hasNpm = [bool](Get-Command npm -ErrorAction SilentlyContinue)
  $hasVercelCli = [bool](Get-Command vercel -ErrorAction SilentlyContinue)
  $hasNpx = [bool](Get-Command npx -ErrorAction SilentlyContinue)
  $vercelSource = ''
  if ($hasVercelCli) {
    $vercelSource = 'vercel'
  } elseif ($hasNpx) {
    $vercelSource = 'npx fallback'
  }
  Add-Check -Name 'cmd:node' -Ok $hasNode
  Add-Check -Name 'cmd:npm' -Ok $hasNpm
  Add-Check -Name 'cmd:vercel-or-npx' -Ok ($hasVercelCli -or $hasNpx) -Value $vercelSource

  if (-not $SkipLinkCheck) {
    try {
      $project = Assert-VercelProjectLink -RootDir $FrontendRoot -ExpectedProjectName $env:VERCEL_PROJECT_NAME
      Add-Check -Name 'vercel:link' -Ok $true -Value $project.projectName
    } catch {
      Add-Check -Name 'vercel:link' -Ok $false -Value $_.Exception.Message
    }
  }

  $rows | Format-Table -AutoSize

  $failed = $rows | Where-Object { $_.status -ne 'ok' }
  if ($failed) {
    throw "Preflight failed: $($failed.Count) issue(s) need attention."
  }

  Write-Host 'Vercel preflight passed.' -ForegroundColor Green
}

function Invoke-LinkProject {
  param([string]$FrontendRoot)

  $projectName = $env:VERCEL_PROJECT_NAME
  $scope = $env:VERCEL_SCOPE
  $token = $env:VERCEL_TOKEN
  if ([string]::IsNullOrWhiteSpace($projectName)) {
    throw 'VERCEL_PROJECT_NAME is required. Set it in scripts/vercel/.env or pass it via environment.'
  }

  Push-Location $FrontendRoot
  try {
    $args = @('link', '--project', $projectName, '--yes')
    if (-not [string]::IsNullOrWhiteSpace($scope)) {
      $args += @('--scope', $scope)
    }
    if (-not [string]::IsNullOrWhiteSpace($token)) {
      $args += @('--token', $token)
    }
    Write-Host "[INFO] Linking Vercel project '$projectName' in $FrontendRoot" -ForegroundColor Green
    Invoke-VercelCli -Arguments $args
  } finally {
    Pop-Location
  }
}

function Invoke-SyncEnv {
  param(
    [string]$EnvFilePath,
    [string]$FrontendRoot,
    [string]$Token,
    [switch]$Execute
  )

  if (-not (Test-Path -LiteralPath $EnvFilePath)) {
    return
  }

  $entries = Read-KeyValueFile -Path $EnvFilePath
  if ($entries.Count -eq 0) {
    return
  }

  $project = Get-LocalVercelProjectLink -RootDir $FrontendRoot
  if ($Execute -and $null -eq $project) {
    throw 'Local Vercel project link was not found. Run deploy_webui.cmd -AutoLink first.'
  }

  $planDir = Join-Path $repoRoot '.temp\dist\vercel-env-sync'
  New-Item -ItemType Directory -Force -Path $planDir | Out-Null
  $planPath = Join-Path $planDir ("vercel-env-sync-plan-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
  [PSCustomObject]@{
    projectName = $env:VERCEL_PROJECT_NAME
    projectDir = $FrontendRoot
    envFilePath = (Resolve-Path -LiteralPath $EnvFilePath).Path
    execute = [bool]$Execute
    items = @(
      foreach ($entry in $entries) {
        [PSCustomObject]@{
          name = $entry.name
          valueLength = [string]$entry.value.Length
          action = 'add-or-update'
        }
      }
    )
  } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $planPath -Encoding UTF8

  if (-not $Execute) {
    Write-Output "Vercel env sync plan created."
    Write-Output "Plan: $planPath"
    return
  }

  if ([string]::IsNullOrWhiteSpace($Token)) {
    throw 'VERCEL_TOKEN is required to sync env vars.'
  }
  if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    throw 'Vercel CLI is required for env sync execution.'
  }

  Push-Location $FrontendRoot
  try {
    foreach ($entry in $entries) {
      foreach ($environment in @('preview', 'production')) {
        $tempFile = [System.IO.Path]::GetTempFileName()
        try {
          Set-Content -LiteralPath $tempFile -Value $entry.value -Encoding UTF8
          $command = "Get-Content -LiteralPath '$tempFile' -Raw | vercel env update $($entry.name) $environment --yes"
          if (-not [string]::IsNullOrWhiteSpace($env:VERCEL_SCOPE)) {
            $command += " --scope $env:VERCEL_SCOPE"
          }
          if (-not [string]::IsNullOrWhiteSpace($Token)) {
            $command += " --token $Token"
          }
          & powershell -NoProfile -Command $command
          if ($LASTEXITCODE -ne 0) {
            $command = "Get-Content -LiteralPath '$tempFile' -Raw | vercel env add $($entry.name) $environment --yes"
            & powershell -NoProfile -Command $command
          }
          if ($LASTEXITCODE -ne 0) {
            throw "Failed to sync $($entry.name) for environment '$environment'."
          }
        } finally {
          Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
        }
      }
    }
  } finally {
    Pop-Location
  }

  Write-Output "Vercel env sync completed."
  Write-Output "Plan: $planPath"
}

function Invoke-SmokeWebUi {
  param(
    [string]$BaseUrl,
    [string]$ApiBaseUrl = '',
    [bool]$ExpectApiJson = $false
  )

  function Invoke-SmokeRequest {
    param([string]$Url)
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30
    return [PSCustomObject]@{
      status = [int]$response.StatusCode
      contentType = [string]$response.Headers['Content-Type']
      body = [string]$response.Content
    }
  }

  $root = $BaseUrl.TrimEnd('/')
  $deep = '/stock/000001'
  $rootResult = Invoke-SmokeRequest -Url $root
  $deepResult = Invoke-SmokeRequest -Url ($root + $deep)
  Write-Output ("root: {0} {1}" -f $rootResult.status, $root)
  Write-Output ("deep: {0} {1}" -f $deepResult.status, ($root + $deep))
  if ($rootResult.status -ne 200) {
    throw "Root smoke check failed with status $($rootResult.status)."
  }
  if ($deepResult.status -ne 200) {
    throw "Deep route smoke check failed with status $($deepResult.status)."
  }
  if ($rootResult.contentType -notmatch 'text/html' -or $deepResult.contentType -notmatch 'text/html') {
    throw 'Smoke HTML response content type is not HTML.'
  }

  if (-not [string]::IsNullOrWhiteSpace($ApiBaseUrl)) {
    $apiRoot = $ApiBaseUrl.TrimEnd('/')
    $apiResult = Invoke-SmokeRequest -Url ($apiRoot + '/api/quote?code=000001')
    Write-Output ("api: {0} {1}" -f $apiResult.status, ($apiRoot + '/api/quote?code=000001'))
    if ($apiResult.status -ne 200) {
      throw "API smoke check failed with status $($apiResult.status)."
    }
    if ($ExpectApiJson -and $apiResult.contentType -notmatch 'application/json') {
      throw "API content type is not JSON: $($apiResult.contentType)"
    }
  }

  Write-Host 'WebUI smoke check passed.' -ForegroundColor Green
}

$frontend = Resolve-FrontendRoot -ProjectDir $ProjectDir
$projectName = $env:VERCEL_PROJECT_NAME
if ([string]::IsNullOrWhiteSpace($EnvFile)) {
  $EnvFile = Join-Path $PSScriptRoot '.env'
}
$token = if ([string]::IsNullOrWhiteSpace($VercelToken)) { $env:VERCEL_TOKEN } else { $VercelToken }
$scope = $env:VERCEL_SCOPE
$customDomain = if ([string]::IsNullOrWhiteSpace($VercelCustomDomain)) { $env:VERCEL_CUSTOM_DOMAIN } else { $VercelCustomDomain }
$apiBaseUrl = if ([string]::IsNullOrWhiteSpace($ApiBaseUrl)) { $env:VITE_API_BASE } else { $ApiBaseUrl }

if ($AutoLink) {
  Invoke-LinkProject -FrontendRoot $frontend
}

Invoke-Preflight -FrontendRoot $frontend -SkipLinkCheck:(!$Execute)

if ($SyncEnv) {
  Invoke-SyncEnv -EnvFilePath $EnvFile -FrontendRoot $frontend -Token $token -Execute:$Execute
}

$releasePlanDir = Join-Path $frontend '.temp\dist\vercel-release'
New-Item -ItemType Directory -Force -Path $releasePlanDir | Out-Null
$releasePlanPath = Join-Path $releasePlanDir ("deploy-webui-plan-{0}.json" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

$deployArgs = @('deploy', '--yes')
if ($Prod) {
  $deployArgs += '--prod'
}
if (-not [string]::IsNullOrWhiteSpace($token)) {
  $deployArgs += @('--token', $token)
}
if (-not [string]::IsNullOrWhiteSpace($scope)) {
  $deployArgs += @('--scope', $scope)
}

[PSCustomObject]@{
  projectName = $projectName
  projectDir = $frontend
  envFile = $EnvFile
  execute = [bool]$Execute
  prod = [bool]$Prod
  build = [bool]$Build
  syncEnv = [bool]$SyncEnv
  smoke = [bool]$Smoke
  smokeApi = [bool]$SmokeApi
  apiBaseUrl = $apiBaseUrl
  deployRetries = $DeployRetries
  command = @('vercel') + $deployArgs
  customDomain = $customDomain
  preparedAt = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $releasePlanPath -Encoding UTF8

if (-not $Execute) {
  Write-Output "Deployment plan created."
  Write-Output "Plan: $releasePlanPath"
  Write-Output "Re-run with -Execute to deploy."
  return
}

Push-Location $frontend
try {
  if ($Build) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
      throw 'npm was not found. Install Node.js first.'
    }
    npm run build
  }

  $attempts = [Math]::Max(1, $DeployRetries)
  $deployOutput = ''
  for ($i = 1; $i -le $attempts; $i++) {
    $out = Invoke-VercelCli -Arguments $deployArgs 2>&1
    $deployOutput = ($out | Out-String).Trim()
    if ($LASTEXITCODE -eq 0) {
      break
    }
    if ($i -lt $attempts) {
      Start-Sleep -Seconds (2 * $i)
    }
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Vercel deployment failed after $attempts attempt(s)."
  }

  $deploymentUrl = ''
  $matches = [regex]::Matches($deployOutput, 'https://[^\s]+\.vercel\.app')
  if ($matches.Count -gt 0) {
    $deploymentUrl = $matches[$matches.Count - 1].Value.Trim()
  }

  if ($Smoke -and -not [string]::IsNullOrWhiteSpace($deploymentUrl)) {
    try {
      Invoke-SmokeWebUi -BaseUrl $deploymentUrl -ApiBaseUrl $apiBaseUrl -ExpectApiJson:$SmokeApi
    } catch {
      Write-Warning "Smoke request failed: $($_.Exception.Message)"
    }
  }

  if (-not [string]::IsNullOrWhiteSpace($customDomain)) {
    Write-Output "Deployed site can be aliased to: $customDomain"
  }

  if (-not [string]::IsNullOrWhiteSpace($deploymentUrl)) {
    Write-Output "Deployment URL: $deploymentUrl"
  }
} finally {
  Pop-Location
}
