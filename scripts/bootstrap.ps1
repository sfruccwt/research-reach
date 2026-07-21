param(
    [string]$Python,
    [string]$CodexHome = (Join-Path $HOME '.codex')
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Python) {
    $ManagedPython = Join-Path $HOME '.agent-reach-venv\Scripts\python.exe'
    $Python = if (Test-Path -LiteralPath $ManagedPython) { $ManagedPython } else { (Get-Command python).Source }
}

& $Python -m pip install --no-deps --upgrade --force-reinstall $RepoRoot
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }

$SkillNames = @('research-reach-opening', 'research-reach-search', 'research-reach-synthesis')
$SourceRoot = Join-Path $RepoRoot 'skills'
$TargetRoot = Join-Path $CodexHome 'skills'
$Validator = Join-Path $TargetRoot '.system\skill-creator\scripts\quick_validate.py'

foreach ($Name in $SkillNames) {
    $Source = Join-Path $SourceRoot $Name
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw "Missing source skill: $Name" }
    if (Test-Path -LiteralPath $Validator -PathType Leaf) {
        & $Python $Validator $Source
        if ($LASTEXITCODE -ne 0) { throw "Skill validation failed: $Name" }
    }
}

New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
$StagingRoot = Join-Path $TargetRoot ('.research-reach-install-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $StagingRoot | Out-Null
try {
    foreach ($Name in $SkillNames) {
        Copy-Item -LiteralPath (Join-Path $SourceRoot $Name) -Destination (Join-Path $StagingRoot $Name) -Recurse
    }
    foreach ($Name in $SkillNames) {
        $Target = Join-Path $TargetRoot $Name
        if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
        Move-Item -LiteralPath (Join-Path $StagingRoot $Name) -Destination $Target
    }
    $Legacy = Join-Path $TargetRoot 'research-reach'
    if (Test-Path -LiteralPath $Legacy) { Remove-Item -LiteralPath $Legacy -Recurse -Force }
}
finally {
    if (Test-Path -LiteralPath $StagingRoot) { Remove-Item -LiteralPath $StagingRoot -Recurse -Force }
}

Write-Host 'Installed Research Reach CLI and three Companion Skills.'
