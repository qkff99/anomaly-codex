#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from _project_toolchain import (
    default_project_metadata,
    project_root_from_name,
    require_valid_project_name,
    write_project,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a new local STALKER modding project under projects/<name>.")
    parser.add_argument("--name", required=True, help="Project directory name.")
    parser.add_argument("--display-name", help="Human-facing display name stored in project metadata.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_valid_project_name(args.name)

    project_root = project_root_from_name(args.name).resolve()
    if project_root.exists():
        print(f"project already exists: {project_root}")
        return 1

    (project_root / "gamedata").mkdir(parents=True, exist_ok=False)
    metadata = default_project_metadata(args.name, args.display_name)
    metadata_path = write_project(project_root, metadata)

    print(f"project_root: {project_root}")
    print(f"metadata: {metadata_path}")
    print(f"mod_root: {project_root / 'gamedata'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
