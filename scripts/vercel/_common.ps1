$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $PSCommandPath
$repoRoot = Resolve-Path (Join-Path $scriptRoot '..\..')
$frontendRoot = Join-Path $repoRoot 'webUI\tongstock-master\web'
$defaultEnvPath = Join-Path $scriptRoot '.env'
$exampleEnvPath = Join-Path $scriptRoot '.env.example'

function Import-EnvFile {
  param([string]$Path)
  if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
    return
  }
  foreach ($rawLine in Get-Content -LiteralPath $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#')) {
      continue
    }
    $parts = $line -split '=', 2
    if ($parts.Count -ne 2) {
      continue
    }
    $name = $parts[0].Trim()
    $value = $parts[1].Trim()
    if ([string]::IsNullOrWhiteSpace($name) -or [string]::IsNullOrWhiteSpace($value)) {
      continue
    }
    if (-not [string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable($name, 'Process'))) {
      continue
    }
    Set-Item -Path ("Env:{0}" -f $name) -Value $value
  }
}

function Initialize-VercelScriptEnv {
  Import-EnvFile -Path $defaultEnvPath
  Import-EnvFile -Path $exampleEnvPath
}

function Resolve-FrontendRoot {
  param([string]$ProjectDir = "")
  if (-not [string]::IsNullOrWhiteSpace($ProjectDir)) {
    return (Resolve-Path -LiteralPath $ProjectDir).Path
  }
  if (-not (Test-Path -LiteralPath $frontendRoot)) {
    throw "Frontend project not found: $frontendRoot"
  }
  return (Resolve-Path -LiteralPath $frontendRoot).Path
}

function Get-LocalVercelProjectLink {
  param([string]$RootDir)
  $projectJsonPath = Join-Path $RootDir '.vercel\project.json'
  if (Test-Path -LiteralPath $projectJsonPath) {
    try {
      return Get-Content -Raw -LiteralPath $projectJsonPath | ConvertFrom-Json
    } catch {
      throw "Unable to parse local Vercel project link: $projectJsonPath"
    }
  }

  $repoJsonPath = Join-Path $RootDir '.vercel\repo.json'
  if (Test-Path -LiteralPath $repoJsonPath) {
    try {
      $repo = Get-Content -Raw -LiteralPath $repoJsonPath | ConvertFrom-Json
      $project = @($repo.projects)[0]
      if ($null -ne $project) {
        return [PSCustomObject]@{
          projectId = [string]$project.id
          orgId = [string]$project.orgId
          projectName = [string]$project.name
        }
      }
    } catch {
      throw "Unable to parse local Vercel repo link: $repoJsonPath"
    }
  }

  return $null
}

function Assert-VercelProjectLink {
  param(
    [string]$RootDir,
    [string]$ExpectedProjectName = ""
  )
  $project = Get-LocalVercelProjectLink -RootDir $RootDir
  if ($null -eq $project) {
    throw "Local Vercel project link was not found. Run scripts\vercel\link_project.cmd first."
  }
  if (-not [string]::IsNullOrWhiteSpace($ExpectedProjectName) -and [string]$project.projectName -ne $ExpectedProjectName) {
    throw "Vercel project mismatch. Expected '$ExpectedProjectName' but local link is '$($project.projectName)'."
  }
  return $project
}

function Invoke-VercelCli {
  param([string[]]$Arguments)
  if (Get-Command vercel -ErrorAction SilentlyContinue) {
    & vercel @Arguments
    return
  }
  if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw 'Vercel CLI not found and npx is unavailable. Install Node.js or Vercel CLI first.'
  }
  & npx --yes vercel@latest @Arguments
}

function Read-KeyValueFile {
  param([string]$Path)
  $entries = New-Object System.Collections.Generic.List[object]
  if (-not (Test-Path -LiteralPath $Path)) {
    return $entries
  }
  foreach ($rawLine in Get-Content -LiteralPath $Path) {
    if ($null -eq $rawLine) {
      continue
    }
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#')) {
      continue
    }
    $parts = $rawLine -split '=', 2
    if ($parts.Count -ne 2) {
      continue
    }
    $entries.Add([PSCustomObject]@{
      name = $parts[0].Trim()
      value = $parts[1]
    }) | Out-Null
  }
  return $entries
}
