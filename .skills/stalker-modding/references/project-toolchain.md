# Project Toolchain

Use this file when the task is about creating, scaffolding, validating, packaging, or bootstrapping local projects inside `projects/`.

## Project Layout

- Every local project lives under `projects/<project-name>`.
- The project overlay is `projects/<project-name>/.codex-stalker/project.json`.
- The mod payload root is `projects/<project-name>/gamedata`.
- Loose packaging output lives under `projects/<project-name>/dist/<project-name>/gamedata`.
- Repo-tracked regression inputs live under `tests/fixtures/`, not under `projects/`.

## Commands

- `scripts/init_project.py --name <name> [--display-name <label>]`
  - create the project root
  - create `gamedata/`
  - create `.codex-stalker/project.json`
- `scripts/scaffold_template.py --project <name> --template <kind> ...`
  - scaffold one of the supported starter templates
- `scripts/check_project.py projects/<name>`
  - validate project metadata shape
- `scripts/import_mod.py --source <path> --name <name> [--display-name <label>]`
  - import an existing mod root or direct `gamedata/` folder into `projects/<name>`
- `scripts/validate_project.py --project <name>`
  - validate metadata plus scaffold outputs
- `scripts/package_project.py --project <name>`
  - build loose output only
- `scripts/fomod_tool.py --project <name> [--author ... --version ...]`
  - build a simple `00 Core + fomod/` distribution package under `dist/<project-name>-fomod`
- `scripts/bootstrap_workspace.sh` / `.ps1`
  - ensure local tooling and run repo-local smoke checks
- `scripts/run_regressions.py [--suite <name>] [--json]`
  - run deterministic repo-local regression suites against canonical fixtures and temporary projects

## Supported Templates In V1

- `lua_feature`
- `lua_mcm`
- `localization_pack`
- `dltx_patch`
- `dxml_patch`

## Defaults

- Project metadata is JSON only in v1.
- `mod_root` stays `gamedata`.
- Artifact defaults are loose packaging on, zip packaging off.
- Lua and MCM starter names default from a normalized project identifier.
- If a default `lua_mcm` runtime name collides with an existing project script, the scaffold falls back to `<name>_runtime` while keeping the menu script at `*_mcm.script`.
- If a `lua_mcm` stem already ends with `_mcm`, that stem is reserved for the menu script and the runtime script gets `_runtime`.
- `lua_mcm` and `localization_pack` scaffolds create `eng` UTF-8 XML and `rus` `windows-1251` XML.

## Workflow Defaults

1. Run `init_project.py`.
2. If starting from an existing mod, choose `import_mod.py` instead of a blank scaffold.
3. Run one or more `scaffold_template.py` commands when a blank or partially blank project needs starter payloads.
4. Edit inside the project root unless the user explicitly requested in-place edits.
5. Run `validate_project.py`.
6. Run `package_project.py` when a loose overlay is needed.
7. Run `fomod_tool.py` when the user wants a FOMOD installer package.
8. Run `run_regressions.py` when you need deterministic repo-local reliability coverage for the workbench itself.

## Safety Rules

- Do not hand-edit `project.json` into an invalid shape; use the scaffold commands where possible.
- Do not place project-owned mod files at the repo root.
- Do not keep repo-tracked smoke projects under `projects/`; use `tests/fixtures` plus temporary projects instead.
- Do not package from mixed workspace state; package from `projects/<name>/gamedata` only.
- Do not treat MO2 `overwrite/` output as the authored source of truth; build packages from the project root.
- Do not use the project toolchain to mutate user-global Codex configuration in v1.
