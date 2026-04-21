# Workspace Memory

This repository is a Codex skill and plugin workbench for STALKER Anomaly modding, not a live `gamedata` patch module.

Canonical local assets:
- `.skills/stalker-modding` is the primary skill source of truth.
- `plugins/stalker-modding-workbench` is the repo-local Codex plugin wrapper that exposes the same skill plus MCP endpoints.
- `.agents/plugins/marketplace.json` marks the plugin as `INSTALLED_BY_DEFAULT` for repo-local discovery.
- `.codex-stalker/workspace.json` is the machine-readable overlay for this workbench.
- `.vscode/mcp.json` is the tracked VS Code MCP config for the same repo-local endpoints, including `modorganizer2`.
- `.codex-stalker/workspace.json` also stores remembered external paths and curated known reference repos such as `stalker-gamma`.
- `xray-monolith` MCP works best through code search and documentation fetch; for concrete file reads, prefer raw GitHub URLs over `github.com/.../blob/...` links.
- `xray-monolith` doc search is useful but not fully reliable on narrow queries; if it falls back to README text, switch to code search plus raw file fetch.

Reference roots:
- `ai_workspace/vanilla scripts` for vanilla baseline scripts and configs
- `ai_workspace/src` for engine source
- `ai_workspace/lua_help.script.txt` for exported Lua symbols
- `ai_workspace/anomaly-modding-book-main` for local tutorial and file-format docs
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main` for local Anomaly MCM API, menu UI, and integration behavior
- `ai_workspace/user references` for user-added local references that should be searched automatically
- `tests/fixtures` for deterministic repo-local regression inputs; this is not a live mod workspace

Lifecycle notes:
- `ai_workspace/vanilla scripts/gamedata` is the baseline mod tree for file placement.
- Gameplay projects created here should normally mirror `gamedata/...` under `projects/<project-name>`.
- Project-local machine-readable metadata lives in `projects/<project-name>/.codex-stalker/project.json`.
- `projects/` is reserved for user-owned working copies and generated local projects, not checked-in smoke examples.
- `gamedata/scripts/*.script` is the gameplay script surface; modules with `on_game_start()` are discovered during Anomaly startup.
- MCM addon modules are discovered separately through `gamedata/scripts/*mcm.script` and should provide `on_mcm_load()`.
- `ui_mcm.get(path)` is runtime-only; do not call it while `on_mcm_load()` is building the options tree.
- For MCM integration, prefer shipping `*_mcm.script` plus localization strings rather than patching `ui_main_menu.script` or `ui_mm_main.xml` directly.
- If the user distributes through MO2, treat MO2 `mods/` as a deployment target, `profiles/` as profile state, `downloads/` as cache, and `overwrite/` as transient tool output rather than authored source.
- MO2 base paths can differ between portable and instance-managed setups; do not hardcode one layout unless the user provided it.
- Use `fomod_tool.py` when the user asks for a FOMOD installer package; the default package shape is `00 Core/` plus `fomod/info.xml` and `fomod/ModuleConfig.xml`.
- If the task starts from an existing mod, always choose explicitly between import-to-`projects` and in-place editing.
- Prefer `import_mod.py` for copy mode.
- If the task starts from a crash log, prefer `log_triage.py` before reading raw log text.
- Reusable MO2 `mods/`, unpacked `gamedata/`, log folders, and external mod roots may be remembered in `external_paths`, but only after explicit user approval.
- For log-driven triage, MO2 `mods/` or unpacked `gamedata/` is usually the better remembered path, because it helps resolve the failing addon files.
- Use `stalker-gamma` as a curated repo for addon discovery and modpack composition, not for authoritative engine semantics.
- `on_game_start` is for callback registration and lightweight script init, not for actor/world-dependent gameplay logic.
- `actor_on_first_update` is the preferred first hook for one-shot logic that needs the live actor or world state.
- `_g.script`, `lua_help.script`, and `axr_main.script` are the first files to inspect when tracing vanilla callback flow or exported symbols.
- Prefer existing callbacks and config hooks first, then DXML for XML diffs, then DLTX for `.ltx` diffs, then narrow monkey patches, and only then full-file overrides.
- Treat DXML and DLTX as Modded Exes features; call out that dependency explicitly if the target runtime is uncertain.
- String-table localization lives in `gamedata/configs/text/<language>/*.xml`, with language selected through `gamedata/configs/localization.ltx`.
- Vanilla Russian localization XML is often `windows-1251`; inspect with `xml_localization_tool.py`, prepare to UTF-8 before editing, then restore the original encoding.

If more local material is needed, prefer linking external folders or files into `ai_workspace/user references` instead of copying large reference dumps into the repo.

When a task is about actual mod behavior, search the relevant `ai_workspace` roots before using remote MCP or web sources.
When the task is inside a project, prefer the project overlay after `AGENTS.md` and before generic workspace assumptions.
For new work, prefer `init_project.py`, `scaffold_template.py`, `validate_project.py`, `package_project.py`, and `fomod_tool.py` over hand-rolled setup.
For repo-local reliability checks, prefer `run_regressions.py` over ad-hoc sample projects.
For existing mods, prefer `import_mod.py` unless the user explicitly wants in-place edits.
For quality review of mod roots or projects, prefer `./.skills/stalker-modding/scripts/quality_scan.py scan <path> --task <task-type>` after syntax checks. It reports Lua quality risks, MCM/save/hot-path issues, vanilla deltas, patch opportunities, conflict surface, dependency graph, and task gates. Use its `graph`, `suggest-patch`, `save-template`, and `optional-pattern` subcommands for advanced review and implementation scaffolds.
For recurring log work, prefer remembered MO2 `mods/` or unpacked `gamedata/` first; use `logs_dir` memory only when the user explicitly wants repeated latest-log automation.
When local refs are not enough, prefer `discover_github_refs.py` and curated known repos before generic web searching.
When Lua files are edited, prefer `./.skills/stalker-modding/scripts/luac_tool.py check ...` as the first syntax gate.
When mod behavior is edited or reviewed, prefer `./.skills/stalker-modding/scripts/quality_scan.py scan ... --task ...` as the static quality gate.
When localization XML is edited, prefer `./.skills/stalker-modding/scripts/xml_localization_tool.py prepare-edit ...` before editing and `finish-edit ...` before finalizing.
If Python, `luac`, or `rg` is missing, prefer `./.skills/stalker-modding/scripts/bootstrap_env.sh ensure ...` before treating the environment as blocked.
