#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil

from _project_toolchain import load_project, packaging_ignore_entries, validate_project_metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package a project into a loose dist/<project>/gamedata overlay.")
    parser.add_argument("--project", required=True, help="Project name under projects/.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root, metadata = load_project(args.project)
    errors = validate_project_metadata(metadata)
    if errors:
        print("project metadata is invalid:")
        for error in errors:
            print(f"- {error}")
        return 1

    mod_root_name = str(metadata["mod_root"])
    source_root = project_root / mod_root_name
    if not source_root.exists():
        print(f"mod root not found: {source_root}")
        return 1

    artifact_defaults = metadata["artifact_defaults"]
    if not artifact_defaults.get("loose", True):
        print("loose packaging is disabled in artifact_defaults")
        return 1

    dist_root = project_root / "dist" / str(metadata["project_name"])
    target_root = dist_root / mod_root_name

    if dist_root.exists():
        shutil.rmtree(dist_root)
    dist_root.mkdir(parents=True, exist_ok=True)

    shutil.copytree(source_root, target_root, ignore=packaging_ignore_entries, dirs_exist_ok=True)

    print(f"source: {source_root}")
    print(f"packaged: {target_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
