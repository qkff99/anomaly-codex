# Existing Mod Workflow

Use this file when the user wants to fix, adapt, configure, or extend an existing mod instead of creating a new one from scratch.

## Default Choice

Always ask which mode to use:

- copy the mod into `projects/`
- or edit it in place

Recommend copy-to-`projects` by default because it is safer and keeps authored changes isolated.

## Copy Mode

Use `scripts/import_mod.py --source <path> --name <project-name>`.

- If the source contains `gamedata/`, treat it as a mod root and import the whole tree.
- If the source itself is a `gamedata/` folder, import it into `projects/<name>/gamedata`.
- Imported projects record their origin in `projects/<name>/.codex-stalker/project.json`.

## In-Place Mode

- Use only when the user explicitly wants direct edits or the change is narrow enough to justify it.
- Do not force project creation for path-based in-place work.
- Be explicit that the target path becomes the live source of truth for that task.

## Reference Paths

If implementation needs comparison against installed mods or modpacks:

- ask for MO2 `mods/` when the user uses MO2
- ask for unpacked `gamedata/` when the user does not use MO2
- remember confirmed paths with `scripts/external_path_tool.py` only after the user explicitly allows it

If a specific external folder will be reused often, it can also be linked into `ai_workspace/user references`.
