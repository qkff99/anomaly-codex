param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "ensure", "install-hints")]
    [string]$Command = "status",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
[string[]]$Tools = @("python")
)

function Get-LuacPath {
    if ($env:STALKER_LUAC) {
        $override = [Environment]::ExpandEnvironmentVariables($env:STALKER_LUAC)
        if (Test-Path -LiteralPath $override) {
            return (Resolve-Path -LiteralPath $override).Path
        }
    }

    foreach ($name in @("luac5.1", "luac", "lua5.1", "lua")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -eq $command) {
            continue
        }

        $path = $command.Source
        if (-not $path -and $command.Path) {
            $path = $command.Path
        }

        if ($path -and (Test-Path -LiteralPath $path)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }

    $search_paths = @()
    if ($env:ProgramFiles) {
        $search_paths += @(
            (Join-Path $env:ProgramFiles "Lua\5.1\bin\luac.exe"),
            (Join-Path $env:ProgramFiles "Lua\5.1\luac.exe"),
            (Join-Path $env:ProgramFiles "Lua\5.1\bin\lua.exe"),
            (Join-Path $env:ProgramFiles "Lua\5.1\lua.exe")
        )
    }
    if (${env:ProgramFiles(x86)}) {
        $search_paths += @(
            (Join-Path ${env:ProgramFiles(x86)} "Lua\5.1\bin\luac.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Lua\5.1\luac.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Lua\5.1\bin\lua.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Lua\5.1\lua.exe")
        )
    }
    $search_paths += @(
        "C:\Lua\5.1\bin\luac.exe",
        "C:\Lua\5.1\luac.exe",
        "C:\Lua\5.1\bin\lua.exe",
        "C:\Lua\5.1\lua.exe",
        (Join-Path $env:ProgramData "chocolatey\lib\lua51\tools\luac.exe"),
        (Join-Path $env:ProgramData "chocolatey\lib\lua51\tools\lua.exe"),
        (Join-Path $env:ProgramData "chocolatey\lib\lua\tools\luac.exe"),
        (Join-Path $env:ProgramData "chocolatey\lib\lua\tools\lua.exe")
    )

    foreach ($path in $search_paths) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return (Resolve-Path -LiteralPath $path).Path
        }
    }

    return $null
}

function Test-LuacCompatibility {
    param([string]$Path)

    if (-not $Path) {
        return $false
    }

    try {
        $output = & $Path -v 2>&1
    } catch {
        return $false
    }

    $text = ($output | Out-String).Trim()
    return [bool]($text -match "5\.1")
}

function Sync-LuacEnvironment {
    $path = Get-LuacPath
    if (-not $path) {
        return $false
    }

    $env:STALKER_LUAC = $path
    $dir = Split-Path -Parent $path
    if ($dir) {
        $escaped_dir = [Regex]::Escape($dir)
        if ($env:PATH -notmatch $escaped_dir) {
            $env:PATH = "$dir;$env:PATH"
        }
    }
    return $true
}

function Get-RgPath {
    if ($env:STALKER_RG) {
        $override = [Environment]::ExpandEnvironmentVariables($env:STALKER_RG)
        if (Test-Path -LiteralPath $override) {
            return (Resolve-Path -LiteralPath $override).Path
        }
    }

    $candidates = @()
    foreach ($command in Get-Command rg -All -ErrorAction SilentlyContinue) {
        $path = $command.Source
        if (-not $path -and $command.Path) {
            $path = $command.Path
        }
        if ($path) {
            $candidates += $path
        }
    }

    try {
        $where_hits = & where.exe rg 2>$null
        if ($where_hits) {
            $candidates += $where_hits
        }
    } catch {
    }

    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\rg.exe")
        $winget_packages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        if (Test-Path $winget_packages) {
            $candidates += Get-ChildItem -Path $winget_packages -Filter "rg.exe" -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
        }
    }

    if ($env:ProgramData) {
        $candidates += @(
            (Join-Path $env:ProgramData "chocolatey\bin\rg.exe"),
            (Join-Path $env:ProgramData "chocolatey\lib\ripgrep\tools\rg.exe"),
            (Join-Path $env:ProgramData "chocolatey\lib\ripgrep\tools\bin\rg.exe")
        )
    }

    foreach ($path in $candidates) {
        if (-not $path) {
            continue
        }

        if (Test-Path -LiteralPath $path) {
            $resolved = (Resolve-Path -LiteralPath $path).Path
            if (Test-RgCompatibility $resolved) {
                return $resolved
            }
        }
    }

    return $null
}

function Test-RgCompatibility {
    param([string]$Path)

    if (-not $Path) {
        return $false
    }

    try {
        $output = & $Path --version 2>&1
    } catch {
        return $false
    }

    $text = ($output | Out-String).Trim()
    return [bool]($text -match "ripgrep")
}

function Sync-RgEnvironment {
    $path = Get-RgPath
    if (-not $path) {
        return $false
    }

    $env:STALKER_RG = $path
    $dir = Split-Path -Parent $path
    if ($dir) {
        $escaped_dir = [Regex]::Escape($dir)
        if ($env:PATH -notmatch $escaped_dir) {
            $env:PATH = "$dir;$env:PATH"
        }
    }
    return $true
}

function Test-Tool {
    param([string]$Tool)
    switch ($Tool) {
        "python" { return [bool](Get-Command py -ErrorAction SilentlyContinue) -or [bool](Get-Command python -ErrorAction SilentlyContinue) }
        "rg" {
            $path = Get-RgPath
            if (-not $path) {
                return $false
            }
            return Test-RgCompatibility $path
        }
        "luac" {
            $path = Get-LuacPath
            if (-not $path) {
                return $false
            }
            return Test-LuacCompatibility $path
        }
        default { throw "Unknown tool: $Tool" }
    }
}

function Show-Hints {
    param([string]$Tool)
    switch ($Tool) {
        "python" {
            Write-Output "python install hints:"
            Write-Output "- winget: winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements"
            Write-Output "- chocolatey: choco install python -y"
            Write-Output "- scoop: scoop install python"
        }
        "rg" {
            Write-Output "ripgrep install hints:"
            Write-Output "- winget: winget install --id BurntSushi.ripgrep.MSVC -e --accept-source-agreements --accept-package-agreements"
            Write-Output "- chocolatey: choco install ripgrep -y"
            Write-Output "- scoop: scoop install ripgrep"
        }
        "luac" {
            Write-Output "luac install hints:"
            Write-Output "- winget: winget install --id rjpcomputing.luaforwindows -e --accept-source-agreements --accept-package-agreements"
            Write-Output "- chocolatey: choco install lua51 -y"
            Write-Output "- scoop: scoop install lua"
            Write-Output "- If the install does not expose luac.exe immediately, rerun the bootstrap in a new shell or set STALKER_LUAC to the full path."
        }
    }
}

function Install-WithChoco {
    param([string]$Tool)
    switch ($Tool) {
        "python" { choco install python -y | Out-Host; return $LASTEXITCODE -eq 0 }
        "rg" {
            choco install ripgrep -y | Out-Host
            if ($LASTEXITCODE -eq 0) {
                return Sync-RgEnvironment
            }
            return $false
        }
        "luac" {
            choco install lua51 -y | Out-Host
            if ($LASTEXITCODE -eq 0) {
                return Sync-LuacEnvironment
            }
            return $false
        }
    }
    return $false
}

function Install-WithScoop {
    param([string]$Tool)
    switch ($Tool) {
        "python" { scoop install python | Out-Host; return $LASTEXITCODE -eq 0 }
        "rg" {
            scoop install ripgrep | Out-Host
            if ($LASTEXITCODE -eq 0) {
                return Sync-RgEnvironment
            }
            return $false
        }
        "luac" {
            scoop install lua | Out-Host
            if ($LASTEXITCODE -eq 0) {
                return Sync-LuacEnvironment
            }
            return $false
        }
    }
    return $false
}

function Install-WithWinget {
    param([string]$Tool)
    switch ($Tool) {
        "python" {
            $ids = @("Python.Python.3.12", "Python.Python.3.11")
        }
        "rg" {
            winget install --id BurntSushi.ripgrep.MSVC -e --accept-source-agreements --accept-package-agreements --disable-interactivity | Out-Host
            if ($LASTEXITCODE -eq 0) {
                return Sync-RgEnvironment
            }
            return $false
        }
        "luac" {
            winget install --id rjpcomputing.luaforwindows -e --accept-source-agreements --accept-package-agreements --disable-interactivity | Out-Host
            if ($LASTEXITCODE -eq 0) {
                return Sync-LuacEnvironment
            }
            return $false
        }
        default {
            return $false
        }
    }

    foreach ($id in $ids) {
        winget install --id $id -e --accept-source-agreements --accept-package-agreements | Out-Host
        if ($LASTEXITCODE -eq 0) {
            return $true
        }
    }
    return $false
}

function Ensure-Tool {
    param([string]$Tool)
    if (Test-Tool $Tool) {
        Write-Output "${Tool}: ok"
        return $true
    }

    Write-Output "${Tool}: missing"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        if (Install-WithWinget $Tool) { return (Test-Tool $Tool) }
    }
    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        if (Install-WithScoop $Tool) { return (Test-Tool $Tool) }
    }
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        if (Install-WithChoco $Tool) { return (Test-Tool $Tool) }
    }

    Show-Hints $Tool
    return $false
}

if (-not $Tools -or $Tools.Count -eq 0) {
    $Tools = @("python")
}

$failed = $false
foreach ($tool in $Tools) {
    switch ($Command) {
        "status" {
            if (Test-Tool $tool) { Write-Output "${tool}: ok" } else { Write-Output "${tool}: missing"; $failed = $true }
        }
        "ensure" {
            if (-not (Ensure-Tool $tool)) {
                Write-Output "${tool}: unresolved"
                $failed = $true
            } else {
                Write-Output "${tool}: ready"
            }
        }
        "install-hints" {
            Show-Hints $tool
        }
    }
}

if ($failed) {
    exit 1
}
