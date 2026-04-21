#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from _skill_common import REPO_ROOT, collect_xml_string_ids, load_manifest, read_text_auto


SCRIPT_SUFFIXES = {".lua", ".script"}
TEXT_SUFFIXES = {".lua", ".script", ".ltx", ".xml"}
SKIP_DIRS = {
    ".agents",
    ".codex-stalker",
    ".git",
    ".idea",
    ".skills",
    ".vscode",
    "__pycache__",
    "ai_workspace",
    "dist",
    "help",
    "node_modules",
    "plugins",
    "tests",
}
VANILLA_GAMEDATA = REPO_ROOT / "ai_workspace" / "vanilla scripts" / "gamedata"
SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3}
GENERIC_DEFAULTS = {"config", "menu", "mcm", "mod", "my_mod", "on_update", "options", "root", "settings", "test", "update"}
ALLOWED_GLOBAL_FUNCTIONS = {
    "get_config",
    "load_state",
    "on_game_start",
    "on_mcm_load",
    "on_option_change",
    "on_xml_read",
    "save_state",
}
ALLOWED_GLOBAL_ASSIGNMENTS = {"_G"}
TABLE_FIELD_KEYS = {
    "def",
    "enable_feature",
    "gr",
    "id",
    "link",
    "sh",
    "size",
    "spacing",
    "text",
    "type",
    "val",
}
LOCALIZATION_REF_RE = re.compile(r"""["']((?:ui_mcm|st)_[A-Za-z0-9_]+)["']""")
REQUIRE_RE = re.compile(r"""require\s*(?:\(?\s*)["']([^"']+)["']""")
CALLBACK_RE = re.compile(r"""(?:RegisterScriptCallback|AddScriptCallback)\s*\(\s*["']([^"']+)["']""")
ID_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
SECTION_RE = re.compile(r"""^\s*\[([^\]]+)\]""")
FUNCTION_DEF_RE = re.compile(r"""^\s*(local\s+)?function\s+([A-Za-z_][A-Za-z0-9_.:]*)\s*\(([^)]*)\)""")
LOCAL_FUNCTION_RE = re.compile(r"""^\s*local\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*function\s*\(([^)]*)\)""")
CALL_RE = re.compile(r"""\b([A-Za-z_][A-Za-z0-9_.:]*)\s*\(""")
LUA_KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "for", "function", "if", "in", "local", "not", "or", "repeat", "return", "then", "until", "while"}


@dataclass(frozen=True)
class Issue:
    rule_id: str
    severity: str
    category: str
    path: str
    line: int
    subsystem: str
    message: str
    suggestion: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "category": self.category,
            "path": self.path,
            "line": self.line,
            "subsystem": self.subsystem,
            "message": self.message,
            "suggestion": self.suggestion,
            "evidence": self.evidence,
        }


class Scanner:
    def __init__(self, root: Path, task: str) -> None:
        self.root = root.resolve()
        self.task = task
        self.rules_manifest = load_manifest("quality_rules")
        self.rules: dict[str, dict[str, Any]] = self.rules_manifest.get("rules", {})
        self.generic_names = set(self.rules_manifest.get("generic_names", [])) or GENERIC_DEFAULTS
        self.issues: list[Issue] = []
        self._issue_keys: set[tuple[str, str, int, str]] = set()
        self.localization_ids: set[str] = set()
        self.vanilla_delta: list[dict[str, Any]] = []
        self.patch_opportunities: list[dict[str, Any]] = []
        self.conflict_surface: dict[str, set[str]] = {
            "script_names": set(),
            "mcm_roots": set(),
            "callbacks": set(),
            "sections": set(),
            "xml_ids": set(),
        }
        self.dependency_graph: dict[str, dict[str, Any]] = {}
        self.files_scanned = 0

    def relpath(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            try:
                return path.resolve().relative_to(REPO_ROOT).as_posix()
            except ValueError:
                return path.as_posix()

    def add_issue(self, rule_id: str, path: Path, line: int, evidence: str = "") -> None:
        meta = self.rules.get(rule_id)
        if not meta:
            raise KeyError(f"unknown quality rule: {rule_id}")
        relpath = self.relpath(path)
        clean_evidence = evidence.strip()
        key = (rule_id, relpath, line, clean_evidence)
        if key in self._issue_keys:
            return
        self._issue_keys.add(key)
        self.issues.append(
            Issue(
                rule_id=rule_id,
                severity=str(meta.get("severity", "medium")),
                category=str(meta.get("category", "quality")),
                path=relpath,
                line=line,
                subsystem=classify_path(path),
                message=str(meta.get("message", rule_id)),
                suggestion=str(meta.get("suggestion", "")),
                evidence=clean_evidence,
            )
        )

    def scan(self) -> dict[str, Any]:
        self.scan_root_shape()
        files = list(iter_scan_files(self.root))
        self.collect_localization_ids(files)
        self.collect_conflict_surface(files)
        for path in files:
            self.files_scanned += 1
            self.scan_file(path)
        return self.report()

    def collect_localization_ids(self, files: list[Path]) -> None:
        for path in files:
            if path.suffix.lower() != ".xml" or not path_looks_like_text_xml(path):
                continue
            try:
                self.localization_ids.update(collect_xml_string_ids(path))
            except Exception:
                continue

    def collect_conflict_surface(self, files: list[Path]) -> None:
        for path in files:
            rel = self.relpath(path).replace("\\", "/")
            if path.suffix.lower() in SCRIPT_SUFFIXES and "/gamedata/scripts/" in f"/{rel}":
                self.conflict_surface["script_names"].add(path.stem)
            if path.suffix.lower() == ".xml":
                try:
                    for string_id in collect_xml_string_ids(path):
                        self.conflict_surface["xml_ids"].add(string_id)
                except Exception:
                    pass

    def scan_file(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix in SCRIPT_SUFFIXES:
            self.scan_lua(path)
        elif suffix == ".xml":
            self.scan_xml(path)
        elif suffix == ".ltx":
            self.scan_ltx(path)
        self.scan_patch_strategy(path)

    def scan_root_shape(self) -> None:
        if not self.root.is_dir() or not (self.root / "gamedata").is_dir():
            return
        for entry in sorted(self.root.iterdir()):
            if entry.name in {"gamedata", ".codex-stalker", "dist", "__pycache__"}:
                continue
            if entry.is_file():
                self.add_issue("IMPORT_TOP_LEVEL_IGNORED", entry, 1, entry.name)

    def scan_lua(self, path: Path) -> None:
        text, _ = safe_read_text(path)
        lines = text.splitlines()
        rel = self.relpath(path)
        graph = build_lua_graph(text, lines)
        self.dependency_graph[rel] = graph

        for callback in graph["callbacks"]:
            self.conflict_surface["callbacks"].add(callback)
            if callback in self.generic_names:
                self.add_issue("NAMING_GENERIC_ID", path, find_first_line(lines, callback), callback)

        if is_mcm_script(path, text):
            self.scan_mcm(path, lines, text)

        self.scan_lua_lines(path, lines, graph)
        self.scan_hot_paths(path, lines)
        self.scan_save_state(path, lines, text)
        self.scan_localization_refs(path, lines)

    def scan_lua_lines(self, path: Path, lines: list[str], graph: dict[str, Any]) -> None:
        local_names = collect_lua_local_names(lines)
        on_game_start_ranges = function_ranges(lines, {"on_game_start"})
        for index, raw_line in enumerate(lines):
            line_no = index + 1
            line = strip_lua_comment(raw_line)
            if not line.strip():
                continue

            assign_match = re.match(r"""^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=""", line)
            if assign_match and not line.lstrip().startswith(("local ", "for ", "if ", "elseif ", "return ")):
                name = assign_match.group(1)
                if (
                    name not in ALLOWED_GLOBAL_ASSIGNMENTS
                    and name not in local_names
                    and name not in TABLE_FIELD_KEYS
                    and not name.isupper()
                    and not line.rstrip().endswith(",")
                ):
                    self.add_issue("LUA_HIDDEN_GLOBAL", path, line_no, raw_line)

            fn_match = re.match(r"""^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(""", line)
            if fn_match:
                name = fn_match.group(1)
                if name not in ALLOWED_GLOBAL_FUNCTIONS and name in self.generic_names:
                    self.add_issue("NAMING_GENERIC_ID", path, line_no, name)

            if "db.actor" in line and not has_db_actor_guard(lines, index):
                self.add_issue("LUA_UNSAFE_DB_ACTOR", path, line_no, raw_line)
            if re.search(r"""\blevel\.""", line) and not has_level_guard(lines, index):
                self.add_issue("LUA_UNSAFE_LEVEL", path, line_no, raw_line)
            if "alife()" in line and not has_alife_guard(lines, index):
                self.add_issue("LUA_UNSAFE_ALIFE", path, line_no, raw_line)
            if "ui_mcm." in line and not has_ui_mcm_guard(lines, index):
                self.add_issue("LUA_OPTIONAL_UI_MCM_UNGUARDED", path, line_no, raw_line)
            if re.search(r"""\bgoto\b|::[A-Za-z_][A-Za-z0-9_]*::|\btable\.pack\b|\btable\.unpack\b""", line):
                self.add_issue("LUA_51_UNSUPPORTED", path, line_no, raw_line)

            monkey_patch = re.match(r"""^\s*([A-Za-z_][A-Za-z0-9_]*(?:\.|\[)[^=]+)\s*=\s*function\b""", line)
            if monkey_patch:
                target = monkey_patch.group(1).strip()
                graph["monkey_patches"].append(target)
                self.add_issue("MONKEY_PATCH", path, line_no, target)

            if any(start <= index <= end for start, end in on_game_start_ranges):
                if ("db.actor" in line and not has_db_actor_guard(lines, index)) or re.search(r"""\blevel\.""", line):
                    self.add_issue("CALLBACK_WORLD_IN_ON_GAME_START", path, line_no, raw_line)

    def scan_hot_paths(self, path: Path, lines: list[str]) -> None:
        ranges = hot_path_ranges(lines)
        for start, end, _name in ranges:
            for index in range(start, end + 1):
                raw_line = lines[index]
                line = strip_lua_comment(raw_line)
                line_no = index + 1
                if "ui_mcm.get" in line:
                    self.add_issue("HOTPATH_UI_MCM_GET", path, line_no, raw_line)
                if re.search(r"""\b(?:pairs|ipairs)\s*\(""", line) or "db.storage" in line:
                    self.add_issue("HOTPATH_FULL_SCAN", path, line_no, raw_line)
                if re.search(r"""\b(?:ini_file|system_ini|game_ini)\b""", line):
                    self.add_issue("HOTPATH_CONFIG_READ", path, line_no, raw_line)
                if re.search(r"""string\.|:gsub\s*\(|:match\s*\(|:format\s*\(""", line):
                    self.add_issue("HOTPATH_STRING_WORK", path, line_no, raw_line)

    def scan_mcm(self, path: Path, lines: list[str], text: str) -> None:
        if not re.search(r"""\bfunction\s+on_mcm_load\s*\(""", text):
            self.add_issue("MCM_MISSING_ON_LOAD", path, 1, path.name)
            return

        for start, end in function_ranges(lines, {"on_mcm_load"}):
            for index in range(start, end + 1):
                raw_line = lines[index]
                line = strip_lua_comment(raw_line)
                if "ui_mcm.get" in line:
                    self.add_issue("MCM_GET_IN_ON_LOAD", path, index + 1, raw_line)

        for index, raw_line in enumerate(lines):
            line = strip_lua_comment(raw_line)
            id_match = ID_RE.search(line)
            if id_match:
                value = id_match.group(1)
                if value in self.generic_names:
                    self.add_issue("MCM_GENERIC_ID", path, index + 1, value)
                if index < 12:
                    self.conflict_surface["mcm_roots"].add(value)
                    graph = self.dependency_graph.get(self.relpath(path))
                    if graph is not None:
                        graph.setdefault("mcm_roots", [])
                        if value not in graph["mcm_roots"]:
                            graph["mcm_roots"].append(value)
            if re.search(r"""type\s*=\s*["']key_bind["']""", line):
                window = "\n".join(strip_lua_comment(item) for item in lines[index:index + 12])
                val_match = re.search(r"""\bval\s*=\s*([0-9]+)""", window)
                if not val_match or val_match.group(1) != "2":
                    self.add_issue("MCM_KEYBIND_VAL", path, index + 1, raw_line)

    def scan_save_state(self, path: Path, lines: list[str], text: str) -> None:
        if not re.search(r"""\b(save_state|load_state|actor_binder\s*:\s*save|function\s+[A-Za-z0-9_.]+:save)\b""", text):
            return
        if "STATE_VERSION" not in text:
            self.add_issue("SAVE_MISSING_VERSION", path, 1, "missing STATE_VERSION")
        save_ranges = function_ranges(lines, {"save_state", "save"})
        for index, raw_line in enumerate(lines):
            line = strip_lua_comment(raw_line)
            in_save_body = any(start <= index <= end for start, end in save_ranges)
            if in_save_body and re.search(r"""=\s*(?:db\.actor|level\.object_by_id|function\b)""", line):
                self.add_issue("SAVE_NON_SERIALIZABLE", path, index + 1, raw_line)

    def scan_localization_refs(self, path: Path, lines: list[str]) -> None:
        if path_looks_like_text_xml(path):
            return
        for index, raw_line in enumerate(lines):
            for match in LOCALIZATION_REF_RE.finditer(raw_line):
                string_id = match.group(1)
                if string_id not in self.localization_ids:
                    self.add_issue("LOCALIZATION_MISSING_ID", path, index + 1, string_id)

    def scan_xml(self, path: Path) -> None:
        text, meta = safe_read_text(path)
        if meta.get("is_localization_xml") and meta.get("codec") == "cp1251":
            self.add_issue("LOCALIZATION_LEGACY_ENCODING", path, 1, f"codec={meta.get('codec')}")
        for match in ID_RE.finditer(text):
            value = match.group(1)
            if value in self.generic_names:
                self.add_issue("NAMING_GENERIC_ID", path, line_for_offset(text, match.start()), value)

    def scan_ltx(self, path: Path) -> None:
        text, _ = safe_read_text(path)
        for index, raw_line in enumerate(text.splitlines()):
            section = SECTION_RE.match(raw_line)
            if not section:
                continue
            value = section.group(1).strip("@![]")
            self.conflict_surface["sections"].add(value)
            if value in self.generic_names:
                self.add_issue("NAMING_GENERIC_ID", path, index + 1, value)

    def scan_patch_strategy(self, path: Path) -> None:
        gamedata_rel = gamedata_relative(path)
        if not gamedata_rel:
            return
        vanilla_path = VANILLA_GAMEDATA / gamedata_rel
        status = "overrides-vanilla" if vanilla_path.exists() else "new-file"
        self.vanilla_delta.append(
            {
                "path": self.relpath(path),
                "gamedata_path": gamedata_rel,
                "status": status,
            }
        )
        rel_lower = gamedata_rel.lower()
        if status != "overrides-vanilla":
            return
        if "/configs/text/" in f"/{rel_lower}":
            return
        if path.suffix.lower() == ".xml":
            self.add_issue("PATCH_FULL_XML_OVERRIDE", path, 1, gamedata_rel)
            self.patch_opportunities.append({"path": self.relpath(path), "preferred": "DXML", "target": gamedata_rel})
        elif path.suffix.lower() == ".ltx" and not path.name.lower().startswith("mod_"):
            self.add_issue("PATCH_FULL_LTX_OVERRIDE", path, 1, gamedata_rel)
            self.patch_opportunities.append({"path": self.relpath(path), "preferred": "DLTX", "target": gamedata_rel})

    def report(self) -> dict[str, Any]:
        ordered = sorted(
            self.issues,
            key=lambda issue: (-SEVERITY_RANK.get(issue.severity, 2), issue.path, issue.line, issue.rule_id),
        )
        severity_counts: dict[str, int] = {key: 0 for key in ("high", "medium", "low", "info")}
        category_counts: dict[str, int] = {}
        score_map = self.rules_manifest.get("severity_scores", {})
        risk_score = 0
        for issue in ordered:
            severity_counts[issue.severity] = severity_counts.get(issue.severity, 0) + 1
            category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
            risk_score += int(score_map.get(issue.severity, 0))
        risk_level = "high" if severity_counts.get("high") else "medium" if severity_counts.get("medium") else "low" if severity_counts.get("low") else "clean"
        task_gates = self.rules_manifest.get("task_gates", {}).get(self.task, [])
        return {
            "root": str(self.root),
            "task": self.task,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "summary": {
                "files_scanned": self.files_scanned,
                "issues": len(ordered),
                "severity_counts": severity_counts,
                "category_counts": category_counts,
                "task_gates": task_gates,
            },
            "issues": [issue.to_dict() for issue in ordered],
            "vanilla_delta": sorted(self.vanilla_delta, key=lambda item: item["path"]),
            "patch_opportunities": sorted(self.patch_opportunities, key=lambda item: item["path"]),
            "conflict_surface": {
                key: sorted(values)
                for key, values in self.conflict_surface.items()
                if values
            },
            "dependency_graph": self.dependency_graph,
            "source_tier_markers": ["verified local", "verified MCP", "inference"],
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Static quality scanner for STALKER Anomaly workbench projects.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    scan = subparsers.add_parser("scan", help="Scan a mod/project root or file.")
    scan.add_argument("path", help="File or directory to scan.")
    scan.add_argument("--task", default="code-review", help="Task type for gate selection.")
    scan.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    scan.add_argument(
        "--fail-on",
        choices=("info", "low", "medium", "high"),
        help="Return non-zero when any issue at or above this severity is found.",
    )

    explain = subparsers.add_parser("explain-rule", help="Explain a quality rule.")
    explain.add_argument("rule_id", help="Rule id to explain.")

    graph = subparsers.add_parser("graph", help="Print dependency graph, exports, callbacks, and patch surfaces.")
    graph.add_argument("path", help="File or directory to graph.")
    graph.add_argument("--task", default="code-review", help="Task type for gate selection.")
    graph.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    suggest = subparsers.add_parser("suggest-patch", help="Suggest a minimal DLTX/DXML patch scaffold for an overriding file.")
    suggest.add_argument("path", help="Overriding .ltx or .xml file under a gamedata tree.")
    suggest.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    save_template = subparsers.add_parser("save-template", help="Generate a save/load migration template.")
    save_template.add_argument("module", help="Module key/stem for the save state table.")
    save_template.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    optional = subparsers.add_parser("optional-pattern", help="Print optional dependency guard patterns.")
    optional.add_argument("pattern", nargs="?", default="list", help="Pattern id, or list.")
    optional.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    return parser.parse_args()


def iter_scan_files(root: Path) -> Iterable[Path]:
    root = root.expanduser().resolve()
    if root.is_file():
        if root.suffix.lower() in TEXT_SUFFIXES:
            yield root
        return

    for current_raw, dirs, files in os.walk(root):
        current = Path(current_raw)
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in files:
            path = current / name
            if path.suffix.lower() in TEXT_SUFFIXES:
                yield path.resolve()


def safe_read_text(path: Path) -> tuple[str, dict[str, Any]]:
    try:
        return read_text_auto(path, errors="replace")
    except Exception:
        raw = path.read_bytes()
        return raw.decode("utf-8", errors="replace"), {"codec": "utf-8", "is_localization_xml": False}


def strip_lua_comment(line: str) -> str:
    if "--" not in line:
        return line
    return line.split("--", 1)[0]


def classify_path(path: Path) -> str:
    text = path.as_posix().lower()
    if "/gamedata/scripts/" in text:
        if "mcm" in path.name.lower() or "ui_" in path.name.lower():
            return "ui-mcm"
        if any(token in text for token in ("weapon", "hud", "wpn", "scope", "zoom")):
            return "weapons-hud"
        if any(token in text for token in ("task", "story", "smart", "alife", "squad")):
            return "tasks-story-alife"
        return "scripting-runtime"
    if "/gamedata/configs/ui/" in text or "/gamedata/configs/text/" in text:
        return "ui-mcm"
    if any(token in text for token in ("meshes", "textures", "animations")):
        return "assets-animations"
    if "/gamedata/configs/" in text:
        return "config"
    return "unknown"


def path_looks_like_text_xml(path: Path) -> bool:
    parts = [part.lower() for part in path.parts]
    return any(parts[index:index + 2] == ["configs", "text"] for index in range(len(parts) - 1))


def is_mcm_script(path: Path, text: str) -> bool:
    return path.name.lower().endswith("_mcm.script") or "on_mcm_load" in text


def nearby(lines: list[str], index: int, before: int = 3, after: int = 2) -> str:
    start = max(0, index - before)
    end = min(len(lines), index + after + 1)
    return "\n".join(strip_lua_comment(line).lower() for line in lines[start:end])


def has_db_actor_guard(lines: list[str], index: int) -> bool:
    window = nearby(lines, index)
    return bool(
        re.search(r"""not\s+db\b.*db\.actor|db\s+and\s+db\.actor|db\.actor\s+and|if\s+db\.actor\b""", window, re.DOTALL)
    )


def has_level_guard(lines: list[str], index: int) -> bool:
    window = nearby(lines, index)
    return bool(re.search(r"""not\s+level\b|if\s+level\b|level\s+and""", window))


def has_alife_guard(lines: list[str], index: int) -> bool:
    window = nearby(lines, index, before=1, after=3)
    return bool(re.search(r"""local\s+[A-Za-z_][A-Za-z0-9_]*\s*=\s*alife\(\).*?if\s+not\s+[A-Za-z_][A-Za-z0-9_]*""", window, re.DOTALL))


def has_ui_mcm_guard(lines: list[str], index: int) -> bool:
    window = nearby(lines, index)
    return bool(re.search(r"""if\s+ui_mcm\b|ui_mcm\s+then|ui_mcm\s+and\s+ui_mcm\.""", window))


def collect_lua_local_names(lines: list[str]) -> set[str]:
    names: set[str] = set()
    for raw_line in lines:
        line = strip_lua_comment(raw_line)
        local_match = re.match(r"""^\s*local\s+([A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z_][A-Za-z0-9_]*)*)""", line)
        if local_match:
            for name in local_match.group(1).split(","):
                names.add(name.strip())
        function_match = re.match(r"""^\s*function\s+[A-Za-z_][A-Za-z0-9_.:]*\s*\(([^)]*)\)""", line)
        if function_match:
            for name in function_match.group(1).split(","):
                candidate = name.strip()
                if re.fullmatch(r"""[A-Za-z_][A-Za-z0-9_]*""", candidate):
                    names.add(candidate)
    return names


def parse_lua_params(raw: str) -> list[str]:
    result: list[str] = []
    for item in raw.split(","):
        candidate = item.strip()
        if re.fullmatch(r"""[A-Za-z_][A-Za-z0-9_]*""", candidate):
            result.append(candidate)
    return result


def build_lua_graph(text: str, lines: list[str]) -> dict[str, Any]:
    functions: list[dict[str, Any]] = []
    exports: list[str] = []
    calls: set[str] = set()
    save_functions: set[str] = set()

    for index, raw_line in enumerate(lines):
        line = strip_lua_comment(raw_line)
        def_match = FUNCTION_DEF_RE.match(line)
        if def_match:
            local_prefix, name, params = def_match.groups()
            scope = "local" if local_prefix else "global"
            if ":" in name:
                scope = "method"
            entry = {
                "name": name,
                "line": index + 1,
                "scope": scope,
                "params": parse_lua_params(params),
            }
            functions.append(entry)
            if scope in {"global", "method"}:
                exports.append(name)
            short_name = name.split(":")[-1].split(".")[-1]
            if short_name in {"save", "save_state", "load", "load_state"}:
                save_functions.add(name)
            continue

        local_fn_match = LOCAL_FUNCTION_RE.match(line)
        if local_fn_match:
            name, params = local_fn_match.groups()
            functions.append({"name": name, "line": index + 1, "scope": "local", "params": parse_lua_params(params)})

        for call in CALL_RE.findall(line):
            head = call.split(".")[0].split(":")[0]
            if call in LUA_KEYWORDS or head in LUA_KEYWORDS:
                continue
            calls.add(call)

    return {
        "requires": sorted(set(REQUIRE_RE.findall(text))),
        "callbacks": sorted(set(CALLBACK_RE.findall(text))),
        "functions": sorted(functions, key=lambda item: (item["line"], item["name"])),
        "exports": sorted(set(exports)),
        "calls": sorted(calls),
        "save_functions": sorted(save_functions),
        "mcm_roots": [],
        "monkey_patches": [],
    }


def function_ranges(lines: list[str], names: set[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for index, raw_line in enumerate(lines):
        line = strip_lua_comment(raw_line)
        match = re.match(r"""^\s*function\s+([A-Za-z_][A-Za-z0-9_.:]*)\s*\(""", line)
        if not match:
            continue
        name = match.group(1).split(":")[-1].split(".")[-1]
        if name not in names:
            continue
        ranges.append((index, find_simple_function_end(lines, index)))
    return ranges


def hot_path_ranges(lines: list[str]) -> list[tuple[int, int, str]]:
    ranges: list[tuple[int, int, str]] = []
    for index, raw_line in enumerate(lines):
        line = strip_lua_comment(raw_line)
        match = re.match(r"""^\s*function\s+([A-Za-z_][A-Za-z0-9_.:]*)\s*\(""", line)
        if not match:
            continue
        name = match.group(1).lower()
        if "actor_on_update" in name or name.endswith(":update") or name.endswith(".update") or name.endswith("on_update"):
            ranges.append((index, find_simple_function_end(lines, index), name))
    return ranges


def find_simple_function_end(lines: list[str], start: int) -> int:
    for index in range(start + 1, len(lines)):
        if re.match(r"""^\s*end\s*,?\s*$""", strip_lua_comment(lines[index])):
            return index
    return len(lines) - 1


def find_first_line(lines: list[str], token: str) -> int:
    for index, line in enumerate(lines, 1):
        if token in line:
            return index
    return 1


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def gamedata_relative(path: Path) -> str | None:
    parts = path.resolve().parts
    lowered = [part.lower() for part in parts]
    if "gamedata" not in lowered:
        return None
    index = lowered.index("gamedata")
    if index >= len(parts) - 1:
        return None
    return "/".join(parts[index + 1:])


def print_text_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"root: {report['root']}")
    print(f"task: {report['task']}")
    print(f"risk_level: {report['risk_level']}")
    print(f"risk_score: {report['risk_score']}")
    print(f"files_scanned: {summary['files_scanned']}")
    print(f"issues: {summary['issues']}")
    print("[severity_counts]")
    for key, value in summary["severity_counts"].items():
        print(f"{key}: {value}")
    print()
    print("[task_gates]")
    for gate in summary.get("task_gates", []) or ["none"]:
        print(gate)
    print()
    print("[issues]")
    if not report["issues"]:
        print("none")
    for issue in report["issues"]:
        print(f"{issue['severity'].upper()} {issue['rule_id']} {issue['path']}:{issue['line']}")
        print(f"  {issue['message']}")
        if issue["evidence"]:
            print(f"  evidence: {issue['evidence']}")
        if issue["suggestion"]:
            print(f"  suggestion: {issue['suggestion']}")


def print_graph_report(report: dict[str, Any], *, as_json: bool) -> int:
    payload = {
        "root": report["root"],
        "task": report["task"],
        "dependency_graph": report["dependency_graph"],
        "conflict_surface": report["conflict_surface"],
        "vanilla_delta": report["vanilla_delta"],
        "patch_opportunities": report["patch_opportunities"],
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    print(f"root: {payload['root']}")
    print(f"task: {payload['task']}")
    print("[dependency_graph]")
    if not payload["dependency_graph"]:
        print("none")
    for path, graph in payload["dependency_graph"].items():
        print(path)
        for key in ("requires", "callbacks", "exports", "calls", "save_functions", "mcm_roots", "monkey_patches"):
            values = graph.get(key, [])
            print(f"  {key}: {', '.join(values) if values else 'none'}")
    print()
    print("[conflict_surface]")
    for key, values in payload["conflict_surface"].items():
        print(f"{key}: {', '.join(values)}")
    if not payload["conflict_surface"]:
        print("none")
    return 0


def parse_ltx_sections(text: str) -> OrderedDict[str, OrderedDict[str, str]]:
    sections: OrderedDict[str, OrderedDict[str, str]] = OrderedDict()
    current = ""
    sections[current] = OrderedDict()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith((";", "#")):
            continue
        section = SECTION_RE.match(line)
        if section:
            current = section.group(1).strip()
            sections.setdefault(current, OrderedDict())
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            sections.setdefault(current, OrderedDict())[key] = value
    if not sections[""]:
        sections.pop("", None)
    return sections


def suggest_ltx_patch(path: Path, vanilla_path: Path, gamedata_rel: str) -> dict[str, Any]:
    target_text, _ = safe_read_text(path)
    vanilla_text, _ = safe_read_text(vanilla_path)
    target = parse_ltx_sections(target_text)
    vanilla = parse_ltx_sections(vanilla_text)
    lines = [f"; Suggested DLTX patch for {gamedata_rel}", ""]
    changed_sections: list[str] = []

    for section, target_values in target.items():
        vanilla_values = vanilla.get(section)
        if vanilla_values is None:
            changed_sections.append(section)
            lines.append(f"@[{section}]")
            for key, value in target_values.items():
                lines.append(f"{key} = {value}")
            lines.append("")
            continue

        additions_or_changes: list[tuple[str, str]] = []
        removals: list[str] = []
        for key, value in target_values.items():
            if vanilla_values.get(key) != value:
                additions_or_changes.append((key, value))
        for key in vanilla_values:
            if key not in target_values:
                removals.append(key)
        if additions_or_changes or removals:
            changed_sections.append(section)
            lines.append(f"![{section}]")
            for key in removals:
                lines.append(f"!{key}")
            for key, value in additions_or_changes:
                lines.append(f"{key} = {value}")
            lines.append("")

    for section in vanilla:
        if section not in target:
            changed_sections.append(section)
            lines.append(f"!![{section}]")
            lines.append("")

    return {
        "path": str(path),
        "target": gamedata_rel,
        "patch_kind": "DLTX",
        "manual_required": False,
        "changed_sections": changed_sections,
        "patch_text": "\n".join(lines).rstrip() + "\n",
    }


def changed_line_ranges(vanilla_text: str, target_text: str) -> list[dict[str, int | str]]:
    vanilla_lines = vanilla_text.splitlines()
    target_lines = target_text.splitlines()
    matcher = difflib.SequenceMatcher(a=vanilla_lines, b=target_lines)
    ranges: list[dict[str, int | str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ranges.append(
            {
                "kind": tag,
                "vanilla_start": i1 + 1,
                "vanilla_end": i2,
                "target_start": j1 + 1,
                "target_end": j2,
            }
        )
    return ranges


def suggest_dxml_patch(path: Path, vanilla_path: Path, gamedata_rel: str) -> dict[str, Any]:
    target_text, _ = safe_read_text(path)
    vanilla_text, _ = safe_read_text(vanilla_path)
    ranges = changed_line_ranges(vanilla_text, target_text)
    target_xml = gamedata_rel.replace("/", "\\")
    digest = hashlib.sha1(target_text.encode("utf-8", errors="replace")).hexdigest()[:12]
    lines = [
        f"-- Suggested DXML scaffold for {gamedata_rel}",
        f"-- target sha1: {digest}",
        f"local TARGET_XML = [[{target_xml}]]",
        "",
        "function on_xml_read()",
        '    RegisterScriptCallback("on_xml_read", function(xml_file_name, xml_obj)',
        "        if xml_file_name ~= TARGET_XML then",
        "            return",
        "        end",
        "",
        "        -- Apply a narrow XML diff here.",
    ]
    for item in ranges[:12]:
        lines.append(
            "        -- changed target lines "
            f"{item['target_start']}-{item['target_end']} ({item['kind']})"
        )
    lines.extend(["    end)", "end", ""])
    return {
        "path": str(path),
        "target": gamedata_rel,
        "patch_kind": "DXML",
        "manual_required": True,
        "changed_ranges": ranges,
        "patch_text": "\n".join(lines),
    }


def suggest_patch(path: Path, *, as_json: bool) -> int:
    target = path.expanduser().resolve()
    if not target.exists() or not target.is_file():
        print(f"path not found: {target}", file=sys.stderr)
        return 1
    gamedata_rel = gamedata_relative(target)
    if not gamedata_rel:
        print("file is not under a gamedata tree", file=sys.stderr)
        return 1
    vanilla_path = VANILLA_GAMEDATA / gamedata_rel
    if not vanilla_path.exists():
        payload = {
            "path": str(target),
            "target": gamedata_rel,
            "patch_kind": "new-file",
            "manual_required": False,
            "patch_text": "",
            "message": "No vanilla file exists for this gamedata path; ship as a new overlay file.",
        }
    elif target.suffix.lower() == ".ltx":
        payload = suggest_ltx_patch(target, vanilla_path, gamedata_rel)
    elif target.suffix.lower() == ".xml":
        payload = suggest_dxml_patch(target, vanilla_path, gamedata_rel)
    else:
        print("only .ltx and .xml patch suggestions are supported", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"patch_kind: {payload['patch_kind']}")
        print(f"target: {payload['target']}")
        print(f"manual_required: {'yes' if payload.get('manual_required') else 'no'}")
        message = payload.get("message")
        if message:
            print(f"message: {message}")
        patch_text = payload.get("patch_text") or ""
        if patch_text:
            print("[patch_text]")
            print(patch_text.rstrip())
    return 0


def normalize_module_key(raw: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_]+", "_", raw.strip()).strip("_").lower()
    if not candidate:
        candidate = "mod_state"
    if candidate[0].isdigit():
        candidate = f"mod_{candidate}"
    return candidate


def save_template_payload(module: str) -> dict[str, str]:
    key = normalize_module_key(module)
    snippet = "\n".join(
        [
            "local STATE_VERSION = 1",
            f'local STATE_KEY = "{key}"',
            "",
            "local defaults = {",
            "    enabled = true,",
            "}",
            "",
            "local state = {}",
            "",
            "local function copy_defaults()",
            "    local result = {}",
            "    for key, value in pairs(defaults) do",
            "        result[key] = value",
            "    end",
            "    return result",
            "end",
            "",
            "local function migrate_state(version, saved)",
            "    local result = copy_defaults()",
            "    if type(saved) ~= \"table\" then",
            "        return result",
            "    end",
            "    if version < 1 then",
            "        return result",
            "    end",
            "    if type(saved.enabled) == \"boolean\" then",
            "        result.enabled = saved.enabled",
            "    end",
            "    return result",
            "end",
            "",
            "function save_state(m_data)",
            "    if type(m_data) ~= \"table\" then",
            "        return",
            "    end",
            "    m_data[STATE_KEY] = {",
            "        version = STATE_VERSION,",
            "        values = {",
            "            enabled = state.enabled,",
            "        },",
            "    }",
            "end",
            "",
            "function load_state(m_data)",
            "    local saved = type(m_data) == \"table\" and m_data[STATE_KEY] or nil",
            "    local version = type(saved) == \"table\" and tonumber(saved.version) or 0",
            "    local values = type(saved) == \"table\" and saved.values or nil",
            "    state = migrate_state(version or 0, values)",
            "    -- Rebuild transient engine object caches after this point.",
            "end",
            "",
            "function on_game_start()",
            "    state = copy_defaults()",
            "end",
            "",
        ]
    )
    return {"module": key, "snippet": snippet}


OPTIONAL_PATTERNS: dict[str, dict[str, str]] = {
    "ui_mcm": {
        "title": "Optional MCM read with defaults",
        "snippet": "\n".join(
            [
                "local defaults = { enable_feature = true }",
                "",
                "local function read_mcm_bool(path, fallback)",
                "    if not ui_mcm then",
                "        return fallback",
                "    end",
                "    local value = ui_mcm.get(path)",
                "    if value == nil then",
                "        return fallback",
                "    end",
                "    return value == true",
                "end",
            ]
        ),
    },
    "dynamic_news": {
        "title": "Optional dynamic news guard",
        "snippet": "\n".join(
            [
                "local function send_news(kind, text_id)",
                "    if dynamic_news and type(dynamic_news.send_tip) == \"function\" then",
                "        dynamic_news.send_tip(kind, text_id)",
                "        return true",
                "    end",
                "    return false",
                "end",
            ]
        ),
    },
    "callback": {
        "title": "Optional callback registration",
        "snippet": "\n".join(
            [
                "local function safe_register_callback(name, fn)",
                "    if type(RegisterScriptCallback) ~= \"function\" then",
                "        return false",
                "    end",
                "    RegisterScriptCallback(name, fn)",
                "    return true",
                "end",
            ]
        ),
    },
    "modded_exes": {
        "title": "Optional Modded Exes feature gate",
        "snippet": "\n".join(
            [
                "local function has_callback(name)",
                "    return type(RegisterScriptCallback) == \"function\" and type(name) == \"string\"",
                "end",
                "",
                "local function register_if_available(name, fn)",
                "    if not has_callback(name) then",
                "        return false",
                "    end",
                "    RegisterScriptCallback(name, fn)",
                "    return true",
                "end",
            ]
        ),
    },
}


def print_save_template(module: str, *, as_json: bool) -> int:
    payload = save_template_payload(module)
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload["snippet"].rstrip())
    return 0


def print_optional_pattern(pattern: str, *, as_json: bool) -> int:
    if pattern == "list":
        payload: dict[str, Any] = {"patterns": sorted(OPTIONAL_PATTERNS)}
        if as_json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            for key in payload["patterns"]:
                print(key)
        return 0
    payload = OPTIONAL_PATTERNS.get(pattern)
    if not payload:
        print(f"unknown optional pattern: {pattern}", file=sys.stderr)
        print("known patterns:", ", ".join(sorted(OPTIONAL_PATTERNS)), file=sys.stderr)
        return 1
    result = {"pattern": pattern, **payload}
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"pattern: {pattern}")
        print(f"title: {payload['title']}")
        print("[snippet]")
        print(payload["snippet"].rstrip())
    return 0


def explain_rule(rule_id: str) -> int:
    rules = load_manifest("quality_rules").get("rules", {})
    meta = rules.get(rule_id)
    if not meta:
        print(f"unknown rule: {rule_id}")
        print("known rules:")
        for key in sorted(rules):
            print(f"  - {key}")
        return 1
    print(f"rule_id: {rule_id}")
    print(f"severity: {meta.get('severity')}")
    print(f"category: {meta.get('category')}")
    print(f"message: {meta.get('message')}")
    print(f"suggestion: {meta.get('suggestion')}")
    print("detection: conservative regex/path-aware scan; verify context before large rewrites.")
    return 0


def should_fail(report: dict[str, Any], threshold: str | None) -> bool:
    if not threshold:
        return False
    threshold_rank = SEVERITY_RANK[threshold]
    for issue in report["issues"]:
        if SEVERITY_RANK.get(issue["severity"], 0) >= threshold_rank:
            return True
    return False


def main() -> int:
    args = parse_args()
    if args.subcommand == "explain-rule":
        return explain_rule(args.rule_id)
    if args.subcommand == "suggest-patch":
        return suggest_patch(Path(args.path), as_json=args.json)
    if args.subcommand == "save-template":
        return print_save_template(args.module, as_json=args.json)
    if args.subcommand == "optional-pattern":
        return print_optional_pattern(args.pattern, as_json=args.json)

    root = Path(args.path)
    if not root.exists():
        print(f"path not found: {root}", file=sys.stderr)
        return 1
    scanner = Scanner(root, args.task)
    report = scanner.scan()
    if args.subcommand == "graph":
        return print_graph_report(report, as_json=args.json)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 1 if should_fail(report, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
