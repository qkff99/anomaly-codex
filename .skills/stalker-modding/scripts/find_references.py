#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from _skill_common import REPO_ROOT, canonicalize_task, load_manifest, read_text_auto, resolve_ripgrep_command, workspace_external_paths


SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode", "node_modules", ".frontmatter", ".vs"}
TEXT_SUFFIXES = {
    "",
    ".script",
    ".lua",
    ".xml",
    ".ltx",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".txt",
    ".ini",
    ".h",
    ".hpp",
    ".cpp",
    ".c",
}
AUTO_OPTIONAL_ROOTS = ("user_references",)
AUTO_EXTERNAL_REFERENCE_TASKS = {
    "bugfix",
    "distribution-packaging",
    "feature",
    "refactor",
    "reference-discovery",
    "tutorial",
}
REFERENCE_EXTERNAL_PATH_KINDS = {
    "mo2_mods_dir",
    "gamedata_root",
    "external_mod_root",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search the current workspace or ai_workspace reference roots with task-aware scope."
    )
    parser.add_argument("pattern", help="Regex or plain text pattern to search for.")
    parser.add_argument("--task", default="tutorial", help="Task type or alias used to choose default roots.")
    parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        default=[],
        help="Named root override. Repeat for multiple roots.",
    )
    parser.add_argument("--max-count", type=int, default=50, help="Maximum matches per root when using rg.")
    return parser.parse_args()


def iter_text_files(root: Path, *, follow_links: bool = False):
    seen_dirs: set[Path] = set()
    for current_root, dirs, files in os.walk(root, followlinks=follow_links):
        current_path = Path(current_root)
        real_current = current_path.resolve()
        if follow_links:
            if real_current in seen_dirs:
                dirs[:] = []
                continue
            seen_dirs.add(real_current)
        dirs[:] = [name for name in sorted(dirs) if name not in SKIP_DIRS]
        for name in sorted(files):
            path = current_path / name
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            yield path


def search_with_rg(pattern: str, target: Path, max_count: int, rg_command: Path, *, follow_links: bool = False) -> list[str]:
    command = [
        str(rg_command),
        "-n",
        "--hidden",
        "--glob",
        "!/.git",
        pattern,
        str(target),
    ]
    if follow_links:
        command.insert(1, "--follow")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    matches: list[str] = []
    assert process.stdout is not None
    try:
        for line in process.stdout:
            matches.append(line.rstrip())
            if len(matches) >= max_count:
                process.terminate()
                break
    finally:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)
    return matches


def search_with_python(pattern: str, target: Path, max_count: int, *, follow_links: bool = False) -> list[str]:
    compiled = re.compile(pattern)
    matches: list[str] = []
    paths = [target] if target.is_file() else list(iter_text_files(target, follow_links=follow_links))
    for path in paths:
        try:
            text, _ = read_text_auto(path, errors="ignore")
            lines = text.splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            if compiled.search(line):
                matches.append(f"{path}:{line_number}:{line}")
                if len(matches) >= max_count:
                    return matches
    return matches


def build_external_root_specs() -> dict[str, dict[str, str]]:
    specs: dict[str, dict[str, str]] = {}
    for entry in workspace_external_paths():
        entry_id = entry.get("id")
        kind = entry.get("kind")
        raw_path = entry.get("path")
        label = entry.get("label")
        if not isinstance(entry_id, str) or not entry_id:
            continue
        if kind not in REFERENCE_EXTERNAL_PATH_KINDS:
            continue
        if not isinstance(raw_path, str) or not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve()
        specs[f"external:{entry_id}"] = {
            "id": entry_id,
            "kind": str(kind),
            "path": str(path),
            "label": str(label or entry_id),
        }
    return specs


def normalize_requested_root(raw_name: str, dynamic_roots: dict[str, dict[str, str]]) -> str:
    if raw_name in dynamic_roots:
        return raw_name
    candidate = f"external:{raw_name}"
    if candidate in dynamic_roots:
        return candidate
    return raw_name


def main() -> int:
    args = parse_args()
    hint_manifest = load_manifest("search_hints")
    ref_manifest = load_manifest("reference_roots")
    aliases = hint_manifest.get("aliases", {})
    tasks = hint_manifest.get("task_types", {})
    canonical_task = canonicalize_task(args.task, aliases, tasks)
    if canonical_task is None:
        print(f"unknown task type: {args.task}")
        print("known task types:")
        for key in sorted(tasks):
            print(f"  - {key}")
        return 1

    root_specs = ref_manifest.get("roots", {})
    dynamic_root_specs = build_external_root_specs()
    if args.roots:
        selected_root_names = [normalize_requested_root(raw_name, dynamic_root_specs) for raw_name in args.roots]
    else:
        selected_root_names = list(ref_manifest.get("task_roots", {}).get(canonical_task, ["workspace"]))
        for root_name in AUTO_OPTIONAL_ROOTS:
            spec = root_specs.get(root_name)
            if not spec or root_name in selected_root_names:
                continue
            candidate = (REPO_ROOT / spec["path"]).resolve()
            if candidate.exists():
                selected_root_names.append(root_name)
        if canonical_task in AUTO_EXTERNAL_REFERENCE_TASKS:
            selected_root_names.extend(sorted(dynamic_root_specs))

    missing_roots = [
        name for name in selected_root_names if name not in root_specs and name not in dynamic_root_specs
    ]
    if missing_roots:
        print(f"unknown root names: {', '.join(sorted(missing_roots))}")
        print("known roots:")
        for key in sorted(root_specs):
            print(f"  - {key}")
        for key in sorted(dynamic_root_specs):
            print(f"  - {key}")
        return 1

    print(f"task_type: {canonical_task}")
    print(f"pattern: {args.pattern}")
    print("[selected_roots]")
    available_roots: list[tuple[str, Path]] = []
    for root_name in selected_root_names:
        if root_name in dynamic_root_specs:
            spec = dynamic_root_specs[root_name]
            candidate = Path(spec["path"]).resolve()
            if candidate.exists():
                available_roots.append((root_name, candidate))
                print(f"{root_name}: {candidate} [kind={spec['kind']}, label={spec['label']}]")
            else:
                print(f"{root_name}: missing ({candidate}) [kind={spec['kind']}, label={spec['label']}]")
            continue

        candidate = (REPO_ROOT / root_specs[root_name]["path"]).resolve()
        if candidate.exists():
            available_roots.append((root_name, candidate))
            print(f"{root_name}: {candidate}")
        else:
            print(f"{root_name}: missing ({candidate})")
    print()

    rg_command = resolve_ripgrep_command()
    has_rg = rg_command is not None and args.pattern.isascii()
    for root_name, target in available_roots:
        follow_links = root_name == "user_references"
        print(f"[root:{root_name}]")
        if has_rg:
            matches = search_with_rg(args.pattern, target, args.max_count, rg_command, follow_links=follow_links)
            if matches:
                for match in matches:
                    print(match)
            else:
                print("none")
        else:
            try:
                matches = search_with_python(args.pattern, target, args.max_count, follow_links=follow_links)
            except re.error as exc:
                print(f"invalid regex: {exc}")
                return 1
            if matches:
                for match in matches:
                    print(match)
            else:
                print("none")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
