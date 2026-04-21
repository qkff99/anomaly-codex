#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


DETECT_FILE = "detect.py"
EXTRACT_FILE = "extract.py"


def locate_graphify_root() -> Path:
    spec = importlib.util.find_spec("graphify")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("graphifyy is not installed.")
    return Path(next(iter(spec.submodule_search_locations))).resolve()


def _ensure_detect_script_extension(text: str) -> tuple[str, bool]:
    if "'.script'" in text:
        return text, False
    needle = "'.lua'"
    if needle not in text:
        raise RuntimeError("graphify detect.py no longer contains the expected .lua extension entry.")
    return text.replace(needle, "'.lua', '.script'", 1), True


def _ensure_extract_script_dispatch(text: str) -> tuple[str, bool]:
    changed = False
    if '".script": extract_lua' not in text:
        needle = '        ".lua": extract_lua,\n'
        if needle not in text:
            raise RuntimeError("graphify extract.py no longer contains the expected Lua dispatch entry.")
        text = text.replace(needle, needle + '        ".script": extract_lua,\n', 1)
        changed = True
    collect_files_index = text.find("def collect_files(")
    collect_files_tail = text[collect_files_index:] if collect_files_index >= 0 else text
    if '".script",' not in collect_files_tail:
        needle = '".lua",'
        if needle not in collect_files_tail:
            raise RuntimeError("graphify extract.py no longer contains the expected Lua extension entry.")
        prefix = text[:collect_files_index] if collect_files_index >= 0 else ""
        suffix = collect_files_tail.replace(needle, '".lua", ".script",', 1)
        text = prefix + suffix
        changed = True
    return text, changed


def patch_graphify_for_stalker() -> tuple[bool, str]:
    root = locate_graphify_root()
    detect_path = root / DETECT_FILE
    extract_path = root / EXTRACT_FILE
    if not detect_path.exists() or not extract_path.exists():
        raise RuntimeError(f"graphify package layout is unexpected under {root}")

    detect_text = detect_path.read_text(encoding="utf-8")
    new_detect_text, detect_changed = _ensure_detect_script_extension(detect_text)
    if detect_changed:
        detect_path.write_text(new_detect_text, encoding="utf-8")

    extract_text = extract_path.read_text(encoding="utf-8")
    new_extract_text, extract_changed = _ensure_extract_script_dispatch(extract_text)
    if extract_changed:
        extract_path.write_text(new_extract_text, encoding="utf-8")

    changed = detect_changed or extract_changed
    if changed:
        return True, "graphify patched for .script Lua support"
    return False, "graphify already patched for .script Lua support"


def patch_status() -> dict[str, bool]:
    root = locate_graphify_root()
    detect_path = root / DETECT_FILE
    extract_path = root / EXTRACT_FILE
    detect_text = detect_path.read_text(encoding="utf-8")
    extract_text = extract_path.read_text(encoding="utf-8")
    collect_files_index = extract_text.find("def collect_files(")
    collect_files_tail = extract_text[collect_files_index:] if collect_files_index >= 0 else ""
    return {
        "detect_has_script_extension": "'.script'" in detect_text,
        "extract_has_script_dispatch": '".script": extract_lua' in extract_text,
        "extract_collects_script_extension": '".script",' in collect_files_tail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure the installed graphify package treats .script as Lua.")
    parser.add_argument("command", choices=("ensure", "status"))
    args = parser.parse_args()

    if args.command == "ensure":
        changed, message = patch_graphify_for_stalker()
        print(message)
        return 0

    status = patch_status()
    for key, value in status.items():
        print(f"{key}={str(value).lower()}")
    return 0 if all(status.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
