#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

from _project_toolchain import load_json, project_metadata_summary, validate_project_metadata
from _skill_common import (
    REPO_ROOT,
    find_project_overlay,
    find_workspace_overlay,
    is_within,
    load_manifest,
    workspace_external_paths,
    workspace_known_reference_repos,
)


def find_sorted(
    root: Path,
    *,
    max_depth: int,
    want_file: bool | None = None,
    name: str | None = None,
    excluded_roots: tuple[Path, ...] = (),
):
    root = root.resolve()
    root_depth = len(root.parts)
    results: list[Path] = []
    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)
        if any(is_within(current_path, excluded_root) for excluded_root in excluded_roots):
            dirs[:] = []
            continue
        depth = len(current_path.parts) - root_depth
        if depth >= max_depth:
            dirs[:] = []
        else:
            dirs[:] = sorted(dirs)
        if want_file is not False:
            for file_name in sorted(files):
                path = current_path / file_name
                if name is None or path.name == name:
                    results.append(path)
        if want_file is not True:
            for dir_name in sorted(dirs):
                path = current_path / dir_name
                if name is None or path.name == name:
                    results.append(path)
    return sorted(path.resolve() for path in results)


def print_section(title: str, rows: list[str]) -> None:
    print(f"[{title}]")
    if rows:
        for row in rows:
            print(row)
    else:
        print("none")
    print()


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    manifest = load_manifest("reference_roots")
    root_specs = manifest.get("roots", {})

    overlay = find_workspace_overlay(root)
    notes_dir = root / "help" / "stalker"
    notes = find_sorted(notes_dir, max_depth=2, want_file=True) if notes_dir.exists() else []

    skill_files = find_sorted(root / ".skills", max_depth=3, want_file=True, name="SKILL.md") if (root / ".skills").exists() else []
    plugin_files = (
        find_sorted(root / "plugins", max_depth=4, want_file=True, name="plugin.json")
        if (root / "plugins").exists()
        else []
    )
    plugin_files = [path for path in plugin_files if path.parent.name == ".codex-plugin"]
    marketplace = root / ".agents" / "plugins" / "marketplace.json"

    codex_assets: list[str] = []
    codex_assets.extend(str(path) for path in skill_files)
    codex_assets.extend(str(path) for path in plugin_files)
    if marketplace.exists():
        codex_assets.append(str(marketplace.resolve()))

    reference_rows: list[str] = []
    reference_paths: dict[str, Path] = {}
    for root_name, spec in sorted(root_specs.items()):
        if root_name == "workspace":
            continue
        candidate = (REPO_ROOT / spec["path"]).resolve()
        if candidate.exists():
            reference_paths[root_name] = candidate
            reference_rows.append(f"{root_name}: {candidate}")
        else:
            reference_rows.append(f"{root_name}: missing ({candidate})")

    user_reference_entries: list[str] = []
    user_reference_root = reference_paths.get("user_references")
    if user_reference_root and user_reference_root.exists():
        for path in sorted(user_reference_root.iterdir()):
            if path.name.startswith("."):
                continue
            if path.is_symlink():
                kind = "symlink-dir" if path.is_dir() else "symlink-file"
                user_reference_entries.append(f"{path} [{kind}] -> {path.resolve()}")
            else:
                kind = "dir" if path.is_dir() else "file"
                user_reference_entries.append(f"{path} [{kind}]")

    project_rows: list[str] = []
    project_dist_roots: list[Path] = []
    project_metadata_files = []
    projects_dir = root / "projects"
    if projects_dir.exists():
        project_metadata_files = find_sorted(projects_dir, max_depth=3, want_file=True, name="project.json")
    for metadata_path in project_metadata_files:
        if metadata_path.parent.name != ".codex-stalker":
            continue
        project_root = metadata_path.parent.parent
        project_dist_roots.append(project_root / "dist")
        try:
            metadata = load_json(metadata_path)
            errors = validate_project_metadata(metadata)
            if errors:
                summary = f"{project_root.resolve()} [invalid: {'; '.join(errors)}]"
            else:
                summary = project_metadata_summary(project_root, metadata)
        except (OSError, ValueError) as exc:
            summary = f"{project_root.resolve()} [invalid: {exc}]"
        project_rows.append(summary)

    excluded_reference_roots = tuple(reference_paths.values()) + tuple(
        path.resolve() for path in project_dist_roots if path.exists()
    )
    fixtures_root = (root / "tests" / "fixtures").resolve()
    if fixtures_root.exists():
        excluded_reference_roots = excluded_reference_roots + (fixtures_root,)
    gamedata_paths = find_sorted(
        root,
        max_depth=5,
        want_file=False,
        name="gamedata",
        excluded_roots=excluded_reference_roots,
    )
    gamedata_rows = [f"{path} [workspace]" for path in gamedata_paths]
    project_gamedata_count = len(gamedata_rows)

    module_paths = []
    for file_name in ("meta.ini", "addon.json"):
        module_paths.extend(
            find_sorted(
                root,
                max_depth=4,
                want_file=True,
                name=file_name,
                excluded_roots=excluded_reference_roots,
            )
        )
    module_paths.extend(
        path
        for path in find_sorted(root, max_depth=4, want_file=True, excluded_roots=excluded_reference_roots)
        if path.name.startswith("mod_") and path.suffix.lower() == ".ltx"
    )
    module_rows = [f"{path} [workspace]" for path in sorted({entry.resolve() for entry in module_paths})]
    project_module_count = len(module_rows)

    if codex_assets and project_rows:
        workspace_type = "skill_workbench_with_projects"
    elif codex_assets and project_gamedata_count == 0 and project_module_count == 0:
        workspace_type = "skill_workbench"
    elif codex_assets and project_gamedata_count <= 1 and project_module_count == 0:
        workspace_type = "skill_workbench_with_local_refs"
    elif project_gamedata_count > 1 or project_module_count > 1:
        workspace_type = "mixed_workbench"
    elif project_gamedata_count == 1 or project_module_count == 1:
        workspace_type = "single_module_or_unknown"
    else:
        workspace_type = "unknown"

    print(f"workspace: {root}")
    print()

    overlay_rows = []
    agents_md = root / "AGENTS.md"
    overlay_rows.append(f"agents_md: {agents_md.resolve()}" if agents_md.exists() else "agents_md: missing")
    overlay_rows.append(f"workspace_overlay: {overlay.resolve()}" if overlay else "workspace_overlay: missing")
    project_overlay = find_project_overlay(root)
    overlay_rows.append(f"project_overlay: {project_overlay.resolve()}" if project_overlay else "project_overlay: none")
    print_section("overlay", overlay_rows)
    print_section("project_notes", [str(path) for path in notes])
    print_section("codex_assets", codex_assets)
    print_section("reference_roots", reference_rows)
    print_section("user_reference_entries", user_reference_entries)
    external_path_rows: list[str] = []
    for entry in workspace_external_paths(root):
        raw_path = entry.get("path")
        if not isinstance(raw_path, str):
            continue
        candidate = Path(raw_path).expanduser()
        status = "exists" if candidate.exists() else "missing"
        external_path_rows.append(
            f"{entry.get('id')}: {entry.get('kind')} [{status}] {candidate} :: {entry.get('label')}"
        )
    print_section("external_paths", external_path_rows)
    known_repo_rows = [
        f"{entry.get('id')}: {entry.get('repo')} [{entry.get('role')}] -> {entry.get('mcp_server')}"
        for entry in workspace_known_reference_repos(root)
    ]
    print_section("known_reference_repos", known_repo_rows)
    print_section("projects", project_rows)
    print_section("gamedata_roots", gamedata_rows)
    print_section("module_hints", module_rows)
    print("[workspace_type_guess]")
    print(workspace_type)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
