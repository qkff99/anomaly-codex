---
name: stalker-modding
description: "Use when working on S.T.A.L.K.E.R./XRay modding tasks, especially Anomaly 1.5.3 + Modded Exes: Lua scripts, configs, UI XML, XML localization, crash-log triage, existing addon maintenance, HUD and weapons, callbacks, binders, save/load safety, engine capability lookup, mixed mod workbenches, packaging, MO2/FOMOD distribution, and GitHub/GitMCP reference research."
---

# STALKER Modding

Use this skill for XRay-family modding work with an Anomaly-first bias. It is optimized for code, config, UI, HUD, save/load, and engine-facing tasks, while still providing curated lookup guidance for animations, assets, mapping, SDK workflows, and Codex-side skill workbenches that generate or edit mods.

Keep context small. Load only the references that match the active task.

## Supported Scope

Primary support:
- Anomaly 1.5.3 and Modded Exes workflows
- Lua scripting, LTX/XML config work, UI/MCM, XML localization, DXML, DLTX, HUD/weapons, callbacks/binders
- crash-log triage for large Anomaly/XRay logs and compact stack extraction
- existing mod maintenance through safe import-to-`projects` or explicit in-place editing
- save/load safety, runtime debugging, engine capability lookup
- workspace-local packaging, FOMOD generation, Mod Organizer 2 directory/layout awareness, and remembered external paths
- GitHub/GitMCP reference discovery for curated addon and modpack repos
- mixed workbenches that contain several mod prototypes in one folder

Fallback support:
- Other XRay-family branches, when local code or trusted repo references make the answer clear
- assets, animations, mapping, models, and SDK topics through curated references rather than deep procedural automation

## Lua Tooling

This skill should know how to detect, install-guide, and use `luac` for Lua 5.1 syntax checks.

- Prefer `scripts/luac_tool.py detect` to discover the compiler.
- Prefer `scripts/luac_tool.py check ...` to syntax-check touched `.lua` and `.script` files.
- If no compiler is available, use `scripts/luac_tool.py --install-if-missing` or `scripts/bootstrap_env.* ensure luac` before falling back to install hints.
- Prefer Lua 5.1 tooling for Anomaly work. Warn when the detected compiler is not clearly 5.1.
- Prefer `scripts/quality_scan.py scan <path> --task <task-type>` after or alongside `luac` for Anomaly-specific static quality checks: hidden globals, unsafe engine boundaries, hot-path polling, MCM contract errors, save serialization risks, full overrides, patch opportunities, and conflict surface.
- Use `scripts/quality_scan.py explain-rule <rule-id>` when a reported rule needs a concise fix pattern.
- Use `scripts/quality_scan.py graph <path>` for script dependency graphs, exports, calls, callbacks, save functions, monkey patches, and conflict surface.
- Use `scripts/quality_scan.py suggest-patch <gamedata-file>` to compare a full `.ltx`/`.xml` override against local vanilla and generate a DLTX suggestion or DXML scaffold.
- Use `scripts/quality_scan.py save-template <module>` for versioned save/load migration boilerplate, and `scripts/quality_scan.py optional-pattern <id>` for optional dependency guard snippets.

## Dependency Bootstrap

This skill should attempt to bootstrap missing local tooling when practical.

- Use `scripts/bootstrap_env.sh ensure python rg luac` on shell-based systems.
- Use `scripts/bootstrap_env.ps1 ensure python rg luac` on Windows PowerShell.
- Wrapper scripts should attempt `bootstrap_env` automatically when Python is missing.
- Prefer package-manager installs over ad-hoc downloads.

## Compiled Knowledge Vault

This workbench ships a checked-in `stalker-anomaly` vault under `.expertise/`. It is compact and resolves source spans against the tracked reference packs. Before planning, editing, reviewing, or giving a repository answer, follow `$stalker-anomaly-expert`: check vault health, route through the Wiki, retrieve a bounded evidence pack, and verify decision-critical source spans.

Use `scripts/expertctl.py` as the no-install entrypoint for the bundled compiler. Run `status`, `doctor`, `search`, `context`, and narrow `read-source` queries during ordinary work. Before extending this compact starter, run `hydrate stalker-anomaly`, then use `add`, `scan`, `compile-plan`, `apply-build`, and `doctor`; never hand-edit vault state or snapshots.

## Workspace Project Layout

When initializing a new local project in this workspace, create a dedicated folder under `projects/`.

- Use `projects/<project-name>` for new mods, script packs, experiments, or tooling subprojects.
- Treat that folder as the active project root for subsequent edits and analysis.
- Treat `projects/<project-name>/.codex-stalker/project.json` as the machine-readable overlay for that project.
- Use `scripts/init_project.py` to create the folder and starter metadata instead of hand-rolling project roots.
- Treat `projects/` as user-owned working state; keep repo-tracked smoke inputs under `tests/fixtures` instead of checked-in sample projects.
- If the user wants to edit an existing mod, ask whether to import a copy into `projects/` or edit the target in place.
- Prefer import-to-`projects` as the safer default, and use `scripts/import_mod.py` for copy mode.
- Use `scripts/extract_mo2_resources.py` when the user wants bulk local references from MO2 `mods/*`; it flattens discovered `configs/` and `scripts/` payloads into one `dest/configs` + `dest/scripts` tree and reports path conflicts.
- If the user asks for a distributable installer, use `scripts/fomod_tool.py` to stage a `00 Core + fomod/` package from the project payload instead of hand-authoring the XML.
- Keep shared references in `ai_workspace`, but keep new project-owned files under `projects/`.

## Mod Structure And Script Lifecycle

This skill should recognize the standard STALKER resource tree and use `ai_workspace/vanilla scripts/gamedata` as the baseline when deciding where files belong.

- Treat `gamedata/` as the mod root overlay that overrides packed `db` resources.
- New local gameplay projects should usually mirror the game tree under `projects/<project-name>/gamedata/...`.
- Typical paths:
  - `gamedata/scripts/*.script` for gameplay Lua modules
  - `gamedata/configs/**/*.ltx` and `gamedata/configs/**/*.xml` for configs and UI XML
  - `gamedata/textures`, `gamedata/sounds`, `gamedata/meshes` for assets
- Treat `.script` files in `gamedata/scripts` as auto-discovered script modules. In Anomaly, startup scans the scripts folder and calls module `on_game_start()` handlers when present.
- Prefer explicit `require(...)` only for helper-library dependencies, not as a substitute for basic script discovery.

Lifecycle rules:
- Root scope: define locals, helpers, constants, and optional `AddScriptCallback(...)`; do not assume gameplay world state here.
- `on_game_start`: use for callback registration and lightweight script-layer setup only.
- Do not treat `on_game_start` as a world-ready or level-ready hook. Scripts are loaded, but `db.actor`, `level`, spawned objects, and gameplay UI may still be unavailable or incomplete.
- `main_menu_on_init` and related menu callbacks are menu-only surfaces. Do not attach gameplay-world logic there.
- `on_game_load`: use for load-time reinitialization and binder-adjacent restore work, but do not assume every gameplay object is already spawned.
- `actor_on_first_update`: prefer this as the first safe hook for one-shot logic that needs the in-game actor, level objects, inventory, or world-attached UI state.
- `actor_on_update`: treat as a hot path and use only when no event-driven alternative is good enough.

## Extension Strategy

When choosing how to extend or modify behavior, prefer the least invasive surface that can solve the problem.

1. Existing callbacks, config hooks, or vanilla extension points
2. DXML for XML patching before load
3. DLTX for differential `.ltx` changes
4. Monkey patching existing Lua functions
5. Direct full-file overrides as a last resort

Rules:
- Prefer callbacks over monkey patching whenever a callback can express the behavior.
- Prefer DXML over replacing whole XML files when the target environment has Modded Exes and the task is really an XML diff.
- Prefer DLTX over full `.ltx` replacement when the target environment has Modded Exes and the task is a config diff.
- Monkey patch only when callbacks or diff-style patch systems cannot solve the problem cleanly.
- If monkey patching is required, preserve the original function first, patch narrowly, and be explicit about load-order and conflict risk.
- Treat anomaly-modding-book workflow advice as strong default practice, but verify exact runtime semantics against local vanilla code or engine source before acting.

## XML Localization And Encodings

This skill should understand the vanilla localization layout and the encoding pitfalls around STALKER XML.

- Treat `gamedata/configs/text/<language>/*.xml` as the primary string-table localization surface.
- Treat `<string_table><string id=\"...\"><text>...</text></string></string_table>` as the canonical localization XML structure.
- Read the active language from `gamedata/configs/localization.ltx` when language choice matters.
- Know that UI XML often stores string-table ids in `<text>` nodes, and engine/UI code resolves them through `CStringTable().translate(...)`.
- Know that LTX and gameplay XML frequently reference localization ids via keys like `text`, `hint`, `inv_name`, and `inv_name_short`.
- Treat `on_localization_change` as the runtime hook for UI or script surfaces that need to refresh cached translated strings.
- Vanilla Russian localization XML is often `windows-1251`. Do not assume UTF-8 just because the file extension is `.xml`.
- Before reading or editing legacy-encoded XML, prefer `scripts/xml_localization_tool.py inspect` and then `prepare-edit`.
- After editing a prepared file, run `scripts/xml_localization_tool.py finish-edit` to restore the original encoding before finalizing.

## Source Priority

Use the minimum source tier that can answer the task correctly.

1. Local workspace code and configs
2. Local vanilla refs
3. Local Lua API export
4. Local engine source
5. Indexed repo context
6. Live repo references
7. External web

Expanded rules:
- Start with local files whenever the task is about the current workspace.
- If `AGENTS.md` exists, read it before generic references.
- If the current task is inside `projects/<project-name>`, prefer `projects/<project-name>/.codex-stalker/project.json` after `AGENTS.md` and before workspace-wide overlay assumptions.
- If `.codex-stalker/workspace.json` or `.codex-stalker/workspace.yml` exists, treat it as project overlay and prefer it over generic assumptions.
- If `help/stalker/*.md` exists, treat it as local project memory.
- Treat `ai_workspace` as structured local references, not as a generic dump folder:
  - `ai_workspace/vanilla scripts` -> vanilla baseline
  - `ai_workspace/src` -> engine source
  - `ai_workspace/lua_help.script.txt` -> exported API surface
  - `ai_workspace/anomaly-modding-book-main` -> local tutorial and format docs
  - `ai_workspace/Anomaly-Mod-Configuration-Menu-main` -> local authority for Anomaly MCM menu behavior, API, and conflict surface
  - `ai_workspace/GAMMA Scripts` -> flattened local GAMMA MO2 configs/scripts reference overlay for pack-specific addon behavior and conflict examples
  - `ai_workspace/user references` -> user-managed extra references; search these automatically when present
  - `.expertise/stalker-anomaly` -> checked-in, provenance-backed routes and source hashes for this workbench
- Treat `.codex-stalker/workspace.json` `external_paths` as remembered user-approved search roots for logs, MO2 installs, unpacked `gamedata`, or external mod folders.
- Treat `.codex-stalker/workspace.json` `known_reference_repos` as curated persistent GitMCP references that should be preferred over ad-hoc web searching.
- If the user asks, or if the agent decides extra local material is worth indexing, link it into `ai_workspace/user references` instead of copying it into the repo.
- Use `xray-monolith` before generic web lookups for engine capabilities or Modded Exes behavior.
- Use `anomaly-modding-book` before generic web lookups for tutorials, onboarding, file formats, and workflow questions.
- Use `modorganizer2` before generic web lookups for MO2 directory layout, profile/overwrite assumptions, VFS behavior, and packaging expectations.
- Use local `ai_workspace/GAMMA Scripts` before remote `stalker-gamma` when pack-specific scripts/configs are enough; use curated repos such as `stalker-gamma` before generic web lookups when local refs are insufficient for addon discovery, modpack composition, or pack-specific glue examples.
- Use DeepWiki for fast subsystem mapping, but verify actionable claims in code or primary references before editing.

Load `references/source-priority.md` when source choice is non-obvious.

## Task Classifier

Route the task before loading detail.

Primary task modes:
- `bugfix`, `feature`, `refactor`, `review` or `code-review`
- `log-triage`, `reference-discovery`
- `config-tweak`, `localization`, `merge-conflict-analysis`, `reverse-engineering`
- `tutorial`
- `distribution-packaging`, `mo2`, `fomod`

Subsystem focus:
- `ui-mcm` or `ui-hud`, `weapons-hud`, `save-load`, `engine-capability`
- `tasks-story-alife`, `visible-body-legs`
- `assets-animations`, `asset-reference`, `animation-reference`, `mapping-sdk`
- `dxml-dltx`

Recommended references:
- file placement, load order, onboarding: `references/mod-structure-and-load-order.md`
- project scaffolding, validate, package, bootstrap workflow: `references/project-toolchain.md`
- repo-local regression workflow and canonical fixtures: `references/project-toolchain.md`
- crash summaries and stack-driven debugging workflow: `references/log-triage.md`
- existing mod import-vs-in-place workflow: `references/existing-mod-workflow.md`
- MO2 layout and FOMOD packaging: `references/mod-organizer2-and-fomod.md`
- GitHub discovery and curated repo persistence: `references/github-reference-discovery.md`, `references/repos/stalker-gamma.md`
- modding-book workflow defaults and Lua patterns: `references/modding-book-practices.md`
- differential patch systems and compatibility-first config strategy: `references/dxml-and-dltx.md`
- localization and XML encodings: `references/localization-and-encodings.md`, `references/ui-xml-mcm.md`
- MCM workflow and API: `references/mcm-menu.md`, `references/ui-xml-mcm.md`
- code or review: `references/runtime-model.md`, `references/callbacks-and-binders.md`
- save/load: `references/save-safety.md`, `references/manual-qa.md`
- actor or binder hot path: `references/performance-hotpaths.md`
- weapons and HUD: `references/weapons-and-hud.md`, `references/ui-xml-mcm.md`
- visible body and legs: `references/visible-body-and-legs.md`
- tasks, story, A-Life: `references/tasks-story-alife.md`
- engine questions: `references/repos/xray-monolith.md`
- tutorial or onboarding: `references/repos/anomaly-modding-book.md`
- assets and animations: `references/assets-and-animations.md`
- mapping or SDK: `references/mapping-and-sdk.md`

## Workflow

1. Classify the task and identify whether the workspace, a project copy, or an explicit in-place path is the source of truth.
2. Before substantial task work, follow `$stalker-anomaly-expert` and obtain a bounded evidence pack from the checked-in vault.
3. Run `scripts/scan_workspace.py` or the platform wrapper for unfamiliar or mixed workspaces.
4. If the task is about an existing mod, ask whether to import a copy into `projects/` or edit the target in place.
5. For copy mode, use `scripts/import_mod.py`; for in-place mode, work directly on the provided path and do not force project creation.
6. If the task needs a new local project, create it with `scripts/init_project.py` and keep work under `projects/<project-name>`.
7. If the task is inside a project, validate `projects/<project-name>/.codex-stalker/project.json` with `scripts/check_project.py`.
8. If needed, validate `.codex-stalker/workspace.json` or `.codex-stalker/workspace.yml` with `scripts/check_overlay.py`.
9. Remember external paths only after the user explicitly allows it.
10. For crash or log-driven bugfix work, run `scripts/log_triage.py` before pasting a huge raw log into context. For engine fatal logs, use its resolved `inspect_points` as the first source locations to inspect in `ai_workspace/src`.
11. Use `scripts/query_hints.py` to pick the smallest effective search surface.
12. For unfamiliar subsystems, use the vault router, lexical search, bounded context, and source verification before broad raw-file search.
13. Use `scripts/find_references.py` to search only the relevant roots instead of grepping the whole tree blindly. This search should also include `ai_workspace/user references` automatically and, for the right task types, remembered external mod roots.
14. For log-driven tasks where script or asset resolution matters, prefer asking for MO2 `mods/`, unpacked `gamedata`, or another external mod root before asking for a remembered `logs_dir`.
15. If external refs are needed, ask for MO2 `mods/`, unpacked `gamedata`, or another external mod root and remember the confirmed path only with the user's permission.
16. If extra local references are needed, create links into `ai_workspace/user references` with `scripts/link_user_reference.py`, or extract MO2 `configs/` + `scripts/` references with `scripts/extract_mo2_resources.py`.
17. Read local code and configs before repo or web references.
18. For entrypoints and touchpoints, run `scripts/find_entrypoints.py` and `scripts/map_subsystems.py`.
19. If the task is scaffold-heavy, prefer `scripts/scaffold_template.py` over hand-creating starter files.
20. If the task is about distribution or MO2 delivery, package the project first and then use `scripts/fomod_tool.py` for a FOMOD staging folder when requested.
21. If XML localization files or other legacy-encoded XML files were touched, inspect them with `scripts/xml_localization_tool.py`, use `prepare-edit` before editing, and `finish-edit` before finalizing.
22. If Lua files were touched, run `scripts/luac_tool.py check ...` before finalizing unless the environment clearly cannot provide a compiler.
23. For mod edits, reviews, imports, and feature work, run `scripts/quality_scan.py scan <project-or-mod-root> --task <task-type>` when practical. Treat high findings as blockers unless the task explicitly accepts that risk.
24. For project-local smoke checks, prefer `scripts/validate_project.py`, `scripts/package_project.py`, and `scripts/fomod_tool.py` as needed.
25. For repo-local reliability checks and first-run verification, use `scripts/run_regressions.py` instead of relying on hand-kept example projects under `projects/`.
26. If local refs are insufficient, use `scripts/discover_github_refs.py` to search GitHub and persist only curated high-signal repos.
27. Verify any remote or wiki-derived claim against local code or primary references before acting.
28. Report verified facts separately from inference.

## Safety Rules

- Preserve vanilla behavior unless a narrow deviation is required.
- Treat engine-facing code as nil-fragile.
- Keep save state serializable and versionable.
- Budget work in `actor_on_update`, binder updates, and UI-per-frame paths.
- Prefer deterministic fallback over silent breakage.
- Do not guess about engine behavior when local or primary references can resolve it.
- If local refs are absent and the answer comes from live repos, say that confidence is lower.

Load `references/save-safety.md` and `references/performance-hotpaths.md` before proposing risky changes.

## Repo And MCP Usage

Use this order when online references are needed:

1. `xray-monolith` GitMCP for engine capability, modded exes behavior, exported callbacks, and engine patches
2. `anomaly-modding-book` GitMCP for tutorials, file formats, onboarding, and workflow guidance
3. `modorganizer2` GitMCP for MO2 directory layout, VFS behavior, and packaging assumptions
4. Curated known GitMCP refs such as `stalker-gamma` for addon discovery, install lists, and pack-specific glue examples
5. `deepwiki` for repo architecture and path discovery
6. Web only as a last resort

Do not treat tutorial repos as the final authority on engine behavior when `xray-monolith` or local engine source says otherwise.

`xray-monolith` access notes:
- Prefer MCP code search to locate engine files, callback definitions, and script-side entrypoints.
- Prefer `fetch_xray_monolith_documentation` for repo overview, changelog, and feature presence checks.
- When reading a specific repo file through generic fetch, prefer a raw GitHub URL such as `raw.githubusercontent.com/...`.
- Do not pass `github.com/.../blob/...` URLs into generic fetch unless HTML wrapper output is acceptable.
- Treat `search_xray_monolith_docs` as a secondary helper only; it may time out or fall back to README-level content instead of the exact file you want.

## Overlay Contract

If present, use these local files in this order:

1. `AGENTS.md`
2. `projects/<project-name>/.codex-stalker/project.json` when the task root is inside a project
3. `.codex-stalker/workspace.json`
4. `.codex-stalker/workspace.yml`
5. `help/stalker/*.md`

Overlay defaults:
- `game_family: anomaly`
- `baseline: anomaly_1_5_3_modded_exes`
- `workspace_type: mixed_workbench`
- `notes_language: ru`

Use `manifests/overlay_schema.yml` and `scripts/check_overlay.py` for validation.

Tracked overlay extensions in v2:
- `external_paths`
- `known_reference_repos`

## Cross-Platform Commands

Prefer Python entrypoints so the same helpers work in WSL, Linux, and Windows PowerShell.

- Use `scripts/log_triage.py`, `scripts/import_mod.py`, `scripts/extract_mo2_resources.py`, `scripts/external_path_tool.py`, and `scripts/discover_github_refs.py` as the cross-platform helpers for Wave 2 maintenance workflows.

- WSL/macOS/Linux:
  - `python3 ./.skills/stalker-modding/scripts/scan_workspace.py .`
  - `./.skills/stalker-modding/scripts/scan_workspace.sh .`
- Windows PowerShell:
  - `py -3 .\.skills\stalker-modding\scripts\scan_workspace.py .`
  - `.\.skills\stalker-modding\scripts\scan_workspace.ps1 .`

The same pattern applies to:
- `bootstrap_env`
- `init_project`
- `scaffold_template`
- `validate_project`
- `package_project`
- `fomod_tool`
- `extract_mo2_resources`
- `check_project`
- `find_entrypoints`
- `find_references`
- `link_user_reference`
- `luac_tool`
- `quality_scan`
- `xml_localization_tool`
- `query_hints`
- `map_subsystems`
- `check_overlay`

## References

Load only what the task needs:

- `references/source-priority.md`
- `references/project-toolchain.md`
- `references/mod-organizer2-and-fomod.md`
- `references/modding-book-practices.md`
- `references/dxml-and-dltx.md`
- `references/localization-and-encodings.md`
- `references/mcm-menu.md`
- `references/mod-structure-and-load-order.md`
- `references/runtime-model.md`
- `references/lua-api-map.md`
- `references/callbacks-and-binders.md`
- `references/save-safety.md`
- `references/performance-hotpaths.md`
- `references/weapons-and-hud.md`
- `references/visible-body-and-legs.md`
- `references/ui-xml-mcm.md`
- `references/tasks-story-alife.md`
- `references/engine-quirks.md`
- `references/manual-qa.md`
- `references/assets-and-animations.md`
- `references/mapping-and-sdk.md`
- `references/bootstrap-and-deps.md`
- `references/luac-and-syntax-checks.md`
- `references/repos/xray-monolith.md`
- `references/repos/anomaly-modding-book.md`

## Helper Scripts

- `scripts/scan_workspace.sh` scans for mod roots, local refs, overlays, and mixed-workbench signals
- `scripts/scan_workspace.py` is the cross-platform entrypoint
- `scripts/find_entrypoints.sh` finds callbacks, binders, registrators, and monkey-patch signals
- `scripts/find_entrypoints.py` is the cross-platform entrypoint
- `scripts/find_references.py` searches only the relevant `ai_workspace` roots for a task
- `scripts/link_user_reference.py` links user-local refs into `ai_workspace/user references`
- `scripts/extract_mo2_resources.py` extracts MO2 `mods/*` `configs/` and `scripts/` payloads into one flat reference overlay.
- `scripts/bootstrap_env.sh` and `scripts/bootstrap_env.ps1` install missing local dependencies when practical
- `scripts/luac_tool.py` detects and uses `luac` for syntax checks
- `scripts/quality_scan.py` reports Anomaly-specific static quality issues, risk score, vanilla delta, patch opportunities, conflict surface, dependency graph, and task gates
- `scripts/quality_scan.py graph`, `suggest-patch`, `save-template`, and `optional-pattern` cover advanced review, patch reduction, save migration, and optional dependency templates
- `scripts/xml_localization_tool.py` inspects XML localization files, converts them to UTF-8 for editing, and restores their original encoding
- `scripts/fomod_tool.py` stages a simple `00 Core + fomod/` installer package for MO2-compatible distribution
- `scripts/map_subsystems.py` classifies files by subsystem and path patterns
- `scripts/check_overlay.py` validates `.codex-stalker/workspace.json` or `.codex-stalker/workspace.yml`
- `scripts/expertctl.py` runs the bundled Expertise Compiler against `.expertise/stalker-anomaly`
- `scripts/query_hints.py` prints search/reference hints plus quality gates, checklist items, quality scan commands, and task-specific final-answer contracts

Search and inspection helpers are read-only. Project scaffolding and packaging helpers intentionally write project artifacts.

## Output Contract

- Separate verified facts from inference.
- Prefer local file citations when the workspace contains the relevant code.
- Mark when confidence is lower due to missing local refs or remote-only evidence.
- State which source tier produced the answer when that materially affects reliability.
- For mod edits and reviews, include the task-specific output contract from `manifests/output_contracts.json`: touched files when applicable, source tier marker (`verified local`, `verified MCP`, or `inference`), validation run, runtime risks, and manual QA.
