#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from _project_toolchain import (
    default_project_metadata,
    packaging_ignore_entries,
    project_root_from_name,
    require_valid_project_name,
    write_project,
)


SOURCE_KINDS = ("auto", "mod_root", "gamedata_root")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import an existing mod copy into projects/<name>.")
    parser.add_argument("--source", required=True, help="Existing mod root or gamedata folder.")
    parser.add_argument("--name", required=True, help="New project directory name under projects/.")
    parser.add_argument("--display-name", help="Human-facing display name stored in project metadata.")
    parser.add_argument(
        "--source-kind",
        default="auto",
        choices=SOURCE_KINDS,
        help="Treat the source as a full mod root or direct gamedata root.",
    )
    return parser.parse_args()


def detect_source_kind(source: Path, requested_kind: str) -> str:
    if requested_kind != "auto":
        return requested_kind
    if (source / "gamedata").is_dir():
        return "mod_root"
    if source.is_dir() and source.name.lower() == "gamedata":
        return "gamedata_root"
    raise ValueError("could not detect source kind; use --source-kind mod_root or gamedata_root")


def copy_mod_root(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=packaging_ignore_entries, dirs_exist_ok=False)


def copy_gamedata_root(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, target / "gamedata", ignore=packaging_ignore_entries, dirs_exist_ok=False)


def main() -> int:
    args = parse_args()
    require_valid_project_name(args.name)

    source = Path(args.source).expanduser().resolve()
    if not source.exists() or not source.is_dir():
        print(f"source must be an existing directory: {source}")
        return 1

    kind = detect_source_kind(source, args.source_kind)
    if kind == "mod_root" and not (source / "gamedata").is_dir():
        print(f"mod_root source must contain gamedata/: {source}")
        return 1
    if kind == "gamedata_root" and source.name.lower() != "gamedata":
        print(f"gamedata_root source must be a directory named gamedata: {source}")
        return 1

    project_root = project_root_from_name(args.name).resolve()
    if project_root.exists():
        print(f"project already exists: {project_root}")
        return 1

    if kind == "mod_root":
        copy_mod_root(source, project_root)
    else:
        copy_gamedata_root(source, project_root)

    metadata = default_project_metadata(args.name, args.display_name)
    metadata["source"] = {
        "mode": "imported_copy",
        "kind": kind,
        "origin_path": str(source),
    }
    metadata_path = write_project(project_root, metadata)

    print(f"project_root: {project_root}")
    print(f"metadata: {metadata_path}")
    print(f"source_kind: {kind}")
    print(f"origin_path: {source}")
    print(f"mod_root: {project_root / 'gamedata'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
