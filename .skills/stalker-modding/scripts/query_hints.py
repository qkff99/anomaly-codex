#!/usr/bin/env python3
from __future__ import annotations

import sys

from _skill_common import canonicalize_task, load_manifest


def load_manifest_object(name: str) -> dict:
    data = load_manifest(name)
    return data if isinstance(data, dict) else {}


def checklist_for_task(task_type: str, checklists: dict) -> list[str]:
    task_to_checklist = {
        "save-load": "save_load",
        "ui-mcm": "ui_mcm",
        "weapons-hud": "weapons_hud",
        "visible-body-legs": "visible_body",
        "tasks-story-alife": "tasks_story_alife",
    }
    key = task_to_checklist.get(task_type)
    if not key:
        return []
    entries = checklists.get("checklists", {}).get(key, [])
    return entries if isinstance(entries, list) else []


def subsystem_checks_for_task(task_type: str, subsystems: dict) -> list[str]:
    entries = subsystems.get("subsystems", [])
    if not isinstance(entries, list):
        return []
    matched: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("id") != task_type:
            continue
        checks = entry.get("required_checks", [])
        if isinstance(checks, list):
            matched.extend(str(item) for item in checks)
    return matched


def output_contract_for_task(task_type: str, contracts: dict) -> list[str]:
    all_contracts = contracts.get("contracts", {})
    if not isinstance(all_contracts, dict):
        return []
    selected = all_contracts.get(task_type) or all_contracts.get("default") or []
    return selected if isinstance(selected, list) else []


def print_values(section: str, values: list[str]) -> None:
    print(f"[{section}]")
    if not values:
        print("none")
    else:
        for value in values:
            print(value)
    print()


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
        values = data.get(section, [])
        print_values(section, values)

    quality_rules = load_manifest_object("quality_rules")
    checklists = load_manifest_object("checklists")
    subsystems = load_manifest_object("subsystems")
    output_contracts = load_manifest_object("output_contracts")

    gates = quality_rules.get("task_gates", {}).get(task_type, [])
    print_values("quality_gates", gates if isinstance(gates, list) else [])
    print_values("required_checks", subsystem_checks_for_task(task_type, subsystems))
    print_values("checklist", checklist_for_task(task_type, checklists))
    print_values(
        "quality_commands",
        [
            f"python3 ./.skills/stalker-modding/scripts/quality_scan.py scan <path> --task {task_type}",
            f"python3 ./.skills/stalker-modding/scripts/quality_scan.py scan <path> --task {task_type} --json",
            "python3 ./.skills/stalker-modding/scripts/quality_scan.py graph <path> --json",
            "python3 ./.skills/stalker-modding/scripts/quality_scan.py suggest-patch <gamedata-file> --json",
            "python3 ./.skills/stalker-modding/scripts/quality_scan.py save-template <module>",
            "python3 ./.skills/stalker-modding/scripts/quality_scan.py optional-pattern list",
        ],
    )
    print_values("output_contract", output_contract_for_task(task_type, output_contracts))
    markers = output_contracts.get("source_tier_markers", [])
    print_values("source_tier_markers", markers if isinstance(markers, list) else [])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
