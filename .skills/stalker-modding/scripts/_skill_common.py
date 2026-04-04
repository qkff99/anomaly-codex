#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parents[1]
MANIFESTS_DIR = SKILL_ROOT / "manifests"
OVERLAY_CANDIDATES = (
    ".codex-stalker/workspace.json",
    ".codex-stalker/workspace.yml",
    ".codex-stalker/workspace.yaml",
)
WORKSPACE_OVERLAY_JSON = ".codex-stalker/workspace.json"
PROJECT_OVERLAY_CANDIDATES = (
    ".codex-stalker/project.json",
)
XML_DECL_ENCODING_RE = re.compile(r"""<\?xml[^>]*encoding\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
XML_START_TAG_RE = re.compile(r"""^\ufeff?\s*(?:<\?xml[^>]*\?>\s*)?(?:<!--.*?-->\s*)*<([A-Za-z_][\w:.-]*)""", re.DOTALL)
XML_DECL_ENCODING_ATTR_RE = re.compile(r"""encoding\s*=\s*["'][^"']+["']""", re.IGNORECASE)
ENCODING_ALIASES = {
    "utf8": "utf-8",
    "utf-8": "utf-8",
    "utf-8-sig": "utf-8-sig",
    "cp1251": "cp1251",
    "windows-1251": "cp1251",
    "win-1251": "cp1251",
}


def _is_working_ripgrep(candidate: Path) -> bool:
    if not candidate.exists() or not candidate.is_file():
        return False
    try:
        completed = subprocess.run(
            [str(candidate), "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    output = ((completed.stdout or "") + (completed.stderr or "")).lower()
    return completed.returncode == 0 and "ripgrep" in output


def resolve_ripgrep_command() -> Path | None:
    candidates: list[Path] = []

    override = os.environ.get("STALKER_RG")
    if override:
        candidates.append(Path(override).expanduser())

    for name in ("rg", "rg.exe"):
        resolved = shutil.which(name)
        if resolved:
            candidates.append(Path(resolved))

    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            local_root = Path(local_app)
            candidates.append(local_root / "Microsoft" / "WinGet" / "Links" / "rg.exe")
            packages_root = local_root / "Microsoft" / "WinGet" / "Packages"
            if packages_root.exists():
                candidates.extend(candidate for candidate in packages_root.rglob("rg.exe"))

        program_data = os.environ.get("ProgramData")
        if program_data:
            data_root = Path(program_data)
            candidates.extend(
                [
                    data_root / "chocolatey" / "bin" / "rg.exe",
                    data_root / "chocolatey" / "lib" / "ripgrep" / "tools" / "rg.exe",
                    data_root / "chocolatey" / "lib" / "ripgrep" / "tools" / "bin" / "rg.exe",
                ]
            )

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            resolved = candidate.expanduser()
        key = str(resolved).casefold()
        if key in seen:
            continue
        seen.add(key)
        if _is_working_ripgrep(resolved):
            return resolved

    return None


def load_structured_file(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yml", ".yaml"}:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                f"PyYAML is required to read {path.name}. "
                f"Prefer the JSON variant when running in a clean environment."
            ) from exc
        return yaml.safe_load(text)
    raise ValueError(f"Unsupported structured file format: {path}")


def load_manifest(name: str) -> Any:
    for suffix in (".json", ".yml", ".yaml"):
        path = MANIFESTS_DIR / f"{name}{suffix}"
        if path.exists():
            return load_structured_file(path)
    raise FileNotFoundError(f"Manifest not found: {name}")


def find_nearest_structured_file(start: Path, candidates: tuple[str, ...]) -> Path | None:
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for probe_root in (current, *current.parents):
        for relative in candidates:
            path = probe_root / relative
            if path.exists():
                return path
    return None


def find_workspace_overlay(root: Path) -> Path | None:
    return find_nearest_structured_file(root, OVERLAY_CANDIDATES)


def find_project_overlay(root: Path) -> Path | None:
    return find_nearest_structured_file(root, PROJECT_OVERLAY_CANDIDATES)


def find_project_root(root: Path) -> Path | None:
    overlay = find_project_overlay(root)
    if overlay is None:
        return None
    return overlay.parent.parent


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def workspace_overlay_json_path(root: Path | None = None) -> Path:
    base = root.resolve() if root else REPO_ROOT
    return base / WORKSPACE_OVERLAY_JSON


def load_workspace_overlay_data(root: Path | None = None) -> tuple[Path, dict[str, Any]]:
    target_root = root or REPO_ROOT
    overlay = find_workspace_overlay(target_root)
    if overlay is None:
        overlay = workspace_overlay_json_path(target_root)
    if not overlay.exists():
        return overlay, {}
    data = load_structured_file(overlay)
    if not isinstance(data, dict):
        raise ValueError(f"workspace overlay must be an object: {overlay}")
    return overlay, data


def save_workspace_overlay_data(data: dict[str, Any], root: Path | None = None) -> Path:
    target = workspace_overlay_json_path(root)
    write_json_file(target, data)
    return target


def workspace_external_paths(root: Path | None = None) -> list[dict[str, Any]]:
    _, data = load_workspace_overlay_data(root)
    entries = data.get("external_paths", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def workspace_known_reference_repos(root: Path | None = None) -> list[dict[str, Any]]:
    _, data = load_workspace_overlay_data(root)
    entries = data.get("known_reference_repos", [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def load_project_metadata(path_or_root: Path) -> dict[str, Any] | None:
    if path_or_root.is_file():
        candidate = path_or_root
    else:
        overlay = find_project_overlay(path_or_root)
        candidate = overlay if overlay else path_or_root / ".codex-stalker" / "project.json"
    if not candidate.exists():
        return None
    data = load_json_file(candidate)
    if not isinstance(data, dict):
        raise ValueError(f"project metadata must be a JSON object: {candidate}")
    return data


def save_project_metadata(project_root: Path, data: dict[str, Any]) -> Path:
    target = project_root / ".codex-stalker" / "project.json"
    write_json_file(target, data)
    return target


def ensure_text_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text_exact(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    ensure_text_parent(path)
    with path.open("w", encoding=encoding, newline="") as handle:
        handle.write(text)


def write_bytes_exact(path: Path, payload: bytes) -> None:
    ensure_text_parent(path)
    path.write_bytes(payload)


def normalize_rel_path(raw: str) -> str:
    return raw.replace("\\", "/").strip("/")


def repo_relative(path: Path) -> str:
    return normalize_rel_path(str(path.resolve().relative_to(REPO_ROOT)))


def relative_to_root(path: Path, root: Path) -> str:
    return normalize_rel_path(str(path.resolve().relative_to(root.resolve())))


def collect_paths(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    results: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in suffixes:
            results.append(path.resolve())
    return sorted(results)


def collect_xml_string_ids(path: Path) -> set[str]:
    text, _ = read_text_auto(path, errors="strict")
    return {
        match.group(1)
        for match in re.finditer(r"""<string\s+id=["']([^"']+)["']""", text)
    }


def path_has_any_suffix(path: Path, suffixes: tuple[str, ...]) -> bool:
    return path.suffix.lower() in suffixes


def is_project_path(path: Path) -> bool:
    try:
        path.resolve().relative_to((REPO_ROOT / "projects").resolve())
        return True
    except ValueError:
        return False
    return None


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def canonicalize_task(task: str, aliases: dict[str, str], tasks: dict[str, Any]) -> str | None:
    normalized = task.strip().lower()
    if normalized in tasks:
        return normalized
    return aliases.get(normalized)


def normalize_encoding_name(name: str | None) -> str | None:
    if not name:
        return None
    normalized = name.strip().lower().replace("_", "-")
    return ENCODING_ALIASES.get(normalized, normalized)


def parse_xml_declared_encoding(raw: bytes) -> str | None:
    head = raw[:512].decode("ascii", errors="ignore")
    match = XML_DECL_ENCODING_RE.search(head)
    if not match:
        return None
    return match.group(1).strip()


def path_looks_like_localization_xml(path: Path) -> bool:
    lowered = [part.lower() for part in path.parts]
    for index in range(len(lowered) - 2):
        if lowered[index] == "configs" and lowered[index + 1] == "text":
            return True
    return False


def detect_newline_style(text: str) -> str:
    if "\r\n" in text:
        return "crlf"
    if "\r" in text:
        return "cr"
    return "lf"


def normalize_newlines(text: str, style: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if style == "crlf":
        return normalized.replace("\n", "\r\n")
    if style == "cr":
        return normalized.replace("\n", "\r")
    return normalized


def detect_xml_root_tag(text: str) -> str | None:
    match = XML_START_TAG_RE.search(text[:2048])
    if not match:
        return None
    return match.group(1)


def rewrite_xml_declaration_encoding(text: str, encoding_name: str) -> str:
    if not encoding_name:
        return text

    declaration_match = re.match(r"""^(\ufeff?\s*<\?xml\b)([^>]*)(\?>)""", text, re.IGNORECASE | re.DOTALL)
    if not declaration_match:
        return text

    start, middle, end = declaration_match.groups()
    if XML_DECL_ENCODING_ATTR_RE.search(middle):
        updated_middle = XML_DECL_ENCODING_ATTR_RE.sub(f'encoding="{encoding_name}"', middle, count=1)
    else:
        updated_middle = f'{middle} encoding="{encoding_name}"'

    updated = f"{start}{updated_middle}{end}"
    return updated + text[declaration_match.end():]


def detect_xml_text_metadata(path: Path, raw: bytes) -> dict[str, Any]:
    declared_encoding = parse_xml_declared_encoding(raw)
    normalized_declared = normalize_encoding_name(declared_encoding)
    has_bom = raw.startswith(b"\xef\xbb\xbf")

    codec: str
    detection_source: str

    if has_bom:
        codec = "utf-8-sig"
        detection_source = "bom"
    elif normalized_declared:
        codec = normalized_declared
        detection_source = "xml-declaration"
        try:
            raw.decode(codec)
        except (LookupError, UnicodeDecodeError):
            codec = "utf-8"
            detection_source = "utf8-fallback"
    else:
        try:
            raw.decode("utf-8")
            codec = "utf-8"
            detection_source = "utf8-probe"
        except UnicodeDecodeError:
            codec = "cp1251"
            detection_source = "legacy-fallback"

    return {
        "codec": codec,
        "declared_encoding": declared_encoding,
        "normalized_declared_encoding": normalized_declared,
        "had_xml_declaration": raw.lstrip().startswith(b"<?xml"),
        "had_utf8_bom": has_bom,
        "detection_source": detection_source,
        "path_looks_like_localization_xml": path_looks_like_localization_xml(path),
    }


def read_text_auto(path: Path, *, errors: str = "strict") -> tuple[str, dict[str, Any]]:
    raw = path.read_bytes()

    if path.suffix.lower() == ".xml":
        meta = detect_xml_text_metadata(path, raw)
        try:
            text = raw.decode(meta["codec"], errors=errors)
        except LookupError:
            text = raw.decode("utf-8", errors=errors)
            meta["codec"] = "utf-8"
            meta["detection_source"] = "utf8-fallback"
        meta["newline"] = detect_newline_style(text)
        meta["root_tag"] = detect_xml_root_tag(text)
        meta["is_localization_xml"] = bool(
            meta["path_looks_like_localization_xml"] or meta["root_tag"] == "string_table"
        )
        return text, meta

    text = raw.decode("utf-8", errors=errors)
    return text, {
        "codec": "utf-8",
        "declared_encoding": None,
        "normalized_declared_encoding": None,
        "had_xml_declaration": False,
        "had_utf8_bom": False,
        "detection_source": "utf8-default",
        "newline": detect_newline_style(text),
        "root_tag": None,
        "is_localization_xml": False,
        "path_looks_like_localization_xml": False,
    }
