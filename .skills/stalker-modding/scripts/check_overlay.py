#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from _skill_common import find_workspace_overlay


EXTERNAL_PATH_KINDS = {
    "logs_dir",
    "mo2_mods_dir",
    "gamedata_root",
    "external_mod_root",
}
REPO_SLUG_RE = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
DEFAULTS = {
    "game_family": "anomaly",
    "baseline": "anomaly_1_5_3_modded_exes",
    "workspace_type": "mixed_workbench",
    "notes_language": "ru",
    "active_modules": [],
    "reference_roots": [],
    "known_conflicts": [],
    "priority_subsystems": [],
    "qa_playbooks": [],
    "optional_systems": [],
    "external_paths": [],
    "known_reference_repos": [],
}

LIST_FIELDS = {
    "active_modules",
    "reference_roots",
    "known_conflicts",
    "priority_subsystems",
    "qa_playbooks",
    "optional_systems",
}


def fail(message: str) -> int:
    print(f"ERROR: {message}")
    return 1


def validate_external_paths(entries: object) -> str | None:
    if not isinstance(entries, list):
        return "external_paths must be a list"

    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"external_paths[{index}]"
        if not isinstance(entry, dict):
            return f"{prefix} must be an object"
        if set(entry) != {"id", "kind", "path", "label"}:
            return f"{prefix} must contain only id, kind, path, label"
        for key in ("id", "kind", "path", "label"):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                return f"{prefix}.{key} must be a non-empty string"
        if entry["id"] in seen_ids:
            return f"{prefix}.id must be unique"
        seen_ids.add(entry["id"])
        if entry["kind"] not in EXTERNAL_PATH_KINDS:
            return f"{prefix}.kind is invalid: {entry['kind']}"
        if not Path(entry["path"]).is_absolute():
            return f"{prefix}.path must be an absolute path"
    return None


def validate_known_reference_repos(entries: object) -> str | None:
    import re

    if not isinstance(entries, list):
        return "known_reference_repos must be a list"

    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"known_reference_repos[{index}]"
        if not isinstance(entry, dict):
            return f"{prefix} must be an object"
        if set(entry) != {"id", "repo", "mcp_server", "role"}:
            return f"{prefix} must contain only id, repo, mcp_server, role"
        for key in ("id", "repo", "mcp_server", "role"):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                return f"{prefix}.{key} must be a non-empty string"
        if entry["id"] in seen_ids:
            return f"{prefix}.id must be unique"
        seen_ids.add(entry["id"])
        if not re.fullmatch(REPO_SLUG_RE, entry["repo"]):
            return f"{prefix}.repo must match owner/repo"
    return None


def main() -> int:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = find_workspace_overlay(Path("."))
        if target is None:
            target = Path(".codex-stalker/workspace.json")
    if not target.exists():
        return fail(f"{target} not found")

    suffix = target.suffix.lower()
    if suffix == ".json":
        data = json.loads(target.read_text(encoding="utf-8")) or {}
    elif suffix in {".yml", ".yaml"}:
        try:
            import yaml
        except ModuleNotFoundError:
            return fail(
                f"{target} requires PyYAML. Prefer .codex-stalker/workspace.json in clean Windows environments."
            )
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    else:
        return fail(f"unsupported overlay format: {target}")
    if not isinstance(data, dict):
        return fail("overlay must be a YAML mapping")

    merged = dict(DEFAULTS)
    merged.update(data)

    for key in DEFAULTS:
        if key not in merged:
            return fail(f"missing field: {key}")

    for key in LIST_FIELDS:
        value = merged.get(key)
        if not isinstance(value, list):
            return fail(f"{key} must be a list")
        if not all(isinstance(item, str) for item in value):
            return fail(f"{key} must contain only strings")

    error = validate_external_paths(merged.get("external_paths"))
    if error:
        return fail(error)

    error = validate_known_reference_repos(merged.get("known_reference_repos"))
    if error:
        return fail(error)

    for key in set(DEFAULTS) - LIST_FIELDS - {"external_paths", "known_reference_repos"}:
        if not isinstance(merged.get(key), str):
            return fail(f"{key} must be a string")

    print("overlay: valid")
    for key in sorted(merged):
        print(f"{key}: {merged[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
