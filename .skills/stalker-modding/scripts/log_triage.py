#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from _skill_common import REPO_ROOT, workspace_external_paths


TAIL_CHUNK_SIZE = 64 * 1024
TAIL_MAX_BYTES = 4 * 1024 * 1024
TAIL_FALLBACK_LINES = 120
ENGINE_SOURCE_ROOT = REPO_ROOT / "ai_workspace" / "src"
VANILLA_GAMEDATA_ROOT = REPO_ROOT / "ai_workspace" / "vanilla scripts" / "gamedata"
START_MARKERS = (
    "SCRIPT RUNTIME ERROR",
    "SCRIPT SYNTAX ERROR",
    "SCRIPT ERROR (memory allocation)",
    "SCRIPT ERROR (while running file)",
    "SCRIPT ERROR (while running the error handler function)",
    "! [SCRIPT ERROR]:",
    "FATAL ERROR",
)
LUA_STACK_RE = re.compile(r"""(?:.*?\[LUA\]\s+)?(\d+)\s*:\s*\[([^\]]+)\]\s+(.+?)(?:\((\d+)\))?\s*:\s*(.*)$""")
TRACEBACK_RE = re.compile(r"""^\s*(\d+)-\s+(.*?):(?:(\d+):)?(.*)$""")
WINDOWS_TRACEBACK_RE = re.compile(r"""^\s*(\d+)-\s+((?:[A-Za-z]:)?[^:]+):(?:(\d+):)?(.*)$""")
FATAL_FIELD_RE = re.compile(r"""^(?:\[error\]\s*)?(Expression|Function|File|Line|Description)\s*:\s*(.+)$""")
ENGINE_STACK_FRAME_RE = re.compile(r"""^(?P<source>.+?)\s+\((?P<line>\d+)\):\s+(?P<function>.+)$""")
SCRIPT_ERROR_RE = re.compile(
    r"""(?P<source>.+?\.(?:script|lua|xml|ltx|script\.txt)):(?P<line>\d+):\s*(?P<message>.+)$""",
    re.IGNORECASE,
)
SRC_SEGMENT_RE = re.compile(r"""(?:^|[\\/])src[\\/](?P<tail>.+)$""", re.IGNORECASE)
GAMEDATA_SEGMENT_RE = re.compile(r"""(?:^|[\\/])gamedata[\\/](?P<tail>.+)$""", re.IGNORECASE)
ENGINE_RELATIVE_STARTS = ("layers", "xrai", "xrcore", "xreditor", "xrgame", "xrnetserver", "xrparticles", "xrphysics", "xrserverentities", "xrxmlparser")
GAMEDATA_RELATIVE_STARTS = ("scripts", "configs", "textures", "sounds", "meshes", "shaders", "levels", "spawns", "ui")
DEBUG_WRAPPER_FUNCTIONS = {
    "invalid_parameter_handler",
    "UnhandledFilter",
    "xrDebug::backend",
    "xrDebug::gather_info",
    "handler_base",
    "pure_call_handler",
    "abort_handler",
    "floating_point_handler",
    "illegal_instruction_handler",
    "termination_handler",
}
DEBUG_WRAPPER_PATH_SUFFIXES = (
    "xrcore/xrdebugnew.cpp",
    "xrcore/xrdebug.h",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract compact error summaries from Anomaly/XRay logs. "
            "For repeated log-driven work, prefer remembering MO2 mods or unpacked gamedata "
            "before a logs_dir, and only remember paths with explicit user approval."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    summarize = subparsers.add_parser("summarize", help="Print a compact summary of the latest high-signal error block.")
    summarize.add_argument("target", nargs="?", help="Log file or directory containing logs.")
    summarize.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    latest = subparsers.add_parser(
        "latest",
        help=(
            "Summarize the latest log from remembered logs_dir entries. "
            "Use this mainly when the user explicitly wants latest-log automation."
        ),
    )
    latest.add_argument("--logs-id", help="Remembered logs_dir id to use when multiple are configured.")
    latest.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    extract = subparsers.add_parser("extract", help="Print raw extracted error block(s) from a log.")
    extract.add_argument("target", nargs="?", help="Log file or directory containing logs.")
    extract.add_argument(
        "--kind",
        default="all",
        choices=("lua_runtime", "lua_syntax", "engine_fatal", "all"),
        help="Which block kind to extract.",
    )
    return parser


def remembered_log_dirs() -> list[dict[str, str]]:
    entries = []
    for entry in workspace_external_paths():
        if entry.get("kind") == "logs_dir":
            entries.append(
                {
                    "id": str(entry["id"]),
                    "path": str(entry["path"]),
                    "label": str(entry["label"]),
                }
            )
    return entries


def latest_log_in_directory(directory: Path) -> Path:
    logs = [path for path in directory.rglob("*.log") if path.is_file()]
    if not logs:
        raise FileNotFoundError(f"no .log files found in {directory}")
    return max(logs, key=lambda path: (path.stat().st_mtime, path.name))


def resolve_latest_target(logs_id: str | None) -> Path:
    remembered = remembered_log_dirs()
    if not remembered:
        raise FileNotFoundError("no remembered logs_dir paths are configured")
    if logs_id:
        matches = [entry for entry in remembered if entry["id"] == logs_id]
        if not matches:
            known = ", ".join(sorted(entry["id"] for entry in remembered))
            raise FileNotFoundError(f"unknown logs_id: {logs_id}. known ids: {known}")
        return latest_log_in_directory(Path(matches[0]["path"]))
    if len(remembered) > 1:
        known = ", ".join(f"{entry['id']} ({entry['label']})" for entry in remembered)
        raise FileNotFoundError(f"multiple remembered logs_dir entries exist; use --logs-id. known ids: {known}")
    return latest_log_in_directory(Path(remembered[0]["path"]))


def resolve_target(raw_target: str | None) -> Path:
    if raw_target:
        candidate = Path(raw_target).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"target not found: {candidate}")
        if candidate.is_dir():
            return latest_log_in_directory(candidate)
        return candidate
    return resolve_latest_target(logs_id=None)


def read_tail_text(path: Path) -> str:
    size = path.stat().st_size
    if size == 0:
        return ""

    buffer = b""
    with path.open("rb") as handle:
        offset = size
        while offset > 0 and len(buffer) < TAIL_MAX_BYTES:
            read_size = min(TAIL_CHUNK_SIZE, offset)
            offset -= read_size
            handle.seek(offset)
            chunk = handle.read(read_size)
            buffer = chunk + buffer
            text = buffer.decode("utf-8", errors="ignore")
            if any(marker in text for marker in START_MARKERS):
                return text
    return buffer.decode("utf-8", errors="ignore")


def classify_start(line: str) -> str | None:
    if "FATAL ERROR" in line:
        return "engine_fatal"
    if "SCRIPT SYNTAX ERROR" in line:
        return "lua_syntax"
    if (
        "SCRIPT RUNTIME ERROR" in line
        or "SCRIPT ERROR (memory allocation)" in line
        or "SCRIPT ERROR (while running file)" in line
        or "SCRIPT ERROR (while running the error handler function)" in line
        or "! [SCRIPT ERROR]:" in line
    ):
        return "lua_runtime"
    return None


def extract_blocks(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    blocks: list[dict[str, Any]] = []
    current_kind: str | None = None
    current_start = 0

    for index, line in enumerate(lines):
        start_kind = classify_start(line)
        if start_kind is None:
            continue
        stripped = line.strip()
        if (
            current_kind in {"lua_runtime", "lua_syntax"}
            and start_kind == "lua_runtime"
            and stripped.startswith("! [SCRIPT ERROR]:")
            and index - current_start <= 4
        ):
            continue
        if current_kind is not None:
            blocks.append(
                {
                    "kind": current_kind,
                    "start_index": current_start,
                    "lines": lines[current_start:index],
                }
            )
        current_kind = start_kind
        current_start = index

    if current_kind is not None:
        blocks.append(
            {
                "kind": current_kind,
                "start_index": current_start,
                "lines": lines[current_start:],
            }
        )
        return blocks

    fallback = lines[-TAIL_FALLBACK_LINES:] if lines else []
    if fallback and any("[LUA]" in line or "stack traceback:" in line for line in fallback):
        return [{"kind": "lua_runtime", "start_index": max(0, len(lines) - len(fallback)), "lines": fallback}]
    return []


def parse_lua_stack(lines: list[str]) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for line in lines:
        stripped = line.strip()
        match = LUA_STACK_RE.search(stripped)
        if match:
            _, frame_type, source, line_no, function_name = match.groups()
            frames.append(
                {
                    "type": frame_type,
                    "source": source.strip(),
                    "line": int(line_no) if line_no else None,
                    "function": function_name.strip() or None,
                }
            )
            continue
        match = WINDOWS_TRACEBACK_RE.match(stripped)
        if match:
            _, source, line_no, tail = match.groups()
            frames.append(
                {
                    "type": "traceback",
                    "source": source.strip(),
                    "line": int(line_no) if line_no else None,
                    "function": tail.strip() or None,
                }
            )
            continue
        match = TRACEBACK_RE.match(stripped)
        if match:
            _, source, line_no, tail = match.groups()
            frames.append(
                {
                    "type": "traceback",
                    "source": source.strip(),
                    "line": int(line_no) if line_no else None,
                    "function": tail.strip() or None,
                }
            )
    return frames


def is_lua_error_continuation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if "SCRIPT RUNTIME ERROR" in stripped or "SCRIPT SYNTAX ERROR" in stripped:
        return True
    if stripped.startswith(("! [LUA]", "* [LUA]", "~ [LUA]", "! [SCRIPT ERROR]:", "! [ERROR] ---")):
        return True
    if stripped == "stack traceback:":
        return True
    if TRACEBACK_RE.match(stripped):
        return True
    return False


def trim_lua_block_lines(lines: list[str]) -> list[str]:
    trimmed: list[str] = []
    body_started = False
    for line in lines:
        stripped = line.strip()
        if not trimmed:
            trimmed.append(line)
            continue
        if is_lua_error_continuation(line):
            trimmed.append(line)
            if stripped:
                body_started = True
            continue
        if body_started:
            break
        trimmed.append(line)
    while trimmed and not trimmed[-1].strip():
        trimmed.pop()
    return trimmed


def normalize_lua_path(raw_source: str | None) -> str | None:
    if not isinstance(raw_source, str):
        return None
    normalized = raw_source.strip().replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized).strip("/")
    return normalized or None


def parse_lua_primary_error(lines: list[str]) -> dict[str, Any] | None:
    ranked: list[tuple[int, dict[str, Any]]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        cleaned = stripped
        for prefix in ("! [SCRIPT ERROR]:", "! [LUA]"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        match = SCRIPT_ERROR_RE.search(cleaned)
        if not match:
            continue
        source = match.group("source").strip()
        line_no = int(match.group("line"))
        message = match.group("message").strip()
        score = 0
        if stripped.startswith("! [SCRIPT ERROR]:"):
            score += 3
        if stripped.startswith("! [LUA]"):
            score += 2
        if source.lower().endswith((".script", ".lua")):
            score += 2
        ranked.append(
            (
                score,
                {
                    "source_file": source,
                    "line": line_no,
                    "headline": message,
                },
            )
        )
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def parse_engine_fatal_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        match = FATAL_FIELD_RE.match(line.strip())
        if match:
            key, value = match.groups()
            fields[key.lower()] = value.strip()
    return fields


def parse_engine_stack(lines: list[str]) -> list[dict[str, Any]]:
    sequences: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    collecting = False
    had_real_frame = False
    non_match_count = 0

    def flush_current() -> None:
        nonlocal current, collecting, had_real_frame, non_match_count
        if current:
            sequences.append(current)
        current = []
        collecting = False
        had_real_frame = False
        non_match_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped.lower() == "stack trace:":
            flush_current()
            collecting = True
            continue
        if not collecting:
            continue
        if not stripped:
            if had_real_frame:
                non_match_count += 1
                if non_match_count >= 2:
                    flush_current()
            continue
        if FATAL_FIELD_RE.match(stripped):
            continue
        if classify_start(stripped) is not None:
            flush_current()
            continue

        match = ENGINE_STACK_FRAME_RE.match(stripped)
        if match:
            current.append(
                {
                    "type": "engine",
                    "source": match.group("source").strip(),
                    "line": int(match.group("line")),
                    "function": match.group("function").strip() or None,
                    "raw": stripped,
                }
            )
            had_real_frame = True
            non_match_count = 0
            continue

        if had_real_frame and ("!" in stripped or stripped.lower().endswith(".dll") or stripped.lower().endswith(".exe")):
            current.append(
                {
                    "type": "engine-symbol",
                    "source": stripped,
                    "line": None,
                    "function": None,
                    "raw": stripped,
                }
            )
            non_match_count = 0
            continue

        if had_real_frame:
            non_match_count += 1
            if non_match_count >= 2:
                flush_current()

    flush_current()
    if not sequences:
        return []
    return max(sequences, key=score_engine_stack_sequence)


def score_engine_stack_sequence(frames: list[dict[str, Any]]) -> tuple[int, int]:
    real_frames = sum(1 for frame in frames if frame.get("type") == "engine")
    resolved_frames = sum(1 for frame in frames if frame.get("type") == "engine" and resolve_engine_source_path(frame.get("source")))
    return resolved_frames, real_frames


@lru_cache(maxsize=1)
def cached_engine_source_paths() -> tuple[Path, ...]:
    if not ENGINE_SOURCE_ROOT.exists():
        return ()
    suffixes = {".cpp", ".c", ".h", ".hpp", ".inl"}
    return tuple(sorted(path.resolve() for path in ENGINE_SOURCE_ROOT.rglob("*") if path.is_file() and path.suffix.lower() in suffixes))


@lru_cache(maxsize=1)
def cached_workspace_gamedata_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    repo_gamedata = REPO_ROOT / "gamedata"
    if repo_gamedata.exists():
        roots.append(repo_gamedata.resolve())

    projects_dir = REPO_ROOT / "projects"
    if projects_dir.exists():
        for path in projects_dir.glob("*/gamedata"):
            if path.is_dir():
                roots.append(path.resolve())

    if VANILLA_GAMEDATA_ROOT.exists():
        roots.append(VANILLA_GAMEDATA_ROOT.resolve())

    for entry in workspace_external_paths():
        raw_path = entry.get("path")
        kind = entry.get("kind")
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path).expanduser().resolve()
        if kind == "gamedata_root" and path.is_dir():
            roots.append(path)
        elif kind == "external_mod_root":
            if path.is_dir() and path.name.lower() == "gamedata":
                roots.append(path)
            elif (path / "gamedata").is_dir():
                roots.append((path / "gamedata").resolve())
        elif kind == "mo2_mods_dir" and path.is_dir():
            for candidate in path.glob("*/gamedata"):
                if candidate.is_dir():
                    roots.append(candidate.resolve())

    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return tuple(deduped)


def normalize_engine_path(raw_source: str | None) -> str | None:
    if not isinstance(raw_source, str):
        return None
    normalized = raw_source.strip().replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized).strip("/")
    return normalized or None


def engine_relative_candidates(raw_source: str | None) -> list[str]:
    normalized = normalize_engine_path(raw_source)
    if not normalized:
        return []

    candidates: list[str] = []
    src_match = SRC_SEGMENT_RE.search(normalized)
    if src_match:
        candidates.append(src_match.group("tail").replace("\\", "/"))

    lowered = normalized.lower()
    parts = normalized.split("/")
    for index, part in enumerate(parts):
        if part.lower() in ENGINE_RELATIVE_STARTS:
            candidates.append("/".join(parts[index:]))
            break

    basename = parts[-1]
    if basename:
        candidates.append(basename)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        clean = candidate.strip("/").replace("\\", "/")
        lowered_candidate = clean.lower()
        if not clean or lowered_candidate in seen:
            continue
        seen.add(lowered_candidate)
        deduped.append(clean)
    return deduped


def lua_relative_candidates(raw_source: str | None) -> list[str]:
    normalized = normalize_lua_path(raw_source)
    if not normalized:
        return []

    candidates: list[str] = []
    gamedata_match = GAMEDATA_SEGMENT_RE.search(normalized)
    if gamedata_match:
        candidates.append(gamedata_match.group("tail").replace("\\", "/"))

    parts = normalized.split("/")
    for index, part in enumerate(parts):
        if part.lower() in GAMEDATA_RELATIVE_STARTS:
            candidates.append("/".join(parts[index:]))
            break

    basename = parts[-1]
    if basename:
        candidates.append(basename)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        clean = candidate.strip("/").replace("\\", "/")
        lowered_candidate = clean.lower()
        if not clean or lowered_candidate in seen:
            continue
        seen.add(lowered_candidate)
        deduped.append(clean)
    return deduped


def resolve_engine_source_path(raw_source: str | None) -> Path | None:
    for candidate in engine_relative_candidates(raw_source):
        exact = (ENGINE_SOURCE_ROOT / candidate).resolve()
        if exact.exists():
            return exact

    all_paths = cached_engine_source_paths()
    relative_candidates = engine_relative_candidates(raw_source)
    for candidate in relative_candidates:
        lowered_candidate = candidate.lower()
        suffix_matches = [
            path for path in all_paths if str(path).replace("\\", "/").lower().endswith("/" + lowered_candidate)
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]

    if relative_candidates:
        basename = Path(relative_candidates[-1]).name.lower()
        basename_matches = [path for path in all_paths if path.name.lower() == basename]
        if len(basename_matches) == 1:
            return basename_matches[0]
    return None


def resolve_lua_source_path(raw_source: str | None) -> Path | None:
    relative_candidates = lua_relative_candidates(raw_source)
    gamedata_roots = cached_workspace_gamedata_roots()

    for candidate in relative_candidates:
        normalized_candidate = candidate.replace("\\", "/")
        for root in gamedata_roots:
            exact = (root / normalized_candidate).resolve()
            if exact.exists():
                return exact

    if relative_candidates:
        basename = Path(relative_candidates[-1]).name.lower()
        if "." not in basename:
            return None
        basename_matches: list[Path] = []
        for root in gamedata_roots:
            basename_matches.extend(path for path in root.rglob("*") if path.is_file() and path.name.lower() == basename)
        unique = sorted({path.resolve() for path in basename_matches})
        if len(unique) == 1:
            return unique[0]
    return None


def is_debug_wrapper_point(local_path: Path | None, function_name: str | None) -> bool:
    if function_name and function_name.strip() in DEBUG_WRAPPER_FUNCTIONS:
        return True
    if local_path is None:
        return False
    normalized = str(local_path).replace("\\", "/").lower()
    return normalized.endswith(DEBUG_WRAPPER_PATH_SUFFIXES)


def build_inspect_points(
    kind: str,
    source_file: str | None,
    line_no: int | None,
    function_name: str | None,
    stack_frames: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    if kind in {"lua_runtime", "lua_syntax"} and source_file:
        local_path = resolve_lua_source_path(source_file)
        points.append(
            {
                "origin": "lua_error",
                "raw_source": source_file,
                "local_path": str(local_path) if local_path else None,
                "line": line_no,
                "function": function_name,
                "exists": local_path is not None,
                "is_debug_wrapper": False,
            }
        )

    if kind == "engine_fatal" and source_file:
        local_path = resolve_engine_source_path(source_file)
        points.append(
            {
                "origin": "fatal_file",
                "raw_source": source_file,
                "local_path": str(local_path) if local_path else None,
                "line": line_no,
                "function": function_name,
                "exists": local_path is not None,
                "is_debug_wrapper": is_debug_wrapper_point(local_path, function_name),
            }
        )

    for frame in stack_frames:
        if frame.get("type") in {"Lua", "main", "traceback", "C  ", "C"}:
            raw_source = frame.get("source")
            local_path = resolve_lua_source_path(raw_source if isinstance(raw_source, str) else None)
            points.append(
                {
                    "origin": "lua_stack",
                    "raw_source": raw_source,
                    "local_path": str(local_path) if local_path else None,
                    "line": frame.get("line"),
                    "function": frame.get("function"),
                    "exists": local_path is not None,
                    "is_debug_wrapper": False,
                }
            )
            continue
        if frame.get("type") != "engine":
            continue
        raw_source = frame.get("source")
        local_path = resolve_engine_source_path(raw_source if isinstance(raw_source, str) else None)
        points.append(
            {
                "origin": "engine_stack",
                "raw_source": raw_source,
                "local_path": str(local_path) if local_path else None,
                "line": frame.get("line"),
                "function": frame.get("function"),
                "exists": local_path is not None,
                "is_debug_wrapper": is_debug_wrapper_point(local_path, frame.get("function")),
            }
        )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str | None, int | None, str | None]] = set()
    for point in points:
        key = (point.get("local_path"), point.get("line"), point.get("function"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)

    return sorted(deduped, key=inspect_point_score, reverse=True)[:5]


def inspect_point_score(point: dict[str, Any]) -> tuple[int, int, int, int]:
    exists = 1 if point.get("exists") else 0
    non_wrapper = 0 if point.get("is_debug_wrapper") else 1
    is_engine_stack = 1 if point.get("origin") == "engine_stack" else 0
    has_line = 1 if point.get("line") is not None else 0
    return exists, non_wrapper, is_engine_stack, has_line


def choose_headline(kind: str, lines: list[str], fields: dict[str, str], stack_frames: list[dict[str, Any]]) -> str:
    if kind == "engine_fatal":
        if fields.get("description"):
            return fields["description"]
        if fields.get("expression"):
            return fields["expression"]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if classify_start(stripped) is not None:
            continue
        if stripped == "stack traceback:" or stripped == "stack trace:":
            continue
        if FATAL_FIELD_RE.match(stripped):
            continue
        return stripped

    if stack_frames:
        frame = stack_frames[0]
        source = frame.get("source") or "<unknown>"
        if frame.get("line"):
            return f"{source}:{frame['line']}"
        return str(source)
    return lines[0].strip() if lines else "<no details>"


def parse_block(block: dict[str, Any], log_path: Path) -> dict[str, Any]:
    lines = list(block["lines"])
    kind = str(block["kind"])
    if kind in {"lua_runtime", "lua_syntax"}:
        lines = trim_lua_block_lines(lines)
    stack_frames = parse_lua_stack(lines)
    fields = parse_engine_fatal_fields(lines) if kind == "engine_fatal" else {}
    if kind == "engine_fatal":
        stack_frames.extend(parse_engine_stack(lines))

    source_file = fields.get("file")
    line_no: int | None = int(fields["line"]) if fields.get("line", "").isdigit() else None
    expression = fields.get("expression")
    function_name = fields.get("function")
    primary_lua_error = parse_lua_primary_error(lines) if kind in {"lua_runtime", "lua_syntax"} else None

    if primary_lua_error:
        source_file = primary_lua_error["source_file"]
        line_no = primary_lua_error["line"]
        primary_headline = primary_lua_error["headline"]
    else:
        primary_headline = None

    if not source_file and stack_frames:
        source_file = stack_frames[0].get("source")
        line_no = stack_frames[0].get("line") or line_no

    headline = primary_headline or choose_headline(kind, lines, fields, stack_frames)
    inspect_points = build_inspect_points(kind, source_file, line_no, function_name, stack_frames)

    return {
        "kind": kind,
        "headline": headline,
        "source_file": source_file,
        "line": line_no,
        "function": function_name,
        "expression": expression,
        "stack_frames": stack_frames[:5],
        "inspect_points": inspect_points,
        "raw_block": "\n".join(lines).strip(),
        "log_path": str(log_path),
    }


def block_score(summary: dict[str, Any], block_index: int, total_blocks: int) -> tuple[int, int, int, int]:
    inspect_points = summary.get("inspect_points", [])
    resolved_points = sum(1 for point in inspect_points if point.get("exists"))
    non_wrapper_points = sum(1 for point in inspect_points if point.get("exists") and not point.get("is_debug_wrapper"))
    stack_size = len(summary.get("stack_frames", []))
    recency = block_index - total_blocks
    return non_wrapper_points, resolved_points, stack_size, recency


def choose_latest_block(text: str, log_path: Path, kind: str | None = None) -> dict[str, Any] | None:
    blocks = extract_blocks(text)
    if kind and kind != "all":
        blocks = [block for block in blocks if block["kind"] == kind]
    if not blocks:
        return None
    if all(block["kind"] == "engine_fatal" for block in blocks):
        parsed = [parse_block(block, log_path) for block in blocks]
        scored = [
            (block_score(summary, index, len(parsed)), summary)
            for index, summary in enumerate(parsed)
        ]
        return max(scored, key=lambda item: item[0])[1]
    return parse_block(blocks[-1], log_path)


def suggested_search_targets(summary: dict[str, Any]) -> list[str]:
    def normalize_function_hint(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.startswith("in function"):
            normalized = normalized[len("in function") :].strip()
        normalized = normalized.strip("`'\"")
        return normalized or None

    suggestions: list[str] = []
    if summary.get("source_file"):
        suggestions.append(str(summary["source_file"]))
    for frame in summary.get("stack_frames", []):
        if isinstance(frame, dict):
            source = frame.get("source")
            function_name = frame.get("function")
            if source:
                suggestions.append(str(source))
            normalized_function = normalize_function_hint(function_name)
            if normalized_function:
                suggestions.append(normalized_function)
    if summary.get("expression"):
        suggestions.append(str(summary["expression"]))
    for point in summary.get("inspect_points", []):
        local_path = point.get("local_path")
        line_no = point.get("line")
        if local_path and line_no is not None:
            suggestions.append(f"{local_path}:{line_no}")
        elif local_path:
            suggestions.append(str(local_path))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in suggestions:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped[:5]


def print_summary(summary: dict[str, Any], *, as_json: bool) -> int:
    if as_json:
        payload = {
            "kind": summary["kind"],
            "headline": summary["headline"],
            "source_file": summary["source_file"],
            "line": summary["line"],
            "function": summary["function"],
            "expression": summary["expression"],
            "stack_frames": summary["stack_frames"],
            "inspect_points": summary["inspect_points"],
            "raw_block": summary["raw_block"],
            "log_path": summary["log_path"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    suggestions = suggested_search_targets(summary)
    print(f"log_path: {summary['log_path']}")
    print(f"kind: {summary['kind']}")
    print(f"headline: {summary['headline']}")
    print(f"source_file: {summary.get('source_file') or 'unknown'}")
    print(f"line: {summary.get('line') if summary.get('line') is not None else 'unknown'}")
    print(f"function: {summary.get('function') or 'unknown'}")
    print(f"expression: {summary.get('expression') or 'none'}")
    print("[stack_frames]")
    if summary["stack_frames"]:
        for frame in summary["stack_frames"]:
            source = frame.get("source") or "<unknown>"
            line_no = frame.get("line")
            function_name = frame.get("function") or ""
            if line_no is not None:
                print(f"{source}:{line_no} {function_name}".rstrip())
            else:
                print(f"{source} {function_name}".rstrip())
    else:
        print("none")
    print()
    print("[inspect_points]")
    inspect_points = summary.get("inspect_points", [])
    if inspect_points:
        for point in inspect_points:
            local_path = point.get("local_path") or "<unresolved>"
            line_no = point.get("line")
            function_name = point.get("function") or ""
            origin = point.get("origin") or "unknown"
            wrapper_flag = " wrapper" if point.get("is_debug_wrapper") else ""
            if line_no is not None:
                print(f"{origin}:{local_path}:{line_no} {function_name}{wrapper_flag}".rstrip())
            else:
                print(f"{origin}:{local_path} {function_name}{wrapper_flag}".rstrip())
    else:
        print("none")
    print()
    print("[suggested_next_search]")
    for suggestion in suggestions:
        print(suggestion)
    if not suggestions:
        print("none")
    return 0


def command_summarize(raw_target: str | None, *, as_json: bool) -> int:
    target = resolve_target(raw_target)
    summary = choose_latest_block(read_tail_text(target), target)
    if summary is None:
        print(f"no high-signal error block found in {target}")
        return 1
    return print_summary(summary, as_json=as_json)


def command_latest(logs_id: str | None, *, as_json: bool) -> int:
    target = resolve_latest_target(logs_id)
    summary = choose_latest_block(read_tail_text(target), target)
    if summary is None:
        print(f"no high-signal error block found in {target}")
        return 1
    return print_summary(summary, as_json=as_json)


def command_extract(raw_target: str | None, kind: str) -> int:
    target = resolve_target(raw_target)
    text = read_tail_text(target)
    blocks = extract_blocks(text)
    if kind != "all":
        blocks = [block for block in blocks if block["kind"] == kind]
    if not blocks:
        print(f"no matching error block found in {target}")
        return 1

    if kind == "all":
        for block in blocks:
            print(f"[{block['kind']}]")
            lines = trim_lua_block_lines(block["lines"]) if block["kind"] in {"lua_runtime", "lua_syntax"} else block["lines"]
            print("\n".join(lines).strip())
            print()
    else:
        lines = trim_lua_block_lines(blocks[-1]["lines"]) if blocks[-1]["kind"] in {"lua_runtime", "lua_syntax"} else blocks[-1]["lines"]
        print("\n".join(lines).strip())
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "summarize":
            return command_summarize(args.target, as_json=args.json)
        if args.command == "latest":
            return command_latest(args.logs_id, as_json=args.json)
        if args.command == "extract":
            return command_extract(args.target, args.kind)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
