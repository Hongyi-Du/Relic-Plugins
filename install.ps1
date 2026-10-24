param(
    [ValidateSet('claude','codex','bridge')][string]$Edition,
    [ValidateSet('claude','codex','both')][string]$HostTarget,
    [switch]$ConfigureOnly
)
$ErrorActionPreference = 'Stop'
$taskPython = Get-Command python -ErrorAction Stop
$taskArgs = @('-X', 'utf8', (Join-Path $PSScriptRoot 'scripts/install.py'))
if ($Edition) { $taskArgs += @('--edition', $Edition) }
if ($HostTarget) { $taskArgs += @('--host', $HostTarget) }
if ($ConfigureOnly) { $taskArgs += '--configure-only' }
& $taskPython.Source @taskArgs
if ($LASTEXITCODE -ne 0) { throw "Relic installation failed (exit $LASTEXITCODE). See the error above." }
