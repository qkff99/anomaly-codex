#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from _project_toolchain import (
    PROJECTS_DIR,
    load_project,
    normalize_identifier,
    path_in_mod_root,
    register_template,
    require_valid_project_name,
    starter_dltx_patch,
    starter_dxml_patch,
    starter_lua_feature,
    starter_mcm_localizations,
    starter_mcm_runtime,
    starter_mcm_script,
    template_output_relpaths,
    validate_project_metadata,
    write_project,
    write_text_exact,
    write_xml_string_table,
)


LUA_STEM_RE = r"^[A-Za-z_][A-Za-z0-9_]*$"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold common STALKER modding templates inside a project.")
    parser.add_argument("--project", required=True, help="Project name under projects/.")
    parser.add_argument(
        "--template",
        required=True,
        choices=("lua_feature", "lua_mcm", "localization_pack", "dltx_patch", "dxml_patch"),
        help="Template kind to create.",
    )
    parser.add_argument("--script-name", help="Lua script stem for lua_feature or lua_mcm.")
    parser.add_argument("--option-root", help="MCM option root for lua_mcm.")
    parser.add_argument("--xml-name", help="Localization XML file name for localization_pack.")
    parser.add_argument("--target-root", help="Target root name for dltx_patch.")
    parser.add_argument("--target-xml", help="Target XML path for dxml_patch.")
    return parser.parse_args()


def ensure_safe_lua_stem(raw: str, *, label: str) -> str:
    import re

    if not re.fullmatch(LUA_STEM_RE, raw):
        raise ValueError(f"{label} must match {LUA_STEM_RE}")
    return raw


def ensure_safe_file_name(raw: str, *, suffix: str) -> str:
    candidate = Path(raw)
    if candidate.name != raw or candidate.suffix.lower() != suffix:
        raise ValueError(f"expected a file name ending in {suffix}: {raw}")
    return raw


def ensure_safe_target_root(raw: str) -> str:
    return ensure_safe_lua_stem(raw, label="target root")


def ensure_safe_target_xml(raw: str) -> str:
    candidate = Path(raw.replace("\\", "/"))
    if candidate.is_absolute():
        raise ValueError("target XML must be a relative path")
    if candidate.suffix.lower() != ".xml":
        raise ValueError("target XML must end in .xml")
    return raw.replace("\\", "/").strip("/")


def require_project_languages(metadata: dict[str, object]) -> None:
    languages = metadata.get("languages", [])
    if not isinstance(languages, list) or "eng" not in languages or "rus" not in languages:
        raise ValueError("project languages must include eng and rus for this template")


def ensure_outputs_absent(project_root: Path, relpaths: list[str]) -> None:
    collisions = [project_root / relpath for relpath in relpaths if (project_root / relpath).exists()]
    if collisions:
        paths = ", ".join(str(path) for path in collisions)
        raise FileExistsError(f"template outputs already exist: {paths}")


def declared_output_relpaths(metadata: dict[str, object]) -> set[str]:
    result: set[str] = set()
    templates = metadata.get("templates", [])
    if not isinstance(templates, list):
        return result

    for entry in templates:
        if isinstance(entry, dict) and "kind" in entry:
            result.update(template_output_relpaths(entry))
    return result


def relpaths_collide(project_root: Path, metadata: dict[str, object], relpaths: list[str]) -> bool:
    if len(set(relpaths)) != len(relpaths):
        return True
    declared = declared_output_relpaths(metadata)
    for relpath in relpaths:
        if relpath in declared or (project_root / relpath).exists():
            return True
    return False


def scaffold_lua_feature(project_root: Path, metadata: dict[str, object], script_stem: str) -> dict[str, object]:
    relpath = f"gamedata/scripts/{script_stem}.script"
    entry = {"kind": "lua_feature", "script": relpath}
    ensure_outputs_absent(project_root, template_output_relpaths(entry))
    write_text_exact(project_root / relpath, starter_lua_feature(script_stem))
    return entry


def build_lua_mcm_entry(
    script_stem: str,
    option_root: str,
    *,
    runtime_suffix: str = "",
) -> dict[str, object]:
    runtime_stem = f"{script_stem}{runtime_suffix}"
    mcm_stem = script_stem if script_stem.endswith("_mcm") else f"{script_stem}_mcm"
    if runtime_stem == mcm_stem:
        runtime_stem = f"{runtime_stem}_runtime"
    return {
        "kind": "lua_mcm",
        "runtime_script": f"gamedata/scripts/{runtime_stem}.script",
        "mcm_script": f"gamedata/scripts/{mcm_stem}.script",
        "option_root": option_root,
        "localization": {
            "eng": f"gamedata/configs/text/eng/ui_st_{script_stem}.xml",
            "rus": f"gamedata/configs/text/rus/ui_st_{script_stem}.xml",
        },
    }


def choose_default_lua_mcm_entry(
    project_root: Path,
    metadata: dict[str, object],
    default_stem: str,
    option_root: str,
) -> dict[str, object]:
    candidate_stems: list[tuple[str, str]] = [
        (default_stem, ""),
        (default_stem, "_runtime"),
        (f"{default_stem}_menu", ""),
        (f"{default_stem}_config", ""),
    ]
    candidate_stems.extend((f"{default_stem}_{index}", "") for index in range(2, 100))

    for candidate_stem, runtime_suffix in candidate_stems:
        entry = build_lua_mcm_entry(candidate_stem, option_root, runtime_suffix=runtime_suffix)
        if not relpaths_collide(project_root, metadata, template_output_relpaths(entry)):
            return entry

    raise FileExistsError(f"could not find a free lua_mcm scaffold name for {default_stem}")


def scaffold_lua_mcm(project_root: Path, metadata: dict[str, object], entry: dict[str, object]) -> dict[str, object]:
    require_project_languages(metadata)
    ensure_outputs_absent(project_root, template_output_relpaths(entry))

    display_name = str(metadata["display_name"])
    option_root = str(entry["option_root"])
    localization = entry["localization"]
    assert isinstance(localization, dict)
    runtime_script = str(entry["runtime_script"])
    mcm_script = str(entry["mcm_script"])
    runtime_stem = Path(runtime_script).stem

    write_text_exact(project_root / runtime_script, starter_mcm_runtime(runtime_stem, option_root))
    write_text_exact(project_root / mcm_script, starter_mcm_script(option_root))

    localized_entries = starter_mcm_localizations(option_root, display_name)
    write_xml_string_table(project_root / str(localization["eng"]), localized_entries["eng"], declared_encoding="utf-8")
    write_xml_string_table(
        project_root / str(localization["rus"]),
        localized_entries["rus"],
        declared_encoding="windows-1251",
    )
    return entry


def scaffold_localization_pack(project_root: Path, metadata: dict[str, object], xml_name: str) -> dict[str, object]:
    require_project_languages(metadata)
    eng_rel = f"gamedata/configs/text/eng/{xml_name}"
    rus_rel = f"gamedata/configs/text/rus/{xml_name}"
    entry = {
        "kind": "localization_pack",
        "files": [eng_rel, rus_rel],
    }
    ensure_outputs_absent(project_root, template_output_relpaths(entry))
    write_xml_string_table(project_root / eng_rel, [], declared_encoding="utf-8")
    write_xml_string_table(project_root / rus_rel, [], declared_encoding="windows-1251")
    return entry


def scaffold_dltx_patch(project_root: Path, metadata: dict[str, object], target_root: str) -> dict[str, object]:
    project_name = str(metadata["project_name"])
    file_rel = f"gamedata/configs/mod_{target_root}_{project_name}.ltx"
    entry = {
        "kind": "dltx_patch",
        "target_root": target_root,
        "file": file_rel,
    }
    ensure_outputs_absent(project_root, template_output_relpaths(entry))
    write_text_exact(project_root / file_rel, starter_dltx_patch(project_name, target_root))
    return entry


def scaffold_dxml_patch(project_root: Path, metadata: dict[str, object], target_xml: str) -> dict[str, object]:
    script_stem = f"modxml_{normalize_identifier(str(metadata['project_name']))}"
    script_rel = f"gamedata/scripts/{script_stem}.script"
    entry = {
        "kind": "dxml_patch",
        "target_xml": target_xml,
        "script": script_rel,
    }
    ensure_outputs_absent(project_root, template_output_relpaths(entry))
    write_text_exact(project_root / script_rel, starter_dxml_patch(target_xml))
    return entry


def main() -> int:
    args = parse_args()
    require_valid_project_name(args.project)
    project_root, metadata = load_project(args.project)
    errors = validate_project_metadata(metadata)
    if errors:
        print("project metadata is invalid:")
        for error in errors:
            print(f"- {error}")
        return 1

    default_stem = normalize_identifier(args.project)

    if args.template == "lua_feature":
        script_stem = ensure_safe_lua_stem(args.script_name or default_stem, label="script name")
        entry = scaffold_lua_feature(project_root, metadata, script_stem)
    elif args.template == "lua_mcm":
        option_root = ensure_safe_lua_stem(args.option_root or default_stem, label="option root")
        if args.script_name:
            script_stem = ensure_safe_lua_stem(args.script_name, label="script name")
            runtime_suffix = "_runtime" if script_stem.endswith("_mcm") else ""
            entry = build_lua_mcm_entry(script_stem, option_root, runtime_suffix=runtime_suffix)
        else:
            entry = choose_default_lua_mcm_entry(project_root, metadata, default_stem, option_root)
        entry = scaffold_lua_mcm(project_root, metadata, entry)
    elif args.template == "localization_pack":
        xml_name = ensure_safe_file_name(args.xml_name or f"ui_st_{default_stem}.xml", suffix=".xml")
        entry = scaffold_localization_pack(project_root, metadata, xml_name)
    elif args.template == "dltx_patch":
        if not args.target_root:
            print("--target-root is required for dltx_patch")
            return 1
        entry = scaffold_dltx_patch(project_root, metadata, ensure_safe_target_root(args.target_root))
    elif args.template == "dxml_patch":
        if not args.target_xml:
            print("--target-xml is required for dxml_patch")
            return 1
        entry = scaffold_dxml_patch(project_root, metadata, ensure_safe_target_xml(args.target_xml))
    else:
        raise AssertionError(f"unsupported template kind: {args.template}")

    register_template(metadata, entry)
    metadata_path = write_project(project_root, metadata)

    print(f"project_root: {project_root}")
    print(f"metadata: {metadata_path}")
    print("created:")
    for relpath in template_output_relpaths(entry):
        print(f"- {project_root / relpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
