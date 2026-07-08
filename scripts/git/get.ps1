param(
    [switch]$Rebase,
    [switch]$AllowDirty
)

# =============================================================================
# Config
# =============================================================================
$script:RepoRootOverride = ""
$script:RepoSshUrl = ""
$script:RepoHttpsUrl = ""
$script:PreferredRemoteUrl = ""

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-EnvFileValues {
    param(
        [string]$EnvPath
    )

    $values = @{}
    if (-not (Test-Path $EnvPath)) {
        return $values
    }

    foreach ($line in Get-Content -Path $EnvPath -ErrorAction SilentlyContinue) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        if ($trimmed -match '^(?<key>[^=]+?)\s*=\s*(?<value>.*)$') {
            $key = $Matches['key'].Trim()
            $value = $Matches['value'].Trim()
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $values[$key] = $value
        }
    }

    return $values
}

function Load-RepoUrlsFromEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $envPaths = @(
        (Join-Path $PSScriptRoot ".env"),
        (Join-Path $RepoRoot ".env")
    )

    foreach ($envPath in $envPaths | Select-Object -Unique) {
        if (-not (Test-Path $envPath)) {
            continue
        }

        $envValues = Get-EnvFileValues -EnvPath $envPath
        if ($envValues.ContainsKey("REPO_ROOT_OVERRIDE")) {
            $script:RepoRootOverride = $envValues["REPO_ROOT_OVERRIDE"]
        }
        if ($envValues.ContainsKey("REPO_SSH_URL")) {
            $script:RepoSshUrl = $envValues["REPO_SSH_URL"]
        }
        if ($envValues.ContainsKey("REPO_HTTPS_URL")) {
            $script:RepoHttpsUrl = $envValues["REPO_HTTPS_URL"]
        }
        if ($envValues.ContainsKey("PREFERRED_REMOTE_URL")) {
            $script:PreferredRemoteUrl = $envValues["PREFERRED_REMOTE_URL"]
        }
    }
}

# =============================================================================
# Helpers
# =============================================================================
function Resolve-RepoRoot {
    if ($RepoRootOverride) {
        if (-not (Test-Path $RepoRootOverride)) {
            throw "Configured RepoRootOverride does not exist: $RepoRootOverride"
        }
        return $RepoRootOverride
    }

    $defaultRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    if ($defaultRoot -and (Test-Path (Join-Path $defaultRoot ".git"))) {
        return $defaultRoot
    }

    throw "Could not find a .git directory at the workspace root. Set `$RepoRootOverride or initialize a repository in the skill root first."
}

function Ensure-OriginRemote {
    if (-not $PreferredRemoteUrl) {
        $PreferredRemoteUrl = (git remote get-url origin 2>$null).Trim()
    }
    if (-not $PreferredRemoteUrl) {
        throw "No remote URL configured. Set PREFERRED_REMOTE_URL in scripts/git/.env or configure git origin first."
    }

    $remoteNames = @(git remote)
    $hasOrigin = $remoteNames -contains "origin"

    if ($hasOrigin) {
        git remote set-url origin $PreferredRemoteUrl
        git remote set-url --push origin $PreferredRemoteUrl
        Write-Host "Updated origin -> $PreferredRemoteUrl" -ForegroundColor Cyan
    } else {
        git remote add origin $PreferredRemoteUrl
        Write-Host "Added origin -> $PreferredRemoteUrl" -ForegroundColor Cyan
    }
}

# =============================================================================
# Main
# =============================================================================
$root = Resolve-RepoRoot
$root = [System.IO.Path]::GetFullPath($root)
Load-RepoUrlsFromEnv -RepoRoot $root
Set-Location $root
Ensure-OriginRemote

$branch = (git branch --show-current).Trim()
if (-not $branch) {
    throw "Detached HEAD detected. Cannot auto-pull."
}

$status = git status --porcelain
if ($status -and -not $AllowDirty) {
    throw "Working tree is dirty. Commit/stash changes first, or rerun with -AllowDirty."
}

if ($Rebase) {
    git pull --rebase origin $branch
} else {
    git pull --ff-only origin $branch
}

Write-Host "Updated branch $branch" -ForegroundColor Green
