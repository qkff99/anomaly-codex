# Anomaly Codex Workbench

Russian version: [README_RU.MD](README_RU.MD)

Repo-local Codex skill/plugin workbench for S.T.A.L.K.E.R. Anomaly 1.5.3 modding.

This repository is meant to be opened directly in Codex or VS Code. It provides:
- a local STALKER modding skill
- repo-local MCP config for DeepWiki and GitMCP references
- helper scripts for project creation, import, validation, packaging, FOMOD staging, XML encodings, and crash-log triage

`AGENTS.md` and `.skills/stalker-modding/SKILL.md` remain the source of truth for the agent. This README is the human quickstart.

## Codex Access And Limits

- Codex can currently be tried from ChatGPT Free and Go for a limited time, while Plus, Pro, Business, and Enterprise/Edu have broader included access.
- Do not assume "free" means unlimited. Codex usage is capped by plan limits, and larger tasks, bigger codebases, long sessions, cloud work, and higher-reasoning runs consume the allowance faster.
- If someone is new to Codex, warn them up front that limits can disappear quickly on real coding work so they are not surprised.
- Official references:
  - plan/access overview: https://help.openai.com/en/articles/11369540
  - rate card / credits overview: https://help.openai.com/en/articles/20001106-codex-rate-card

## Quick Setup

1. Download this repository and unpack it into a normal working folder on disk.
   You can use a ZIP download of the repo or your usual Git workflow. The important part is that Codex opens the unpacked repository folder itself, not a nested subfolder.

2. Install Codex in one of these ways:
   - Codex CLI:
     - official getting started: https://help.openai.com/en/articles/11096431-openai-codex-ci-getting-started
     - Codex docs overview: https://platform.openai.com/docs/codex
   - Codex Desktop app:
     - official product announcement: https://openai.com/index/introducing-the-codex-app
     - Codex product page: https://openai.com/codex
   - Codex in VS Code:
     - OpenAI help overview for Codex availability in VS Code: https://help.openai.com/en/articles/11369540
     - Codex product/docs overview: https://platform.openai.com/docs/guides/code-generation

3. Open the unpacked repository folder in Codex or in VS Code with Codex available.

4. In Codex settings, install the repo-local plugin if Codex offers it.
   In this repository it is exposed as the workspace plugin `Anomaly Codex Workspace` / `stalker-modding-workbench`.

5. After the plugin is installed, ask Codex to initialize against this workspace or ask it what it can do now.
   Good starter prompts:
   - `Get oriented in this workspace and tell me what you can do now`
   - `Initialize yourself for working with this repo`
   - `What modding workflows and helper tools are available in this workspace?`

6. After that, run the first local checks:
   - WSL / Linux:

```bash
./.skills/stalker-modding/scripts/bootstrap_workspace.sh --run-regressions
```

   - PowerShell:

```powershell
.\.skills\stalker-modding\scripts\bootstrap_workspace.ps1 --run-regressions
```

## First Run

WSL / Linux:

```bash
./.skills/stalker-modding/scripts/bootstrap_workspace.sh
./.skills/stalker-modding/scripts/run_regressions.sh
```

PowerShell:

```powershell
.\.skills\stalker-modding\scripts\bootstrap_workspace.ps1
.\.skills\stalker-modding\scripts\run_regressions.ps1
```

If you want the quick readiness checks plus the full regression pass in one command:

WSL / Linux:

```bash
./.skills/stalker-modding/scripts/bootstrap_workspace.sh --run-regressions
```

PowerShell:

```powershell
.\.skills\stalker-modding\scripts\bootstrap_workspace.ps1 --run-regressions
```

## Project Workflow

Create a blank local project under `projects/<name>`:

```bash
python3 ./.skills/stalker-modding/scripts/init_project.py --name my_mod
python3 ./.skills/stalker-modding/scripts/scaffold_template.py --project my_mod --template lua_feature
python3 ./.skills/stalker-modding/scripts/validate_project.py --project my_mod
python3 ./.skills/stalker-modding/scripts/package_project.py --project my_mod
```

Import an existing mod copy into `projects/`:

```bash
python3 ./.skills/stalker-modding/scripts/import_mod.py --source /path/to/mod-or-gamedata --name imported_mod
```

If you want to edit an existing mod in place instead of copying it into `projects/`, provide the explicit target path and say that in-place edits are intended.

## Log Triage

Summarize a log file or a whole logs directory:

```bash
python3 ./.skills/stalker-modding/scripts/log_triage.py summarize /path/to/log/or/logs-dir
```

For recurring crash work, prefer remembering the path to MO2 `mods/` or unpacked `gamedata/` before remembering a `logs_dir`, because those paths help resolve the failing addon files. Remember external paths only with explicit user approval.

## Packaging And FOMOD

Loose package:

```bash
python3 ./.skills/stalker-modding/scripts/package_project.py --project my_mod
```

Basic core-only FOMOD package:

```bash
python3 ./.skills/stalker-modding/scripts/fomod_tool.py --project my_mod
```

## Repo Layout

- `projects/` is the user-owned work area for local mod projects
- `tests/fixtures/` contains repo-tracked regression inputs, not live mod projects
- `ai_workspace/` contains local reference material
- `.codex-stalker/workspace.json` stores workspace overlay data and remembered external paths
- `.vscode/mcp.json` mirrors the repo-local plugin MCP configuration

## Notes

- Use `ai_workspace/user references` for extra local references or linked external material.
- Russian localization XML is often `windows-1251`; use `xml_localization_tool.py` before editing legacy XML directly.
- MO2 is treated as a deployment surface, not the authoring root. Author in `projects/` first, then package for MO2 when needed.
