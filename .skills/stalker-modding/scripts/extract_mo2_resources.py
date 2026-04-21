#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RESOURCE_CANDIDATES = (
    (Path("gamedata") / "configs", "configs"),
    (Path("gamedata") / "scripts", "scripts"),
    (Path("configs"), "configs"),
    (Path("scripts"), "scripts"),
)
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__"}


@dataclass(frozen=True)
class ResourceFile:
    mod_name: str
    source: Path
    dest: Path
    output_kind: str
    relative_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract configs/ and scripts/ from every MO2 mods subfolder into one flat reference overlay."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="MO2 mods directory, or an MO2 instance root containing a mods/ directory.",
    )
    parser.add_argument(
        "--dest",
        required=True,
        help="Destination directory. Files are copied into dest/configs and dest/scripts.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite destination files on conflicts. Without this, the first file wins and conflicts are reported.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report planned copies without writing files.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument(
        "--include-hidden",
        action="store_true",
        help="Include hidden mod folders and hidden nested folders.",
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symlinked directories while scanning resource folders.",
    )
    parser.add_argument(
        "--fail-on-conflict",
        action="store_true",
        help="Return exit code 2 when different files target the same destination path.",
    )
    parser.add_argument("--write-report", help="Optional path for a JSON report file.")
    return parser.parse_args()


def path_for_report(path: Path) -> str:
    return path.as_posix()


def detect_mods_root(source: Path) -> tuple[Path, str]:
    if not source.exists() or not source.is_dir():
        raise ValueError(f"source must be an existing directory: {source}")
    if source.name.casefold() == "mods":
        return source.resolve(), "mods_dir"
    nested = source / "mods"
    if nested.is_dir():
        return nested.resolve(), "mo2_root"
    return source.resolve(), "mods_dir"


def iter_mod_dirs(mods_root: Path, *, include_hidden: bool) -> list[Path]:
    mod_dirs: list[Path] = []
    for child in mods_root.iterdir():
        if not child.is_dir():
            continue
        if not include_hidden and child.name.startswith("."):
            continue
        mod_dirs.append(child)
    return sorted(mod_dirs, key=lambda path: path.name.casefold())


def iter_files(root: Path, *, include_hidden: bool, follow_symlinks: bool):
    for current_root, dirs, files in os.walk(root, followlinks=follow_symlinks):
        dirs[:] = [
            name
            for name in sorted(dirs, key=str.casefold)
            if name not in SKIP_DIRS and (include_hidden or not name.startswith("."))
        ]
        for name in sorted(files, key=str.casefold):
            if not include_hidden and name.startswith("."):
                continue
            yield Path(current_root) / name


def find_resource_files(
    mods_root: Path,
    dest_root: Path,
    *,
    include_hidden: bool,
    follow_symlinks: bool,
) -> tuple[list[Path], list[Path], list[ResourceFile]]:
    mod_dirs = iter_mod_dirs(mods_root, include_hidden=include_hidden)
    mods_with_resources: list[Path] = []
    files: list[ResourceFile] = []

    for mod_dir in mod_dirs:
        seen_resource_roots: set[Path] = set()
        found_in_mod = False
        for relative_root, output_kind in RESOURCE_CANDIDATES:
            resource_root = mod_dir / relative_root
            if not resource_root.is_dir():
                continue
            resolved_resource_root = resource_root.resolve()
            if resolved_resource_root in seen_resource_roots:
                continue
            seen_resource_roots.add(resolved_resource_root)
            found_in_mod = True
            for source_file in iter_files(
                resource_root,
                include_hidden=include_hidden,
                follow_symlinks=follow_symlinks,
            ):
                if not source_file.is_file():
                    continue
                relative_path = source_file.relative_to(resource_root)
                files.append(
                    ResourceFile(
                        mod_name=mod_dir.name,
                        source=source_file,
                        dest=dest_root / output_kind / relative_path,
                        output_kind=output_kind,
                        relative_path=relative_path,
                    )
                )
        if found_in_mod:
            mods_with_resources.append(mod_dir)

    files.sort(
        key=lambda item: (
            item.mod_name.casefold(),
            item.output_kind,
            item.relative_path.as_posix().casefold(),
            item.source.as_posix().casefold(),
        )
    )
    return mod_dirs, mods_with_resources, files


def same_file_bytes(left: Path, right: Path) -> bool:
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_file, right.open("rb") as right_file:
            while True:
                left_chunk = left_file.read(1024 * 1024)
                right_chunk = right_file.read(1024 * 1024)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    return True
    except OSError:
        return False


def source_ref(item: ResourceFile) -> str:
    return f"{item.mod_name}:{item.source.as_posix()}"


def copy_resource(source: Path, dest: Path, *, dry_run: bool) -> None:
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def append_event(events: dict[str, list[dict[str, Any]]], name: str, item: ResourceFile, **extra: Any) -> None:
    payload: dict[str, Any] = {
        "mod": item.mod_name,
        "source": path_for_report(item.source),
        "dest": path_for_report(item.dest),
        "kind": item.output_kind,
        "relative_path": item.relative_path.as_posix(),
    }
    payload.update(extra)
    events[name].append(payload)


def extract_resources(
    *,
    source: Path,
    dest: Path,
    overwrite: bool,
    dry_run: bool,
    include_hidden: bool,
    follow_symlinks: bool,
) -> dict[str, Any]:
    mods_root, source_kind = detect_mods_root(source)
    dest_root = dest.expanduser().resolve()

    mod_dirs, mods_with_resources, resource_files = find_resource_files(
        mods_root,
        dest_root,
        include_hidden=include_hidden,
        follow_symlinks=follow_symlinks,
    )

    events: dict[str, list[dict[str, Any]]] = {
        "copied": [],
        "overwritten": [],
        "duplicates_same": [],
        "preexisting_same": [],
        "conflicts": [],
        "skipped_conflicts": [],
    }
    selected_by_dest: dict[Path, ResourceFile] = {}

    for item in resource_files:
        previous_item = selected_by_dest.get(item.dest)
        if previous_item is not None:
            if same_file_bytes(previous_item.source, item.source):
                append_event(events, "duplicates_same", item, existing_source=source_ref(previous_item))
                continue

            resolution = "overwritten" if overwrite else "skipped"
            append_event(
                events,
                "conflicts",
                item,
                existing_source=source_ref(previous_item),
                resolution=resolution,
            )
            if overwrite:
                copy_resource(item.source, item.dest, dry_run=dry_run)
                selected_by_dest[item.dest] = item
                append_event(events, "overwritten", item, previous_source=source_ref(previous_item))
            else:
                append_event(events, "skipped_conflicts", item, existing_source=source_ref(previous_item))
            continue

        if item.dest.exists():
            if same_file_bytes(item.source, item.dest):
                selected_by_dest[item.dest] = item
                append_event(events, "preexisting_same", item)
                continue

            resolution = "overwritten" if overwrite else "skipped"
            append_event(
                events,
                "conflicts",
                item,
                existing_source="preexisting destination file",
                resolution=resolution,
            )
            if overwrite:
                copy_resource(item.source, item.dest, dry_run=dry_run)
                selected_by_dest[item.dest] = item
                append_event(events, "overwritten", item, previous_source="preexisting destination file")
            else:
                append_event(events, "skipped_conflicts", item, existing_source="preexisting destination file")
            continue

        copy_resource(item.source, item.dest, dry_run=dry_run)
        selected_by_dest[item.dest] = item
        append_event(events, "copied", item)

    missing_resource_mods = [path.name for path in mod_dirs if path not in set(mods_with_resources)]
    summary = {
        "source": str(source.expanduser().resolve()),
        "source_kind": source_kind,
        "mods_root": str(mods_root),
        "dest": str(dest_root),
        "dry_run": dry_run,
        "overwrite": overwrite,
        "mods_scanned": len(mod_dirs),
        "mods_with_resources": len(mods_with_resources),
        "mods_without_resources": len(missing_resource_mods),
        "files_seen": len(resource_files),
        "copied": 0 if dry_run else len(events["copied"]),
        "would_copy": len(events["copied"]) if dry_run else 0,
        "overwritten": 0 if dry_run else len(events["overwritten"]),
        "would_overwrite": len(events["overwritten"]) if dry_run else 0,
        "duplicates_same": len(events["duplicates_same"]),
        "preexisting_same": len(events["preexisting_same"]),
        "conflicts": len(events["conflicts"]),
        "skipped_conflicts": len(events["skipped_conflicts"]),
    }
    return {
        "summary": summary,
        "missing_resource_mods": missing_resource_mods,
        "events": events,
    }


def print_text_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    for key in (
        "source",
        "source_kind",
        "mods_root",
        "dest",
        "dry_run",
        "overwrite",
        "mods_scanned",
        "mods_with_resources",
        "files_seen",
        "copied",
        "would_copy",
        "overwritten",
        "would_overwrite",
        "duplicates_same",
        "preexisting_same",
        "conflicts",
        "skipped_conflicts",
    ):
        print(f"{key}: {summary[key]}")

    conflicts = report["events"]["conflicts"]
    if conflicts:
        print("[conflicts]")
        for conflict in conflicts[:50]:
            print(
                f"- {conflict['dest']} <- {conflict['source']} "
                f"(existing: {conflict['existing_source']}; resolution: {conflict['resolution']})"
            )
        if len(conflicts) > 50:
            print(f"... {len(conflicts) - 50} more")


def main() -> int:
    args = parse_args()
    try:
        report = extract_resources(
            source=Path(args.source),
            dest=Path(args.dest),
            overwrite=args.overwrite,
            dry_run=args.dry_run,
            include_hidden=args.include_hidden,
            follow_symlinks=args.follow_symlinks,
        )
    except ValueError as exc:
        print(str(exc))
        return 1

    if args.write_report:
        report_path = Path(args.write_report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)

    if args.fail_on_conflict and report["summary"]["conflicts"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
