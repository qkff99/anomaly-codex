from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from _skill_common import (
    REPO_ROOT,
    collect_xml_string_ids,
    load_json_file,
    load_manifest,
    load_project_metadata,
    normalize_rel_path,
    read_text_auto,
    repo_relative,
    save_project_metadata,
    write_bytes_exact,
    write_text_exact,
)


PROJECTS_DIR = REPO_ROOT / "projects"
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
SAFE_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9]+")
TEMPLATE_FIELDS: dict[str, tuple[str, ...]] = {
    "lua_feature": ("kind", "script"),
    "lua_mcm": ("kind", "runtime_script", "mcm_script", "option_root", "localization"),
    "localization_pack": ("kind", "files"),
    "dltx_patch": ("kind", "target_root", "file"),
    "dxml_patch": ("kind", "target_xml", "script"),
}
PROJECT_SOURCE_FIELDS = ("mode", "kind", "origin_path")
DEFAULT_BASELINE = "anomaly_1_5_3_modded_exes"
DEFAULT_MOD_ROOT = "gamedata"
DEFAULT_LANGUAGES = ["eng", "rus"]
DEFAULT_ARTIFACT_DEFAULTS = {"loose": True, "zip": False}
XML_DECLARATIONS = {
    "utf-8": '<?xml version="1.0" encoding="utf-8" ?>',
    "windows-1251": '<?xml version="1.0" encoding="windows-1251" ?>',
}
TEMPORARY_ARTIFACT_SUFFIXES = (".tmp", ".bak", ".orig", ".rej", ".pyc")
PACKAGING_EXCLUDED_DIR_NAMES = {".codex-stalker", "dist", "__pycache__"}
PACKAGING_EXCLUDED_FILE_NAMES = {".DS_Store"}
STRING_ID_RE = re.compile(r"""<string\s+id=["']([^"']+)["']""")


def project_root_from_name(name: str) -> Path:
    return PROJECTS_DIR / name


def require_valid_project_name(name: str) -> None:
    if not PROJECT_NAME_RE.fullmatch(name):
        raise ValueError("project name must match ^[A-Za-z0-9][A-Za-z0-9_-]*$")


def normalize_identifier(raw: str) -> str:
    candidate = SAFE_IDENTIFIER_RE.sub("_", raw.strip()).strip("_").lower()
    if not candidate:
        candidate = "mod"
    if candidate[0].isdigit():
        candidate = f"mod_{candidate}"
    return candidate


def default_display_name(name: str) -> str:
    words = name.replace("_", " ").replace("-", " ").split()
    return " ".join(word.capitalize() for word in words) if words else name


def default_project_metadata(name: str, display_name: str | None = None) -> dict[str, Any]:
    return {
        "project_name": name,
        "display_name": display_name or default_display_name(name),
        "baseline": DEFAULT_BASELINE,
        "mod_root": DEFAULT_MOD_ROOT,
        "artifact_defaults": dict(DEFAULT_ARTIFACT_DEFAULTS),
        "languages": list(DEFAULT_LANGUAGES),
        "templates": [],
    }


def load_project(project_name: str) -> tuple[Path, dict[str, Any]]:
    project_root = project_root_from_name(project_name).resolve()
    if not project_root.exists():
        raise FileNotFoundError(f"project not found: {project_root}")
    metadata = load_project_metadata(project_root)
    if metadata is None:
        raise FileNotFoundError(f"project metadata not found in {project_root}")
    return project_root, metadata


def load_project_schema() -> dict[str, Any]:
    data = load_manifest("project_schema")
    if not isinstance(data, dict):
        raise ValueError("project_schema manifest must be a JSON object")
    return data


def validate_project_metadata(data: Any) -> list[str]:
    errors: list[str] = []
    schema = load_project_schema()
    required_top = tuple(schema.get("required", ()))
    allowed_top = set(schema.get("properties", {}))
    template_specs = schema.get("templateKinds", {})

    if not isinstance(data, dict):
        return ["project metadata must be a JSON object"]

    for key in required_top:
        if key not in data:
            errors.append(f"missing field: {key}")
    for key in sorted(set(data) - allowed_top):
        errors.append(f"unexpected field: {key}")

    if not isinstance(data.get("project_name"), str) or not data.get("project_name"):
        errors.append("project_name must be a non-empty string")
    elif not PROJECT_NAME_RE.fullmatch(data["project_name"]):
        errors.append("project_name must match ^[A-Za-z0-9][A-Za-z0-9_-]*$")

    if not isinstance(data.get("display_name"), str) or not data.get("display_name"):
        errors.append("display_name must be a non-empty string")
    if not isinstance(data.get("baseline"), str) or not data.get("baseline"):
        errors.append("baseline must be a non-empty string")
    if data.get("mod_root") != DEFAULT_MOD_ROOT:
        errors.append("mod_root must be 'gamedata' in v1")

    source = data.get("source")
    if source is not None:
        if not isinstance(source, dict):
            errors.append("source must be an object when present")
        else:
            for key in PROJECT_SOURCE_FIELDS:
                if key not in source:
                    errors.append(f"source missing field: {key}")
            for key in sorted(set(source) - set(PROJECT_SOURCE_FIELDS)):
                errors.append(f"source unexpected field: {key}")
            if source.get("mode") != "imported_copy":
                errors.append("source.mode must be 'imported_copy'")
            if source.get("kind") not in {"mod_root", "gamedata_root"}:
                errors.append("source.kind must be 'mod_root' or 'gamedata_root'")
            origin_path = source.get("origin_path")
            if not isinstance(origin_path, str) or not origin_path:
                errors.append("source.origin_path must be a non-empty string")
            elif not Path(origin_path).is_absolute():
                errors.append("source.origin_path must be an absolute path")

    artifact_defaults = data.get("artifact_defaults")
    if not isinstance(artifact_defaults, dict):
        errors.append("artifact_defaults must be an object")
    else:
        if set(artifact_defaults) != {"loose", "zip"}:
            errors.append("artifact_defaults must contain only loose and zip")
        for key in ("loose", "zip"):
            if not isinstance(artifact_defaults.get(key), bool):
                errors.append(f"artifact_defaults.{key} must be a boolean")

    languages = data.get("languages")
    if not isinstance(languages, list) or not languages:
        errors.append("languages must be a non-empty list of strings")
    else:
        if not all(isinstance(language, str) and language for language in languages):
            errors.append("languages must contain only non-empty strings")
        if len(set(languages)) != len(languages):
            errors.append("languages must not contain duplicates")

    templates = data.get("templates")
    if not isinstance(templates, list):
        errors.append("templates must be a list")
    else:
        for index, entry in enumerate(templates):
            prefix = f"templates[{index}]"
            if not isinstance(entry, dict):
                errors.append(f"{prefix} must be an object")
                continue
            kind = entry.get("kind")
            if kind not in TEMPLATE_FIELDS:
                errors.append(f"{prefix}.kind is invalid: {kind!r}")
                continue
            required_fields = set(template_specs.get(kind, {}).get("required", ()))
            allowed_fields = set(TEMPLATE_FIELDS[kind])
            for key in required_fields:
                if key not in entry:
                    errors.append(f"{prefix} missing field: {key}")
            for key in sorted(set(entry) - allowed_fields):
                errors.append(f"{prefix} unexpected field: {key}")

            if kind == "lua_feature":
                if not is_rel_text_path(entry.get("script"), suffixes=(".lua", ".script")):
                    errors.append(f"{prefix}.script must be a relative .lua or .script path")
            elif kind == "lua_mcm":
                if not is_rel_text_path(entry.get("runtime_script"), suffixes=(".lua", ".script")):
                    errors.append(f"{prefix}.runtime_script must be a relative Lua path")
                if not is_rel_text_path(entry.get("mcm_script"), suffixes=(".lua", ".script")):
                    errors.append(f"{prefix}.mcm_script must be a relative Lua path")
                if not isinstance(entry.get("option_root"), str) or not entry.get("option_root"):
                    errors.append(f"{prefix}.option_root must be a non-empty string")
                localization = entry.get("localization")
                if not isinstance(localization, dict) or set(localization) != {"eng", "rus"}:
                    errors.append(f"{prefix}.localization must be an object with eng and rus paths")
                else:
                    for lang, raw_path in sorted(localization.items()):
                        if not is_rel_text_path(raw_path, suffixes=(".xml",)):
                            errors.append(f"{prefix}.localization.{lang} must be a relative .xml path")
            elif kind == "localization_pack":
                files = entry.get("files")
                if not isinstance(files, list) or not files:
                    errors.append(f"{prefix}.files must be a non-empty list")
                elif not all(is_rel_text_path(raw_path, suffixes=(".xml",)) for raw_path in files):
                    errors.append(f"{prefix}.files must contain only relative .xml paths")
            elif kind == "dltx_patch":
                if not isinstance(entry.get("target_root"), str) or not entry.get("target_root"):
                    errors.append(f"{prefix}.target_root must be a non-empty string")
                if not is_rel_text_path(entry.get("file"), suffixes=(".ltx",)):
                    errors.append(f"{prefix}.file must be a relative .ltx path")
            elif kind == "dxml_patch":
                if not isinstance(entry.get("target_xml"), str) or not entry.get("target_xml"):
                    errors.append(f"{prefix}.target_xml must be a non-empty string")
                if not is_rel_text_path(entry.get("script"), suffixes=(".lua", ".script")):
                    errors.append(f"{prefix}.script must be a relative Lua path")

    return errors


def is_rel_text_path(raw: Any, *, suffixes: tuple[str, ...]) -> bool:
    if not isinstance(raw, str) or not raw:
        return False
    candidate = Path(normalize_rel_path(raw))
    return not candidate.is_absolute() and candidate.suffix.lower() in suffixes


def template_output_relpaths(entry: dict[str, Any]) -> list[str]:
    kind = entry["kind"]
    if kind == "lua_feature":
        return [normalize_rel_path(entry["script"])]
    if kind == "lua_mcm":
        localization = entry["localization"]
        return [
            normalize_rel_path(entry["runtime_script"]),
            normalize_rel_path(entry["mcm_script"]),
            normalize_rel_path(localization["eng"]),
            normalize_rel_path(localization["rus"]),
        ]
    if kind == "localization_pack":
        return [normalize_rel_path(path) for path in entry["files"]]
    if kind == "dltx_patch":
        return [normalize_rel_path(entry["file"])]
    if kind == "dxml_patch":
        return [normalize_rel_path(entry["script"])]
    raise ValueError(f"unsupported template kind: {kind}")


def template_kinds(metadata: dict[str, Any]) -> list[str]:
    return [entry["kind"] for entry in metadata.get("templates", []) if isinstance(entry, dict) and "kind" in entry]


def register_template(metadata: dict[str, Any], entry: dict[str, Any]) -> None:
    templates = metadata.setdefault("templates", [])
    if not isinstance(templates, list):
        raise ValueError("project metadata templates field is not a list")

    new_outputs = set(template_output_relpaths(entry))
    for existing in templates:
        if not isinstance(existing, dict):
            continue
        existing_outputs = set(template_output_relpaths(existing))
        if new_outputs & existing_outputs:
            overlap = ", ".join(sorted(new_outputs & existing_outputs))
            raise ValueError(f"template outputs already declared: {overlap}")
        if existing == entry:
            raise ValueError("template is already declared in project metadata")

    templates.append(entry)


def write_project(project_root: Path, metadata: dict[str, Any]) -> Path:
    return save_project_metadata(project_root, metadata)


def render_string_table(entries: list[tuple[str, str]], *, declared_encoding: str) -> str:
    lines = [
        XML_DECLARATIONS[declared_encoding],
        "",
        "<string_table>",
        "",
    ]
    for string_id, text in entries:
        lines.append(f'    <string id="{escape(string_id)}">')
        lines.append(f"        <text>{escape(text)}</text>")
        lines.append("    </string>")
        lines.append("")
    lines.append("</string_table>")
    lines.append("")
    return "\n".join(lines)


def write_xml_string_table(path: Path, entries: list[tuple[str, str]], *, declared_encoding: str) -> None:
    text = render_string_table(entries, declared_encoding=declared_encoding)
    codec = "cp1251" if declared_encoding == "windows-1251" else declared_encoding
    write_bytes_exact(path, text.encode(codec))


def collect_xml_ids(path: Path) -> set[str]:
    return collect_xml_string_ids(path)


def starter_lua_feature(script_stem: str) -> str:
    return "\n".join(
        [
            f"-- Gameplay scaffold for {script_stem}",
            "",
            "local function on_actor_first_update()",
            "    if not db or not db.actor then",
            "        return",
            "    end",
            "",
            "    -- World-dependent logic starts here.",
            "end",
            "",
            "function on_game_start()",
            '    RegisterScriptCallback("actor_on_first_update", on_actor_first_update)',
            "end",
            "",
        ]
    )


def starter_mcm_runtime(script_stem: str, option_root: str) -> str:
    return "\n".join(
        [
            f"-- Runtime scaffold for {script_stem}",
            "",
            "local defaults = {",
            "    enable_feature = true,",
            "}",
            "",
            "local config = {",
            "    enable_feature = defaults.enable_feature,",
            "}",
            "",
            f'local OPTION_ROOT = "{option_root}"',
            "",
            "local function option_path(key)",
            '    return OPTION_ROOT .. "/" .. key',
            "end",
            "",
            "local function refresh_config()",
            "    local value = nil",
            "    if ui_mcm then",
            '        value = ui_mcm.get(option_path("enable_feature"))',
            "    end",
            "    if value == nil then",
            "        value = defaults.enable_feature",
            "    end",
            "    config.enable_feature = value",
            "end",
            "",
            "function get_config(key)",
            "    if config[key] ~= nil then",
            "        return config[key]",
            "    end",
            "    return defaults[key]",
            "end",
            "",
            "function on_option_change(from_mcm)",
            "    if not from_mcm then",
            "        return",
            "    end",
            "    refresh_config()",
            "end",
            "",
            "function on_game_start()",
            "    refresh_config()",
            '    RegisterScriptCallback("on_option_change", on_option_change)',
            "end",
            "",
        ]
    )


def starter_mcm_script(option_root: str) -> str:
    return "\n".join(
        [
            f'local OPTION_ROOT = "{option_root}"',
            "",
            "function on_mcm_load()",
            "    local options = {",
            "        id = OPTION_ROOT,",
            "        sh = true,",
            "        gr = {",
            "            {",
            '                id = "header",',
            '                type = "slide",',
            '                link = "AMCM_Banner.dds",',
            f'                text = "ui_mcm_{option_root}_header",',
            "                size = {512, 50},",
            "                spacing = 20,",
            "            },",
            "            {",
            '                id = "enable_feature",',
            '                type = "check",',
            "                val = 1,",
            "                def = true,",
            "            },",
            "        },",
            "    }",
            "    return options",
            "end",
            "",
        ]
    )


def starter_mcm_localizations(option_root: str, display_name: str) -> dict[str, list[tuple[str, str]]]:
    return {
        "eng": [
            (f"ui_mcm_menu_{option_root}", display_name),
            (f"ui_mcm_{option_root}_header", f"{display_name} Settings"),
            (f"ui_mcm_{option_root}_enable_feature", "Enable feature"),
            (
                f"ui_mcm_{option_root}_enable_feature_desc",
                "Toggle the starter feature for this project.",
            ),
        ],
        "rus": [
            (f"ui_mcm_menu_{option_root}", display_name),
            (f"ui_mcm_{option_root}_header", f"Настройки {display_name}"),
            (f"ui_mcm_{option_root}_enable_feature", "Включить функцию"),
            (
                f"ui_mcm_{option_root}_enable_feature_desc",
                "Переключает стартовую функцию для этого проекта.",
            ),
        ],
    }


def starter_localization_pack_comment() -> dict[str, list[tuple[str, str]]]:
    return {
        "eng": [],
        "rus": [],
    }


def starter_dltx_patch(project_name: str, target_root: str) -> str:
    return "\n".join(
        [
            f"; DLTX scaffold for {project_name}",
            f"; Target root: {target_root}",
            "",
            "; ![existing_section]",
            "; !field_to_remove",
            '; >csv_list = token_to_add',
            '; <csv_list = token_to_remove',
            "",
            "; @[new_section]",
            "; parent_section =",
            "; key = value",
            "",
            "; !![obsolete_section]",
            "",
        ]
    )


def starter_dxml_patch(target_xml: str) -> str:
    target_xml_backslash = target_xml.replace("/", "\\")
    return "\n".join(
        [
            f"local TARGET_XML = [[{target_xml_backslash}]]",
            "",
            "function on_xml_read()",
            '    RegisterScriptCallback("on_xml_read", function(xml_file_name, xml_obj)',
            "        if xml_file_name ~= TARGET_XML then",
            "            return",
            "        end",
            "",
            "        -- Apply a narrow XML diff here.",
            "    end)",
            "end",
            "",
        ]
    )


def project_metadata_summary(project_root: Path, metadata: dict[str, Any]) -> str:
    kinds = ",".join(template_kinds(metadata)) or "none"
    source = metadata.get("source")
    source_summary = ""
    if isinstance(source, dict) and source.get("kind"):
        source_summary = f" [source={source['kind']}]"
    return (
        f"{metadata['project_name']}: {project_root.resolve()} "
        f"[display_name={metadata['display_name']}] [templates={kinds}]{source_summary}"
    )


def ensure_project_files_exist(project_root: Path, relpaths: list[str]) -> list[str]:
    missing = []
    for relpath in relpaths:
        candidate = project_root / normalize_rel_path(relpath)
        if not candidate.exists():
            missing.append(relpath)
    return missing


def read_text_strict(path: Path) -> str:
    text, _ = read_text_auto(path, errors="strict")
    return text


def path_in_mod_root(project_root: Path, relpath: str) -> Path:
    return project_root / normalize_rel_path(relpath)


def path_to_repo_relative(path: Path) -> str:
    return repo_relative(path)


def find_on_mcm_load_bodies(text: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(r"""function\s+on_mcm_load\b[^(]*\([^)]*\)(.*?)\nend\b""", text, re.DOTALL)
    ]


def file_looks_cp1251(path: Path) -> bool:
    _, meta = read_text_auto(path, errors="strict")
    return meta.get("codec") == "cp1251"


def detect_declared_encoding(path: Path) -> str | None:
    _, meta = read_text_auto(path, errors="strict")
    return meta.get("declared_encoding")


def packaging_ignore_entries(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in PACKAGING_EXCLUDED_DIR_NAMES or name in PACKAGING_EXCLUDED_FILE_NAMES:
            ignored.add(name)
            continue
        full = Path(directory) / name
        if full.is_dir() and name == "__pycache__":
            ignored.add(name)
            continue
        if full.is_file() and full.suffix.lower() in TEMPORARY_ARTIFACT_SUFFIXES:
            ignored.add(name)
    return ignored


def load_json(path: Path) -> dict[str, Any]:
    data = load_json_file(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data
