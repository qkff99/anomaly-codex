---
name: stalker-modding
description: "Use when working on S.T.A.L.K.E.R./XRay modding tasks, especially Anomaly 1.5.3 + Modded Exes: Lua scripts, configs, UI XML, XML localization, crash-log triage, existing addon maintenance, HUD and weapons, callbacks, binders, save/load safety, engine capability lookup, mixed mod workbenches, and reference research."
---

# STALKER Modding

This repo-local plugin is a wrapper around the canonical workspace skill at `../../../../.skills/stalker-modding`.

Use this plugin wrapper only as the discovery and installation bridge for Codex. For actual workflow, load and follow:
- `../../../../.skills/stalker-modding/SKILL.md`
- `../../../../.codex-stalker/workspace.json`
- `../../../../help/stalker/*.md`

Canonical helper scripts and references also live in `../../../../.skills/stalker-modding/`.
User-added references should be stored in `../../../../ai_workspace/user references` and searched alongside the built-in local refs.
If the user asks, or if the agent decides extra local references are needed, create links there instead of copying big external folders into the repo.
Use `../../../../ai_workspace/Anomaly-Mod-Configuration-Menu-main` as the primary local authority for Anomaly MCM API, `*mcm.script` discovery, keybind widgets, and MCM-specific UI behavior.
Use `../../../../ai_workspace/GAMMA Scripts` as the local flattened GAMMA configs/scripts reference overlay for pack-specific addon behavior and conflict examples.
Use the plugin-local `graphify` skill and `../../../../.skills/stalker-modding/scripts/graphify_workspace.py` when large local corpora need subsystem mapping, Lua dependency routing, or vanilla/GAMMA/MCM cross-file orientation before raw file search.
Prefer existing graph artifacts at `../../../../ai_workspace/map_index.html`, `../../../../ai_workspace/lua-graphify-out`, and `../../../../ai_workspace/*/graphify-out` before rebuilding anything.
This workspace patches local `graphify` so `*.script` is treated as Lua for STALKER script mapping.
Before substantial task work, check `../../../../.codex-stalker/state/bootstrap_state.json`. If it is missing, stale, or `../../../../ai_workspace/lua-graphify-out/graph.json` is absent, run `../../../../.skills/stalker-modding/scripts/bootstrap_workspace.py` automatically instead of waiting for the user to ask.
Treat `../../../../.skills/stalker-modding/scripts/bootstrap_workspace.py` as the first-use bootstrap: it installs `graphifyy`, applies the local `.script` patch to the installed `graphify` package, builds `../../../../ai_workspace/lua-graphify-out`, builds focused subfolder maps under the Lua-bearing `ai_workspace` roots, refreshes `../../../../ai_workspace/map_index.html`, and records state under `../../../../.codex-stalker/state/bootstrap_state.json`.
When a task is already localized to one reference pack or one `ai_workspace` subfolder, prefer the corresponding focused `../../../../ai_workspace/**/graphify-out` map before falling back to the global workspace graph.
Default extension order is callbacks/config hooks first, then DXML, then DLTX, then narrow monkey patches, and full-file overrides only last.
Use `../../../../ai_workspace/vanilla scripts/gamedata/scripts/_g.script`, `lua_help.script`, and `axr_main.script` as the first orientation files when tracing vanilla script flow.
Project-local machine-readable metadata lives in `../../../../projects/<project-name>/.codex-stalker/project.json`.
If the user wants to edit an existing mod, ask whether to import a copy into `../../../../projects/<project-name>` or edit the provided path in place.
Use `../../../../.skills/stalker-modding/scripts/init_project.py`, `scaffold_template.py`, `check_project.py`, `validate_project.py`, `package_project.py`, `import_mod.py`, `extract_mo2_resources.py`, and `fomod_tool.py` for the repo-local project toolchain.
Use `../../../../.skills/stalker-modding/scripts/extract_mo2_resources.py` to flatten MO2 `mods/*` `configs/` and `scripts/` payloads into one reference overlay when the user wants bulk local references.
Use `../../../../.skills/stalker-modding/scripts/run_regressions.py` for deterministic repo-local reliability checks.
Use `../../../../.skills/stalker-modding/scripts/log_triage.py` before bringing huge Anomaly/XRay logs into context.
Use `../../../../.skills/stalker-modding/scripts/external_path_tool.py` to remember logs folders, MO2 `mods/`, unpacked `gamedata/`, or external mod roots in the tracked workspace overlay.
Use `../../../../.skills/stalker-modding/scripts/discover_github_refs.py` to search GitHub references and persist only curated high-signal repos.
Use `../../../../.skills/stalker-modding/scripts/luac_tool.py` to detect and syntax-check Lua files with `luac`.
Use `../../../../.skills/stalker-modding/scripts/graphify_workspace.py` to rebuild Lua-only graphify artifacts and refresh the workspace HTML index when graph-based routing is useful.
Use `../../../../.skills/stalker-modding/scripts/quality_scan.py` to scan projects/mod roots for static quality risks, task gates, vanilla delta, patch opportunities, conflict surface, dependency graphs, save migration templates, optional dependency patterns, and output-contract hints.
Use `../../../../.skills/stalker-modding/scripts/xml_localization_tool.py` to inspect XML localization encodings, convert legacy XML to UTF-8 for editing, and restore the original encoding afterward.
Use MO2 knowledge for packaging and deployment only: author from `projects/<project-name>` first, treat MO2 `overwrite/` as transient output, and build FOMOD installers only when the user asks.
Use `stalker-gamma` as a curated GitMCP repo for addon discovery and modpack composition, not as the primary authority on engine semantics.
If Python or other local tooling is missing, use `../../../../.skills/stalker-modding/scripts/bootstrap_env.sh` or `.ps1` to install dependencies before giving up.

When initializing a new local project in this workspace, create it in `../../../../projects/<project-name>`.
Treat `../../../../projects/` as user-owned workspace state; repo-tracked smoke inputs belong in `../../../../tests/fixtures`.

The plugin-local `.mcp.json` wires:
- `deepwiki`
- `xray-monolith`
- `anomaly-modding-book`
- `modorganizer2`
- `stalker-gamma`
