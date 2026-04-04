# Mod Organizer 2 And FOMOD

Use this file when the task is about MO2-aware distribution, directory layout assumptions, or building a basic FOMOD installer.

## MO2 Mental Model

- MO2 does not normally author mods inside the game directory.
- Mods live in separate mod directories and are merged into the launched game through a virtual file system layer.
- External tools should treat MO2 as a deployment and launch surface, not as the canonical authoring root for project files.

## Directories That Matter

- `mods/`
  - installed mod payloads live here as separate mod folders
  - for authored projects, this is usually the destination after packaging, not the source of truth
- `profiles/`
  - profile-specific state such as enabled mods, ordering, and profile-local configuration
  - do not treat this as mod content storage
- `overwrite/`
  - transient sink for unmanaged tool output
  - useful for debugging or triage, but not a stable authoring root
  - if something important lands here, move it into a real mod or project-owned folder
- `downloads/`
  - download cache, not install state and not authored mod content

## Path Assumptions To Avoid

- Do not hardcode one global MO2 base path.
- Portable setups and instance-managed setups can place the instance data in different locations.
- Do not assume the MO2 install directory, `mods/`, `profiles/`, and `downloads/` all share one fixed layout unless the user has confirmed it.
- Ask for explicit paths or treat them as user-supplied configuration when a task depends on a live MO2 instance.
- When the same MO2 instance will be reused, remember its `mods/` path with `external_path_tool.py` only after the user explicitly approved remembering it.

## STALKER Workspace Rule

- Keep authored files under `projects/<project-name>/gamedata/...`.
- Use `package_project.py` to stage a loose overlay.
- Use `fomod_tool.py` when the user explicitly wants a FOMOD installer package.
- Do not treat MO2 `overwrite/` or an already-installed `mods/<name>` folder as the project source of truth.

## FOMOD Rule Of Thumb

- A FOMOD package is a distribution wrapper, not the authoring format.
- For this workspace, the safe default is a core-only installer:
  - package root contains `00 Core/`
  - `00 Core/` contains the project payload such as `gamedata/...`
  - package root also contains `fomod/info.xml`
  - package root also contains `fomod/ModuleConfig.xml`
- The default generated installer should install the contents of `00 Core/` as required files.

## When To Use FOMOD

- Use FOMOD when the user explicitly asks for a mod-manager-friendly installer package.
- Use loose packaging when the user only needs a `gamedata/` overlay for local testing or manual deployment.
- Do not introduce FOMOD by default when the user only asked for code or config changes.

## Practical Defaults For This Skill

- Prefer a single required core package before offering optional groups.
- Preserve the internal STALKER payload layout under `gamedata/...`.
- Keep FOMOD metadata simple unless the user asks for variants, options, dependencies, or images.
- If optional install variants are requested later, split them into extra top-level folders such as `01 Optional ...`, then extend `ModuleConfig.xml`.

## Primary References

- Official MO2 repo: `ModOrganizer2/modorganizer`
- MO2 architecture summary from indexed repo context: VFS, profile system, installation pipeline, and settings layout
- FOMOD format docs for `info.xml` and `ModuleConfig.xml`: `fomod-docs.readthedocs.io`
