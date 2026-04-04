param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Task
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $scriptDir "query_hints.py") $Task
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $scriptDir "query_hints.py") $Task
    exit $LASTEXITCODE
}
& (Join-Path $scriptDir "bootstrap_env.ps1") ensure python
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $scriptDir "query_hints.py") $Task
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $scriptDir "query_hints.py") $Task
    exit $LASTEXITCODE
}
throw "Python 3 not found after bootstrap attempt."
