# AGENTS.md

## How to MOD STALKER ANOMALY 1.5.3
This document is about some modding to understand modding context and creating mods.

## MCP Tools
Use DeepWiki/GitMcp MCP tools when subsystem mapping or architectural context is needed.
Indexed repos:
- `themrdemonized/xray-monolith`
- `TheParaziT/anomaly-modding-book`
- `ModOrganizer2/modorganizer`
- `Grokitach/Stalker_GAMMA`

## Local References
- `ai_workspace/vanilla scripts` — local copy of vanilla scripts/configs
- `ai_workspace/anomaly-modding-book-main` — local copy of the modding book
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main` — local Anomaly MCM reference repo; use it as the primary authority for `ui_mcm`, `on_mcm_load`, option-tree rules, keybind widgets, and MCM conflict surfaces
- `ai_workspace/GAMMA Scripts` — flattened local GAMMA MO2 `configs/` and `scripts/` reference overlay; use it for pack-specific addon behavior, compatibility examples, and conflict surfaces
- `ai_workspace/src` — engine source
- `ai_workspace/lua_help.script.txt` — exported Lua API surface
- `ai_workspace/user references` — user-managed local reference corpus; add any extra docs, code dumps, notes, or decompiled material here and the skill should search it automatically
- If the user asks, or if the agent decides extra local references are materially useful, create links into `ai_workspace/user references` instead of copying large external folders into the repo.

## Repo Assets
- `.skills/stalker-modding` — canonical local Codex skill
- `.codex-stalker/workspace.json` — machine-readable overlay for this workbench
- `help/stalker/*.md` — local project memory for the skill
- `.agents/plugins/marketplace.json` — repo-local Codex marketplace entry
- `.vscode/mcp.json` — tracked VS Code MCP config mirroring the repo-local plugin MCP endpoints
- `plugins/stalker-modding-workbench` — repo-local plugin wrapper with MCP config
- `plugins/expertise-compiler` — bundled, dependency-free Expertise Compiler plugin and runtime
- `.expertise/stalker-anomaly` — checked-in starter evidence vault for this workbench
- `.agents/skills/stalker-anomaly-expert` — mandatory runtime skill for the starter vault
- `.codex-stalker/workspace.json` also stores remembered external paths and curated known reference repos
- `tests/fixtures` — deterministic regression inputs for logs, XML encodings, imports, and project-toolchain scenarios
- `.skills/stalker-modding/scripts/expertctl.py` — no-install entrypoint for the bundled Expertise Compiler

## Workspace Project Layout
- If a new local project is initialized in this workspace, create it as a dedicated folder inside `projects/`.
- This applies to mods, script packs, tool prototypes, and other workbench projects.
- Treat `projects/<project-name>` as the project root for edits, references, and future follow-up tasks.
- Each project should keep machine-readable metadata at `projects/<project-name>/.codex-stalker/project.json`.
- `projects/` is user-owned workspace state, not a repo-tracked smoke-fixture area.
- Prefer `init_project.py` to create new project roots, `scaffold_template.py` to create starter payloads, `validate_project.py` for checks, and `package_project.py` for loose packaging.
- Prefer `run_regressions.py` for deterministic repo-local reliability checks instead of keeping ad-hoc smoke projects under `projects/`.
- When a distributable FOMOD installer is requested, prefer `fomod_tool.py` instead of hand-writing `fomod/info.xml` and `fomod/ModuleConfig.xml`.
- When the user wants to edit an existing mod, always ask whether to import a copy into `projects/` or edit the provided target in place.
- Prefer import-to-`projects` as the safer default and use `import_mod.py` for copy mode.

## Quick Facts
- Runtime: XRay/Anomaly Lua (`SIMBOARD`, `db`, `alife`, `game_graph`, engine callbacks).
- `ai_workspace/vanilla scripts/gamedata` is the baseline reference tree for mod file placement.
- Local gameplay projects should normally mirror the game tree under `projects/<project-name>/gamedata/...`.
- Scripts in `gamedata/scripts/*.script` are auto-discovered by the script layer; modules with `on_game_start()` can be picked up during Anomaly startup without a manual central registry.
- MCM modules are discovered separately through `gamedata/scripts/*mcm.script`; they should expose `on_mcm_load()` and return a valid options tree.
- Treat `on_game_start` as early script startup, not as a world-ready hook.
- Prefer `actor_on_first_update` for first one-shot logic that needs `db.actor`, spawned objects, or in-world services.
- Treat `main_menu_on_init` and other `main_menu_*` hooks as menu-only surfaces.
- Do not call `ui_mcm.get(...)` inside `on_mcm_load()`. Read MCM values later at runtime or on apply callbacks.
- Use `_g.script`, `lua_help.script`, and `axr_main.script` as the first orientation files when tracing vanilla script flow.
- Follow `$stalker-anomaly-expert` before repository decisions: inspect vault freshness, route narrowly, retrieve an evidence pack, and verify decision-critical source ranges.
- String-table localization lives in `gamedata/configs/text/<language>/*.xml`, with active language selected through `gamedata/configs/localization.ltx`.
- Vanilla Russian localization XML is commonly `windows-1251`; inspect and round-trip through the XML localization helper before editing legacy-encoded files.
- If the user uses Mod Organizer 2, remember that the live game view is virtualized from MO2's mod directories, not authored directly in the game folder.
- Treat MO2 `mods/` as the install target for packaged mods, `profiles/` as profile state, `downloads/` as cache, and `overwrite/` as a transient sink for tool output rather than the source of truth for authored files.
- Do not hardcode a single MO2 layout. Portable and instance-managed setups can place these directories in different base locations.
- For this workspace, author from `projects/<project-name>/gamedata/...` first, then package to a loose overlay or FOMOD when distribution is requested.
- Remember reusable external paths like MO2 `mods/`, unpacked `gamedata/`, `logs_dir`, or external mod roots in `.codex-stalker/workspace.json` only after the user explicitly allows it.
- For log-driven work, prefer remembering MO2 `mods/` or unpacked `gamedata/` before a `logs_dir`, because those paths are more useful for resolving the failing mod files.
- Use `Grokitach/Stalker_GAMMA` as a curated modpack-index reference for addon discovery and install lists, not as the final authority on engine behavior.

## Preferred Extension Order
1. Existing callbacks, config hooks, or vanilla extension points.
2. DXML for XML diffs on Modded Exes.
3. DLTX for `.ltx` diffs on Modded Exes.
4. Narrow monkey patches that preserve the original function.
5. Full-file overrides only as a last resort.

Default practice notes:
- Search and trace vanilla behavior first, then patch.
- Treat anomaly-modding-book as strong workflow guidance, but verify runtime semantics against local vanilla scripts or engine source before acting.
- `actor_on_update` remains a hot-path fallback, not a default extension surface.
- Prefix custom callback names so they do not collide with other addons.

## Core Engineering Principles
1. Vanilla-first compatibility.
   Keep vanilla behavior intact unless a narrow patch is truly required.
2. Nil safety everywhere.
   Engine-facing code should assume partial failure and degrade safely.
3. Save safety.
   Persistent state must remain serializable.
4. Performance-first hot paths.
   Avoid unbounded work in actor update paths.
5. Deterministic fallbacks.
   Failure paths should fall back to safe behavior instead of hard-breaking the runtime.

## Lua Style and Conventions
- Keep code Lua 5.1 compatible.
- Prefer local aliases for hot globals in hot modules.
- Validate external inputs with `type(...)` / `tonumber(...)`.
- Avoid hidden globals.
- Preserve existing naming style:
  - snake_case for locals/helpers/fields
  - `Module:_method(...)` for internal methods
- Keep comments short and only where behavior is non-obvious

## Cross-Platform Helpers
- Prefer Python helper entrypoints for shared behavior.
- On WSL/macOS use `python3` or the provided `.sh` wrappers.
- On Windows PowerShell use `py -3` or the provided `.ps1` wrappers.
- Use `init_project.py`, `scaffold_template.py`, `check_project.py`, `validate_project.py`, and `package_project.py` for project-local workflow instead of ad-hoc file creation.
- Use `fomod_tool.py` / `.sh` / `.ps1` to build a basic `00 Core + fomod/` installer package when the user asks for FOMOD output.
- Use `run_regressions.py` / `.sh` / `.ps1` for deterministic repo-local regression coverage across logs, XML encodings, project scaffolding/imports, and packaging.
- Use `log_triage.py` / `.sh` / `.ps1` to summarize huge Anomaly/XRay logs before bringing them into context.
- Use `import_mod.py` / `.sh` / `.ps1` to copy an existing mod root or `gamedata/` into `projects/<name>`.
- Use `extract_mo2_resources.py` / `.sh` / `.ps1` to extract MO2 `mods/*` `configs/` and `scripts/` payloads into one shared `dest/configs` + `dest/scripts` reference overlay.
- Use `external_path_tool.py` / `.sh` / `.ps1` to remember logs folders, MO2 `mods/`, unpacked `gamedata/`, or external mod roots, but only with the user's permission.
- Use `discover_github_refs.py` / `.sh` / `.ps1` to search GitHub references and persist only curated high-signal repos into MCP config and workspace overlay.
- Use `link_user_reference.py` / `.sh` / `.ps1` to link external local references into `ai_workspace/user references`.
- Use `expertctl.py` to query, update, compile, repair, or audit the bundled `stalker-anomaly` evidence vault.
- Do not bootstrap or install Python, `luac`, `rg`, LSP servers, compilers, or other tooling automatically. Report the missing prerequisite and the reduced validation instead; provision it only when the user explicitly asks.
- Use `xml_localization_tool.py` / `.sh` / `.ps1` to inspect legacy XML encodings, convert localization XML to UTF-8 for editing, and restore the original encoding afterward.

## Performance Rules
- Budget heavy loops.
- Bound cache/table growth.
- Prefer incremental cleanup over bulk cleanup spikes.
- Memoize repeated expensive checks per tick/per call where practical.

## Compatibility Rules
- Supported baseline remains Anomaly 1.5.3 + Modded Exes.
- Optional systems may be absent; keep code robust when `ui_mcm`, dynamic news, or optional globals are missing.
- Optional patches should stay optional/config-gated when feasible.
- Do not introduce mandatory external dependencies without a clear reason.

## Logging and Diagnostics
- Prefer `log_triage.py` before reading or pasting a huge raw log.
- For engine fatal logs, prefer the `inspect_points` emitted by `log_triage.py`; they should resolve stack frames into local `ai_workspace/src/...` files when the stack contains source paths.
- Keep regression log fixtures under `tests/fixtures/logs` rather than under `projects/`.
- High-signal Lua markers:
  - `SCRIPT RUNTIME ERROR`
  - `SCRIPT SYNTAX ERROR`
  - `SCRIPT ERROR (while running file)`
  - `SCRIPT ERROR (memory allocation)`
  - `! [SCRIPT ERROR]:`
  - `! [LUA]`, `* [LUA]`, `~ [LUA]`
  - `stack traceback:`
- High-signal engine fatal markers:
  - `FATAL ERROR`
  - `Expression    :`
  - `Function      :`
  - `File          :`
  - `Line          :`
  - `Description   :`
  - `stack trace:`
- For recurring crash triage, prefer asking for MO2 `mods/` or unpacked `gamedata` first so the failing paths can resolve back to installed addons.
- Use `logs_dir` memory only when the user explicitly wants repeated "latest log" automation.

## Validation Expectations
There is no automated test suite. For risky runtime changes, do as many as practical:
1. syntax check touched scripts
2. check every changed Lua function/prototype stays below Lua 5.1's 200-local limit
3. smoke boot
4. actor first update
5. save/load cycles

Preferred syntax check helper:
- `python3 ./.skills/stalker-modding/scripts/luac_tool.py check <file-or-dir>`
- `py -3 .\.skills\stalker-modding\scripts\luac_tool.py check <file-or-dir>`

Lua local-limit check (mandatory whenever a `.script` or `.lua` file changes):
- Run the Lua 5.1 compiler found by `luac_tool.py detect` with `-l -l <file>`.
- Inspect every emitted prototype header (`... locals ...`); each must stay strictly below `200` locals. Syntax success alone does not prove this.
- Treat `200` or more locals as a blocker: split the function/module and rerun the check.

## Manual QA Checklist
Before finalizing risky behavior changes:
1. game start does not crash
2. callbacks register
3. save/load remains clean

## Common Anti-Patterns To Avoid
- Unbounded scans inside `actor_on_update`.
- Storing non-serializable engine objects in save state.
- Introducing new mandatory monkey patches without strong justification.
- Adding config keys without updating MCM/localization/docs.
- Silently swallowing errors without a controlled fallback.

## Definition of Done
A change is done when:
1. behavior is correct and nil-safe
2. hot-path cost is bounded
3. save/load safety is preserved
4. changed Lua files pass syntax and the 200-local prototype check
5. the diff stays focused on the intended subsystem

<!-- expertise-compiler:stalker-anomaly:start -->
## Mandatory stalker-anomaly Wiki workflow

For every user task in this repository, use `$stalker-anomaly-expert` to gather a concise evidence pack from the `stalker-anomaly` vault before making a plan, code change, review finding, or final repository decision. The pack must state freshness and version, relevant Wiki routes, verified source paths and ranges, conflicts, and missing evidence. If the vault is stale, unhealthy, conflicting, or incomplete, repair or disclose that condition instead of substituting model memory.
<!-- expertise-compiler:stalker-anomaly:end -->
