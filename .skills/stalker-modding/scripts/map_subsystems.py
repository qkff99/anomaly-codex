#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path


SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".idea",
    ".vscode",
    "node_modules",
    ".frontmatter",
    ".vs",
    ".agents",
    ".codex-stalker",
    ".skills",
    "plugins",
    "help",
}
TEXT_EXTS = {".script", ".lua", ".xml", ".ltx", ".md", ".json", ".yml", ".yaml", ".txt", ".h", ".hpp", ".cpp", ".c"}
MAX_DEPTH = 8
MAX_FILES = 12000


def classify(path: Path) -> str:
    text = path.as_posix().lower()
    if "ai_workspace/lua_help.script.txt" in text:
        return "engine-capability"
    if "ai_workspace/src" in text or "/xrengine/" in text:
        return "engine-capability"
    if "/gamedata/scripts/" in text:
        if any(token in text for token in ("legs", "visible_body", "freelook", "ladder")):
            return "visible-body-legs"
        if any(token in text for token in ("weapon", "hud", "wpn", "scope", "zoom")):
            return "weapons-hud"
        if any(token in text for token in ("task", "story", "smart", "gulag", "alife", "squad")):
            return "tasks-story-alife"
        if any(token in text for token in ("ui_", "mcm", "options", "pda")):
            return "ui-mcm"
        return "scripting-runtime"
    if "/gamedata/configs/ui/" in text or "/gamedata/configs/text/" in text:
        return "ui-mcm"
    if any(token in text for token in ("meshes", "textures", "animations", ".blend", ".skl", ".omf", ".ogf", ".dds")):
        return "assets-animations"
    if any(token in text for token in ("rawdata", "sdk", "levels", ".level", ".cform", ".spawn")):
        return "mapping-sdk"
    if "docs/" in text or text.endswith(".md"):
        return "docs"
    return "unknown"


def iter_files(root: Path):
    root = root.resolve()
    root_depth = len(root.parts)
    seen = 0

    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)
        depth = len(current_path.parts) - root_depth
        dirs[:] = [
            name
            for name in dirs
            if name not in SKIP_DIRS and depth < MAX_DEPTH
        ]

        for name in files:
            path = current_path / name
            if path.suffix.lower() not in TEXT_EXTS and path.suffix != "":
                continue
            yield path
            seen += 1
            if seen >= MAX_FILES:
                return


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    buckets: dict[str, list[str]] = defaultdict(list)
    counts: Counter[str] = Counter()
    for path in iter_files(root):
        key = classify(path)
        rel = path.relative_to(root).as_posix()
        counts[key] += 1
        if len(buckets[key]) < 25:
            buckets[key].append(rel)

    output = {
        "root": str(root),
        "subsystems": {
            key: {
                "file_count": counts[key],
                "sample_files": paths,
            }
            for key, paths in sorted(buckets.items())
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
