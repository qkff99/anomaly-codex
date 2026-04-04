param(
    [Parameter(Position = 0)]
    [string]$Path = ".codex-stalker/workspace.json"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $scriptDir "check_overlay.py") $Path
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $scriptDir "check_overlay.py") $Path
    exit $LASTEXITCODE
}
& (Join-Path $scriptDir "bootstrap_env.ps1") ensure python
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $scriptDir "check_overlay.py") $Path
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $scriptDir "check_overlay.py") $Path
    exit $LASTEXITCODE
}
throw "Python 3 not found after bootstrap attempt."
