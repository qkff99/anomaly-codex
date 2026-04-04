#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from _skill_common import REPO_ROOT, is_within


DEFAULT_TARGET_ROOT = REPO_ROOT / "ai_workspace" / "user references"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a link inside ai_workspace/user references to an external local reference."
    )
    parser.add_argument("source", nargs="+", help="Source file or directory to link into ai_workspace/user references.")
    parser.add_argument(
        "--name",
        help="Override destination name. Only valid when linking a single source.",
    )
    parser.add_argument(
        "--target-root",
        default=str(DEFAULT_TARGET_ROOT),
        help="Target root for linked references (defaults to ai_workspace/user references).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the planned link without creating it.")
    return parser.parse_args()


def ensure_valid_source(source: Path, target_root: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"source not found: {source}")
    if is_within(source.resolve(), target_root.resolve()):
        raise ValueError(f"source is already inside user references: {source}")


def create_windows_link(source: Path, target: Path) -> str:
    try:
        target.symlink_to(source, target_is_directory=source.is_dir())
        return "symlink"
    except OSError:
        if source.is_dir():
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(target), str(source)],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                return "junction"
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "mklink /J failed")
        try:
            os.link(str(source), str(target))
            return "hardlink"
        except OSError as exc:
            raise RuntimeError(
                "failed to create a file link on Windows; enable Developer Mode for symlinks or use a same-volume file for hardlink fallback"
            ) from exc


def create_link(source: Path, target: Path) -> str:
    if os.name == "nt":
        return create_windows_link(source, target)
    target.symlink_to(source, target_is_directory=source.is_dir())
    return "symlink"


def main() -> int:
    args = parse_args()
    if args.name and len(args.source) != 1:
        print("--name can only be used with a single source")
        return 1

    target_root = Path(args.target_root).expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    for raw_source in args.source:
        source = Path(raw_source).expanduser().resolve()
        ensure_valid_source(source, target_root)
        target_name = args.name if args.name else source.name
        target = target_root / target_name
        if target.exists() or target.is_symlink():
            print(f"target already exists: {target}")
            return 1

        if args.dry_run:
            print(f"dry-run: {target} -> {source}")
            continue

        link_type = create_link(source, target)
        print(f"created {link_type}: {target} -> {source}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
