#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from _skill_common import resolve_ripgrep_command


PATTERNS = (
    ("callbacks", r"RegisterScriptCallback|UnregisterScriptCallback|SendScriptCallback"),
    ("binders", r"bind_object|object_binder|class[[:space:]]+\".*\"[[:space:]]*\\(object_binder\\)"),
    ("registrators", r"class_registrator|ui_registrator|RegisterScriptClass"),
    ("ui_attach", r"delayed_attach|attach"),
    ("monkey_patches", r"getmetatable|setmetatable|rawget|rawset|debug\\.get"),
)
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
    ".h",
    ".hpp",
    ".cpp",
    ".c",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find common XRay/Anomaly entrypoints and patch sites.")
    parser.add_argument("root", nargs="?", default=".")
    return parser.parse_args()


def iter_text_files(root: Path):
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [name for name in sorted(dirs) if name not in SKIP_DIRS]
        for name in sorted(files):
            path = Path(current_root) / name
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            yield path


def run_rg(root: Path, label: str, pattern: str, rg_command: Path) -> int:
    command = [str(rg_command), "-n", "--hidden", "--glob", "!/.git", pattern, str(root)]
    print(f"[{label}]")
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    print()
    return completed.returncode


def python_search(root: Path, label: str, pattern: str) -> None:
    print(f"[{label}]")
    try:
        compiled = re.compile(pattern)
    except re.error:
        compiled = re.compile(pattern.replace("[[:space:]]", r"\s"))
    found = False
    for path in iter_text_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            if compiled.search(line):
                found = True
                print(f"{path}:{line_number}:{line}")
    print()
    if not found:
        return


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    rg = resolve_ripgrep_command()
    for label, pattern in PATTERNS:
        if rg:
            run_rg(root, label, pattern, rg)
        else:
            python_search(root, label, pattern)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
