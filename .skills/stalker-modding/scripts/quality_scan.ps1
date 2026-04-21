param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Subcommand,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$arguments = @((Join-Path $scriptDir "quality_scan.py"), $Subcommand) + $RemainingArgs

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
