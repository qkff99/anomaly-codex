#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from _skill_common import REPO_ROOT


def _run_git(args: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=capture,
        check=True,
    )


def _tracked_files() -> list[str]:
    result = _run_git(["ls-files"])
    return [line for line in result.stdout.splitlines() if line]


def _is_graphify_artifact(path: str) -> bool:
    unix = path.replace("\\", "/")
    return (
        unix == "ai_workspace/map_index.html"
        or unix.startswith("ai_workspace/lua-graphify-out/")
        or "/graphify-out/" in f"/{unix}"
    )


def _tracked_graphify_files() -> list[str]:
    return [path for path in _tracked_files() if _is_graphify_artifact(path)]


def _tracked_graphify_roots() -> list[str]:
    roots: set[str] = set()
    for path in _tracked_graphify_files():
        unix = path.replace("\\", "/")
        if unix == "ai_workspace/map_index.html":
            roots.add(unix)
            continue
        if "/graphify-out/" in unix:
            roots.add(unix.split("/graphify-out/", 1)[0] + "/graphify-out")
            continue
        if unix.startswith("ai_workspace/lua-graphify-out/"):
            roots.add("ai_workspace/lua-graphify-out")
    return sorted(roots)


def _quote_ps(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _print_filter_repo() -> int:
    roots = _tracked_graphify_roots()
    if not roots:
        print("No tracked graphify artifacts found.")
        return 0

    print("# Run this from a fresh mirror clone, not from a dirty working tree.")
    print(f"git clone --mirror {_quote_ps(_run_git(['remote', 'get-url', 'origin']).stdout.strip())} anomaly-codex.git")
    print("cd anomaly-codex.git")
    print("py -3 -m pip install --user git-filter-repo")
    parts = ["py -3 -m git_filter_repo"]
    for root in roots:
        parts.append(f"--path {_quote_ps(root)}")
    print(" ".join(parts) + " --invert-paths --force")
    print("git push --force --mirror origin")
    return 0


def _untrack_now() -> int:
    paths = _tracked_graphify_files()
    if not paths:
        print("No tracked graphify artifacts found.")
        return 0

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        pathspec_file = Path(handle.name)
        for path in paths:
            handle.write(path)
            handle.write("\n")

    try:
        subprocess.run(
            [
                "git",
                "rm",
                "-r",
                "--cached",
                "--ignore-unmatch",
                f"--pathspec-from-file={pathspec_file}",
            ],
            cwd=REPO_ROOT,
            check=True,
        )
    finally:
        pathspec_file.unlink(missing_ok=True)

    print(f"Untracked {len(paths)} graphify artifact files from git index.")
    return 0


def _list_now() -> int:
    roots = _tracked_graphify_roots()
    paths = _tracked_graphify_files()
    print(f"tracked_files={len(paths)}")
    print(f"tracked_roots={len(roots)}")
    for root in roots:
        print(root)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Repo-local helper for removing generated graphify artifacts from git tracking "
            "and printing the exact git-filter-repo command needed to rewrite history."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List tracked graphify roots and files.")
    sub.add_parser("untrack-now", help="git rm --cached all tracked graphify artifacts without deleting them from disk.")
    sub.add_parser("print-filter-repo", help="Print an exact git-filter-repo command for this repository.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "list":
        return _list_now()
    if args.command == "untrack-now":
        return _untrack_now()
    if args.command == "print-filter-repo":
        return _print_filter_repo()
    raise RuntimeError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
