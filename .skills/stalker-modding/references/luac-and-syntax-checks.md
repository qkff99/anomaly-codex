# luac And Syntax Checks

Use this reference when touched Lua files need a fast syntax gate before manual QA.

## Why This Matters

- Anomaly scripting stays Lua 5.1 compatible.
- `luac -p` catches parse errors before boot.
- Syntax checking is expected before risky runtime changes when Lua files were edited.

## Preferred Tool

Use `scripts/luac_tool.py`.

It:
- detects `luac5.1`, `luac`, `lua5.1`, or `lua`
- prefers Lua 5.1 tooling
- can print install hints when no compiler is available
- syntax-checks `.lua` and `.script` files

## Typical Commands

WSL/Linux:
- `python3 ./.skills/stalker-modding/scripts/luac_tool.py detect`
- `python3 ./.skills/stalker-modding/scripts/luac_tool.py check path/to/file.script`
- `python3 ./.skills/stalker-modding/scripts/luac_tool.py check --recursive projects/my-mod`

Windows PowerShell:
- `py -3 .\.skills\stalker-modding\scripts\luac_tool.py detect`
- `py -3 .\.skills\stalker-modding\scripts\luac_tool.py check path\to\file.script`
- `.\.skills\stalker-modding\scripts\luac_tool.ps1 check --recursive projects\my-mod`

## Install Guidance

If `luac` is missing:
- Linux/WSL: prefer a Lua 5.1 package such as `lua5.1`
- Windows: install a Lua 5.1 distribution with `luac.exe`, then add it to `PATH` or set `STALKER_LUAC`

Do not silently use an unknown newer Lua version for engine-facing scripts when version-sensitive syntax is in play.

## Validation Rule

If Lua files were touched, run a syntax check before claiming completion unless the environment makes that impossible.
