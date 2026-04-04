#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

from _project_toolchain import load_json, validate_project_metadata
from _skill_common import find_project_overlay


def fail(message: str) -> int:
    print(f"ERROR: {message}")
    return 1


def resolve_target() -> Path:
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1]).expanduser().resolve()
        if candidate.is_dir():
            return candidate / ".codex-stalker" / "project.json"
        return candidate

    overlay = find_project_overlay(Path.cwd())
    if overlay is not None:
        return overlay
    return Path(".codex-stalker/project.json").resolve()


def main() -> int:
    target = resolve_target()
    if not target.exists():
        return fail(f"{target} not found")
    if target.suffix.lower() != ".json":
        return fail(f"unsupported project metadata format: {target}")

    data = load_json(target)
    errors = validate_project_metadata(data)
    if errors:
        print("project: invalid")
        for error in errors:
            print(f"- {error}")
        return 1

    print("project: valid")
    for key in (
        "project_name",
        "display_name",
        "baseline",
        "mod_root",
        "source",
        "artifact_defaults",
        "languages",
        "templates",
    ):
        print(f"{key}: {data.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
