param(
    [ValidateSet('auto','claude','codex','both','none')][string]$HostTarget = 'auto',
    [switch]$ConfigureOnly,
    [switch]$NoShortcut,
    [switch]$Open
)
$ErrorActionPreference = 'Stop'
$taskPython = Get-Command python -ErrorAction Stop
$taskArgs = @('-X', 'utf8', (Join-Path $PSScriptRoot 'scripts/install.py'), '--host', $HostTarget)
if ($ConfigureOnly) { $taskArgs += '--configure-only' }
if ($NoShortcut) { $taskArgs += '--no-shortcut' }
if ($Open) { $taskArgs += '--open' }
& $taskPython.Source @taskArgs
if ($LASTEXITCODE -ne 0) { throw "Relic installation failed (exit $LASTEXITCODE). See the error above." }
