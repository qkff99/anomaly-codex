# Bootstrap And Dependencies

Use this reference when the machine is missing required local tooling.

## Purpose

The skill should be able to bootstrap its own local prerequisites instead of only failing with "command not found".

Core tools:
- `python` for nearly all helper scripts
- `luac` for Lua syntax checks
- `rg` for fast search when available

## Bootstrap Helpers

- WSL/Linux/macOS shell: `./.skills/stalker-modding/scripts/bootstrap_env.sh ensure python rg luac`
- Windows PowerShell: `.\.skills\stalker-modding\scripts\bootstrap_env.ps1 ensure python rg luac`

If a wrapper script needs Python and cannot find it, it should try `bootstrap_env` before giving up.

## Notes

- Prefer package-manager installs over downloading random binaries.
- For Anomaly scripting, prefer Lua 5.1 when installing `luac`.
- If a package manager can only install a newer generic Lua, warn about version mismatch risk.
- On Windows, `winget` package ids can drift; use best-effort install plus fallback to `choco` or `scoop` when available.
