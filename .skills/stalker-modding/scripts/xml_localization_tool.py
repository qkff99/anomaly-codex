#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from _skill_common import normalize_newlines, read_text_auto, rewrite_xml_declaration_encoding


DEFAULT_STATE_DIR = Path(tempfile.gettempdir()) / "stalker-codex-xml-codec-state"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect, decode, and round-trip STALKER XML localization files between legacy encodings and UTF-8."
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    inspect = subparsers.add_parser("inspect", help="Inspect XML files and report detected encoding and localization hints.")
    inspect.add_argument("paths", nargs="+", help="XML files to inspect.")

    read = subparsers.add_parser("read", help="Read an XML file as UTF-8 text without modifying the source file.")
    read.add_argument("path", help="XML file to read.")
    read.add_argument("--output", help="Optional UTF-8 output file.")

    prepare = subparsers.add_parser(
        "prepare-edit",
        help="Convert an XML file in place to UTF-8 for editing and store restore metadata.",
    )
    prepare.add_argument("paths", nargs="+", help="XML files to convert to UTF-8 in place.")
    prepare.add_argument("--state-dir", help="Directory for temporary restore metadata.")

    finish = subparsers.add_parser(
        "finish-edit",
        help="Restore a previously prepared XML file back to its original encoding.",
    )
    finish.add_argument("paths", nargs="+", help="XML files to restore from UTF-8.")
    finish.add_argument("--state-dir", help="Directory containing temporary restore metadata.")
    finish.add_argument("--keep-state", action="store_true", help="Keep the restore metadata after a successful finish.")

    return parser.parse_args()


def resolve_state_dir(raw: str | None) -> Path:
    return Path(raw).expanduser().resolve() if raw else DEFAULT_STATE_DIR


def ensure_xml_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"path not found: {resolved}")
    if not resolved.is_file():
        raise FileNotFoundError(f"not a file: {resolved}")
    if resolved.suffix.lower() != ".xml":
        raise ValueError(f"expected an .xml file: {resolved}")
    return resolved


def state_file_for(path: Path, state_dir: Path) -> Path:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
    return state_dir / f"{digest}.json"


def normalized_utf8_view(text: str, meta: dict[str, Any]) -> str:
    if meta.get("declared_encoding"):
        return rewrite_xml_declaration_encoding(text, "utf-8")
    return text


def write_text_exact(path: Path, text: str, encoding: str) -> None:
    with path.open("w", encoding=encoding, newline="") as handle:
        handle.write(text)


def print_inspection(path: Path, meta: dict[str, Any]) -> None:
    print(f"file: {path}")
    print(f"codec: {meta['codec']}")
    print(f"declared_encoding: {meta['declared_encoding'] or 'none'}")
    print(f"root_tag: {meta.get('root_tag') or 'unknown'}")
    print(f"is_localization_xml: {'yes' if meta.get('is_localization_xml') else 'no'}")
    print(f"newline: {meta.get('newline', 'unknown')}")
    print(f"source: {meta.get('detection_source', 'unknown')}")
    print()


def handle_inspect(paths: list[str]) -> int:
    for raw_path in paths:
        path = ensure_xml_path(Path(raw_path))
        _, meta = read_text_auto(path)
        print_inspection(path, meta)
    return 0


def handle_read(path_arg: str, output_arg: str | None) -> int:
    path = ensure_xml_path(Path(path_arg))
    text, meta = read_text_auto(path)
    utf8_text = normalized_utf8_view(text, meta)
    if output_arg:
        output = Path(output_arg).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        write_text_exact(output, utf8_text, "utf-8")
        print(f"wrote_utf8: {output}")
        return 0

    sys.stdout.write(utf8_text)
    if not utf8_text.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def prepare_one(path: Path, state_dir: Path) -> None:
    text, meta = read_text_auto(path)
    utf8_text = normalized_utf8_view(text, meta)

    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_file_for(path, state_dir)
    state = {
        "source_path": str(path),
        "codec": meta["codec"],
        "declared_encoding": meta["declared_encoding"],
        "had_xml_declaration": meta["had_xml_declaration"],
        "newline": meta["newline"],
        "had_utf8_bom": meta["had_utf8_bom"],
        "root_tag": meta.get("root_tag"),
        "is_localization_xml": meta.get("is_localization_xml", False),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    write_text_exact(path, utf8_text, "utf-8")

    print(f"prepared: {path}")
    print(f"from_encoding: {meta['codec']}")
    print(f"state_file: {state_path}")
    print()


def handle_prepare(paths: list[str], state_dir_arg: str | None) -> int:
    state_dir = resolve_state_dir(state_dir_arg)
    for raw_path in paths:
        prepare_one(ensure_xml_path(Path(raw_path)), state_dir)
    return 0


def finish_one(path: Path, state_dir: Path, keep_state: bool) -> None:
    state_path = state_file_for(path, state_dir)
    if not state_path.exists():
        raise FileNotFoundError(f"restore metadata not found for {path}: {state_path}")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    text, _ = read_text_auto(path, errors="strict")

    if state.get("had_xml_declaration") and state.get("declared_encoding"):
        text = rewrite_xml_declaration_encoding(text, state["declared_encoding"])

    text = normalize_newlines(text, state.get("newline", "lf"))
    codec = state.get("codec") or "cp1251"

    try:
        payload = text.encode(codec)
    except UnicodeEncodeError as exc:
        raise UnicodeEncodeError(
            exc.encoding,
            exc.object,
            exc.start,
            exc.end,
            f"{exc.reason}. The current text cannot be represented in {codec}.",
        ) from exc

    path.write_bytes(payload)
    if not keep_state:
        state_path.unlink(missing_ok=True)

    print(f"restored: {path}")
    print(f"to_encoding: {codec}")
    if keep_state:
        print(f"state_file: {state_path}")
    print()


def handle_finish(paths: list[str], state_dir_arg: str | None, keep_state: bool) -> int:
    state_dir = resolve_state_dir(state_dir_arg)
    for raw_path in paths:
        finish_one(ensure_xml_path(Path(raw_path)), state_dir, keep_state)
    return 0


def main() -> int:
    args = parse_args()
    if args.subcommand == "inspect":
        return handle_inspect(args.paths)
    if args.subcommand == "read":
        return handle_read(args.path, args.output)
    if args.subcommand == "prepare-edit":
        return handle_prepare(args.paths, args.state_dir)
    if args.subcommand == "finish-edit":
        return handle_finish(args.paths, args.state_dir, args.keep_state)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
