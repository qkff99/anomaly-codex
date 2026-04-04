#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from _project_toolchain import (
    collect_xml_ids,
    ensure_project_files_exist,
    file_looks_cp1251,
    find_on_mcm_load_bodies,
    load_project,
    read_text_strict,
    template_output_relpaths,
    validate_project_metadata,
)
from _skill_common import normalize_rel_path, read_text_auto
from luac_tool import detect_compiler, iter_targets, syntax_check


STARTER_MCM_SUFFIXES = (
    "header",
    "enable_feature",
    "enable_feature_desc",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate project metadata and scaffold outputs for a local mod project.")
    parser.add_argument("--project", required=True, help="Project name under projects/.")
    return parser.parse_args()


def starter_mcm_ids(option_root: str) -> set[str]:
    result = {f"ui_mcm_menu_{option_root}"}
    result.update(f"ui_mcm_{option_root}_{suffix}" for suffix in STARTER_MCM_SUFFIXES)
    return result


def validate_lua_files(project_root: Path, mod_root: str) -> tuple[list[str], int]:
    compiler = detect_compiler()
    if compiler is None:
        return (["luac compiler was not detected; run luac_tool.py detect or bootstrap_env first"], 0)

    errors: list[str] = []
    checked = 0
    for path in iter_targets([str(project_root / mod_root)], recursive=True):
        checked += 1
        ok, output = syntax_check(compiler, path)
        if not ok:
            message = f"Lua syntax failed: {path}"
            if output:
                message = f"{message}: {output}"
            errors.append(message)
    return errors, checked


def validate_localization_xmls(project_root: Path, mod_root: str) -> tuple[list[str], int]:
    base = project_root / mod_root / "configs" / "text"
    if not base.exists():
        return [], 0

    errors: list[str] = []
    checked = 0
    for path in sorted(base.rglob("*.xml")):
        checked += 1
        try:
            read_text_auto(path, errors="strict")
        except (OSError, UnicodeDecodeError, LookupError) as exc:
            errors.append(f"XML read failed: {path}: {exc}")
    return errors, checked


def validate_template(project_root: Path, template: dict[str, object]) -> list[str]:
    errors: list[str] = []
    kind = str(template["kind"])
    missing = ensure_project_files_exist(project_root, template_output_relpaths(template))
    for relpath in missing:
        errors.append(f"missing output: {relpath}")

    if kind == "lua_mcm":
        mcm_script = project_root / normalize_rel_path(str(template["mcm_script"]))
        localization = template["localization"]
        assert isinstance(localization, dict)
        eng_path = project_root / normalize_rel_path(str(localization["eng"]))
        rus_path = project_root / normalize_rel_path(str(localization["rus"]))

        all_mcm_scripts = sorted((project_root / "gamedata" / "scripts").glob("*mcm.script"))
        if not all_mcm_scripts:
            errors.append("lua_mcm template requires at least one *mcm.script in gamedata/scripts")

        if mcm_script.exists():
            text = read_text_strict(mcm_script)
            if "function on_mcm_load" not in text:
                errors.append(f"{mcm_script} is missing on_mcm_load")
            for body in find_on_mcm_load_bodies(text):
                if "ui_mcm.get(" in body:
                    errors.append(f"{mcm_script} calls ui_mcm.get inside on_mcm_load")

        required_ids = starter_mcm_ids(str(template["option_root"]))
        for xml_path in (eng_path, rus_path):
            if xml_path.exists():
                ids = collect_xml_ids(xml_path)
                missing_ids = sorted(required_ids - ids)
                if missing_ids:
                    errors.append(f"{xml_path} is missing starter MCM ids: {', '.join(missing_ids)}")
        if rus_path.exists() and not file_looks_cp1251(rus_path):
            errors.append(f"{rus_path} should remain cp1251/windows-1251 for the starter scaffold")

    elif kind == "dltx_patch":
        file_path = project_root / normalize_rel_path(str(template["file"]))
        if file_path.exists():
            if not file_path.name.startswith("mod_"):
                errors.append(f"{file_path} must start with mod_")
            if file_path.suffix.lower() != ".ltx":
                errors.append(f"{file_path} must end in .ltx")

    elif kind == "dxml_patch":
        script_path = project_root / normalize_rel_path(str(template["script"]))
        target_xml = str(template["target_xml"])
        if script_path.exists():
            text = read_text_strict(script_path)
            if not script_path.name.startswith("modxml_"):
                errors.append(f"{script_path} must start with modxml_")
            if "function on_xml_read" not in text:
                errors.append(f"{script_path} is missing on_xml_read")
            if target_xml not in text and target_xml.replace("/", "\\") not in text:
                errors.append(f"{script_path} does not mention target XML {target_xml}")

    return errors


def main() -> int:
    args = parse_args()
    project_root, metadata = load_project(args.project)
    errors = validate_project_metadata(metadata)

    mod_root = str(metadata.get("mod_root", "gamedata"))
    templates = metadata.get("templates", [])
    if isinstance(templates, list):
        for template in templates:
            if isinstance(template, dict) and "kind" in template:
                errors.extend(validate_template(project_root, template))
    else:
        errors.append("templates must be a list")

    lua_errors, lua_checked = validate_lua_files(project_root, mod_root)
    errors.extend(lua_errors)

    xml_errors, xml_checked = validate_localization_xmls(project_root, mod_root)
    errors.extend(xml_errors)

    if errors:
        print("project: invalid")
        for error in errors:
            print(f"- {error}")
        return 1

    print("project: valid")
    print(f"project_root: {project_root}")
    print(f"lua_checked: {lua_checked}")
    print(f"xml_checked: {xml_checked}")
    print(f"templates: {len(templates) if isinstance(templates, list) else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
