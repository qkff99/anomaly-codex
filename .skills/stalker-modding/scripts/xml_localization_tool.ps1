param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsList
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $scriptDir "xml_localization_tool.py") @ArgsList
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $scriptDir "xml_localization_tool.py") @ArgsList
    exit $LASTEXITCODE
}
& (Join-Path $scriptDir "bootstrap_env.ps1") ensure python
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 (Join-Path $scriptDir "xml_localization_tool.py") @ArgsList
    exit $LASTEXITCODE
}
if (Get-Command python -ErrorAction SilentlyContinue) {
    & python (Join-Path $scriptDir "xml_localization_tool.py") @ArgsList
    exit $LASTEXITCODE
}
throw "Python 3 not found after bootstrap attempt."
