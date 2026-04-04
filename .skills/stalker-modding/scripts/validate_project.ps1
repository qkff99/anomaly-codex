param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $scriptDir "bootstrap_env.ps1") ensure python luac
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $scriptDir "validate_project.py") @Args
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $scriptDir "validate_project.py") @Args
    exit $LASTEXITCODE
}
throw "Python 3 not found after bootstrap attempt."
