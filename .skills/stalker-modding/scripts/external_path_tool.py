#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from _skill_common import load_workspace_overlay_data, save_workspace_overlay_data


EXTERNAL_PATH_KINDS = {
    "logs_dir",
    "mo2_mods_dir",
    "gamedata_root",
    "external_mod_root",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage remembered external paths in the tracked workspace overlay. "
            "Only store paths after the user explicitly approved remembering them."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List remembered external paths.")

    remember = subparsers.add_parser(
        "remember",
        help="Remember an external path in the workspace overlay after explicit user approval.",
    )
    remember.add_argument("--id", required=True, help="Stable identifier for the path.")
    remember.add_argument("--kind", required=True, choices=sorted(EXTERNAL_PATH_KINDS), help="Kind of path to store.")
    remember.add_argument("--path", required=True, help="Absolute filesystem path.")
    remember.add_argument("--label", required=True, help="Human-facing label.")

    forget = subparsers.add_parser("forget", help="Remove a remembered external path by id.")
    forget.add_argument("--id", required=True, help="Stable identifier to remove.")

    return parser


def load_overlay() -> tuple[Path, dict]:
    overlay_path, data = load_workspace_overlay_data()
    if not isinstance(data, dict):
        raise ValueError(f"workspace overlay must be an object: {overlay_path}")
    data.setdefault("external_paths", [])
    return overlay_path, data


def command_list() -> int:
    overlay_path, data = load_overlay()
    print(f"overlay: {overlay_path}")
    entries = data.get("external_paths", [])
    if not entries:
        print("external_paths: none")
        return 0

    for entry in entries:
        path = Path(str(entry["path"]))
        status = "exists" if path.exists() else "missing"
        print(f"{entry['id']}: {entry['kind']} [{status}] {path} :: {entry['label']}")
    return 0


def command_remember(args: argparse.Namespace) -> int:
    overlay_path, data = load_overlay()
    path = Path(args.path).expanduser().resolve()
    if not path.is_absolute():
        print("--path must be absolute")
        return 1

    entries = data.setdefault("external_paths", [])
    assert isinstance(entries, list)
    if any(isinstance(entry, dict) and entry.get("id") == args.id for entry in entries):
        print(f"external path id already exists: {args.id}")
        return 1

    entries.append(
        {
            "id": args.id,
            "kind": args.kind,
            "path": str(path),
            "label": args.label,
        }
    )
    save_workspace_overlay_data(data)
    print(f"overlay: {overlay_path}")
    print(f"remembered: {args.id} -> {path}")
    return 0


def command_forget(args: argparse.Namespace) -> int:
    overlay_path, data = load_overlay()
    entries = data.setdefault("external_paths", [])
    assert isinstance(entries, list)
    filtered = [entry for entry in entries if not (isinstance(entry, dict) and entry.get("id") == args.id)]
    if len(filtered) == len(entries):
        print(f"external path id not found: {args.id}")
        return 1
    data["external_paths"] = filtered
    save_workspace_overlay_data(data)
    print(f"overlay: {overlay_path}")
    print(f"forgot: {args.id}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "list":
        return command_list()
    if args.command == "remember":
        return command_remember(args)
    if args.command == "forget":
        return command_forget(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
