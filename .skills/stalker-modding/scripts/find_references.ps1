param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Pattern,
    [string]$Task = "tutorial",
    [string[]]$Root = @(),
    [int]$MaxCount = 50
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$arguments = @((Join-Path $scriptDir "find_references.py"), "--task", $Task, "--max-count", $MaxCount.ToString())
foreach ($item in $Root) {
    $arguments += @("--root", $item)
}
$arguments += $Pattern

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @arguments
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python @arguments
    exit $LASTEXITCODE
}
& (Join-Path $scriptDir "bootstrap_env.ps1") ensure python
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 @arguments
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python @arguments
    exit $LASTEXITCODE
}
throw "Python 3 not found after bootstrap attempt."
