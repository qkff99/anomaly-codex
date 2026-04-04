#!/usr/bin/env python3
from __future__ import annotations

import sys

from _skill_common import canonicalize_task, load_manifest


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: query_hints.py <task-type>")
        return 1

    requested_task = sys.argv[1]
    manifest = load_manifest("search_hints")
    aliases = manifest.get("aliases", {})
    tasks = manifest.get("task_types", {})
    task_type = canonicalize_task(requested_task, aliases, tasks)
    if not task_type:
        print(f"unknown task type: {requested_task}")
        print("known task types:")
        for key in sorted(tasks):
            print(f"  - {key}")
        print("known aliases:")
        for key in sorted(aliases):
            print(f"  - {key} -> {aliases[key]}")
        return 1

    data = tasks[task_type]
    print(f"task_type: {task_type}")
    for section in (
        "bash_commands",
        "powershell_commands",
        "reference_roots",
        "gitmcp_queries",
        "deepwiki_questions",
        "references",
    ):
        print(f"[{section}]")
        values = data.get(section, [])
        if not values:
            print("none")
        else:
            for value in values:
                print(value)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
