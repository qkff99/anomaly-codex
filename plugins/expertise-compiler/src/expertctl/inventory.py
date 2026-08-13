from __future__ import annotations

import ast
import configparser
import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .vault import atomic_write_text, read_json, read_jsonl


_MAX_FILE_BYTES = 5 * 1024 * 1024
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "bin",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "obj",
    "target",
    "vendor",
}
_BINARY_SUFFIXES = {
    ".7z", ".a", ".avi", ".bmp", ".class", ".dll", ".dylib", ".exe", ".gif", ".gz",
    ".ico", ".jar", ".jpeg", ".jpg", ".lib", ".mov", ".mp3", ".mp4", ".o", ".obj",
    ".pdf", ".png", ".pyc", ".so", ".tar", ".wasm", ".webm", ".webp", ".woff",
    ".woff2", ".xz", ".zip",
}
_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".py": "python",
    ".pyi": "python",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".properties": "properties",
    ".xml": "xml",
}


def _is_derived_map_directory(path: Path) -> bool:
    """Keep generated corpus maps out of a live workspace-reference scan."""
    return path.name.casefold().endswith("-out") and (path / "graph.json").is_file()
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_CPP_DEF_RE = re.compile(
    r"^\s*(?:(?:template\s*<[^;{}]+>\s*)|(?:[\w:<>,~*&]+\s+))+"
    r"(?P<name>[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*)\s*\([^;{}]*\)"
    r"\s*(?:const\s*)?(?:noexcept\s*)?(?:->\s*[^\{]+)?\{"
)
_CPP_TYPE_RE = re.compile(r"^\s*(?:class|struct|enum(?:\s+class)?|namespace)\s+(?P<name>[A-Za-z_]\w*)")
_JS_TYPE_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?P<kind>class|interface|type|enum)\s+(?P<name>[A-Za-z_$][\w$]*)")
_JS_FUNCTION_RE = re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)")
_JS_ARROW_RE = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>")
_CALL_RE = re.compile(r"(?:\b[A-Za-z_$][\w$]*\.)*\b(?P<name>[A-Za-z_$][\w$]*)\s*\(")


def _decode_text(data: bytes) -> str | None:
    if b"\0" in data:
        return None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if text:
        controls = sum(ord(char) < 32 and char not in "\n\r\t\f\b" for char in text)
        if controls / len(text) > 0.01:
            return None
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _safe_walk(root: Path) -> Iterable[tuple[Path, PurePosixPath, str, bytes]]:
    base = root.resolve()
    if not base.is_dir():
        return
    for current, directories, names in os.walk(base, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directories):
            path = current_path / name
            resolved = path.resolve()
            if not _inside(resolved, base):
                raise ValueError(f"directory link escapes source snapshot: {path.relative_to(base)}")
            if name.casefold() in _SKIP_DIRS or _is_derived_map_directory(path) or path.is_symlink() or resolved != path.absolute():
                continue
            kept.append(name)
        directories[:] = kept
        for name in sorted(names):
            path = current_path / name
            resolved = path.resolve()
            if not _inside(resolved, base):
                raise ValueError(f"file link escapes source snapshot: {path.relative_to(base)}")
            if path.is_symlink() or resolved != path.absolute() or path.suffix.casefold() in _BINARY_SUFFIXES:
                continue
            try:
                if path.stat().st_size > _MAX_FILE_BYTES:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            text = _decode_text(data)
            if text is not None:
                yield path, PurePosixPath(path.relative_to(base).as_posix()), text, data


def _safe_source_files(root: Path) -> Iterable[tuple[Path, PurePosixPath, str, bytes]]:
    if root.is_file() and not root.is_symlink():
        try:
            if root.stat().st_size <= _MAX_FILE_BYTES and root.suffix.casefold() not in _BINARY_SUFFIXES:
                data = root.read_bytes()
                text = _decode_text(data)
                if text is not None:
                    yield root, PurePosixPath(root.name), text, data
        except OSError:
            return
    elif root.is_dir() and not root.is_symlink():
        yield from _safe_walk(root)


def _latest_sources(vault: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in read_jsonl(vault / "sources/registry.jsonl"):
        key = (str(entry.get("kind", "source")), str(entry.get("uri", entry.get("id", ""))))
        latest[key] = entry
    return sorted(latest.values(), key=lambda item: str(item.get("id", "")))


def _source_files(vault: Path, entry: dict[str, Any]) -> Iterable[tuple[Path, PurePosixPath, str, bytes, str]]:
    from .sources import workspace_reference_root

    reference_root = workspace_reference_root(vault, entry)
    if reference_root is not None:
        for path, relative, text, data in _safe_source_files(reference_root):
            yield path, relative, text, data, "workspace-reference"
        return
    normalized = vault / str(entry.get("normalized_path", ""))
    raw = vault / str(entry.get("raw_path", ""))
    sources_root = (vault / "sources").resolve()
    normalized_ok = normalized.exists() and _inside(normalized.resolve(), sources_root)
    raw_ok = raw.exists() and _inside(raw.resolve(), sources_root)
    seen: set[str] = set()
    if normalized_ok:
        for path, relative, text, data in _safe_source_files(normalized):
            seen.add(relative.as_posix())
            yield path, relative, text, data, "normalized"
    if raw_ok:
        for path, relative, text, data in _safe_source_files(raw):
            normalized_peer = relative.with_suffix(relative.suffix + ".md").as_posix() if relative.suffix.lower() in {".html", ".htm"} else relative.as_posix()
            if relative.as_posix() not in seen and normalized_peer not in seen:
                yield path, relative, text, data, "raw"


def _fallback_sources(vault: Path) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for kind in ("normalized", "raw"):
        root = vault / "sources" / kind
        if not root.is_dir():
            continue
        if any(child.is_file() and not child.is_symlink() for child in root.iterdir()):
            entry = entries.setdefault("unregistered", {"id": "unregistered", "kind": "source", "uri": "unregistered"})
            entry[f"{kind}_path"] = root.relative_to(vault).as_posix()
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if child.is_dir() and not child.is_symlink():
                entry = entries.setdefault(child.name, {"id": child.name, "kind": "source", "uri": child.name})
                entry[f"{kind}_path"] = child.relative_to(vault).as_posix()
    return list(entries.values())


def _stable_id(prefix: str, *values: object) -> str:
    payload = "\0".join(str(value) for value in values).encode("utf-8")
    return f"{prefix}.{hashlib.sha256(payload).hexdigest()[:20]}"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _symbol(
    symbols: list[dict[str, Any]],
    source_id: str,
    file_id: str,
    path: str,
    logical_path: str,
    kind: str,
    name: str,
    qualified_name: str,
    line: int,
    end_line: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    occurrence = 1 + sum(
        item.get("source_id") == source_id
        and item.get("logical_path") == logical_path
        and item.get("kind") == kind
        and item.get("qualified_name") == qualified_name
        for item in symbols
    )
    identity: tuple[object, ...] = (source_id, logical_path, kind, qualified_name)
    if occurrence > 1:
        identity += (occurrence,)
    item = {
        "id": _stable_id("sym", *identity),
        "source_id": source_id,
        "file_id": file_id,
        "path": path,
        "logical_path": logical_path,
        "kind": kind,
        "name": name,
        "qualified_name": qualified_name,
        "line": line,
        "end_line": end_line or line,
    }
    if occurrence > 1:
        item["occurrence"] = occurrence
    item.update(extra)
    return item


def _edge(source: str, target: str, kind: str, *, confidence: float = 1.0, **extra: Any) -> dict[str, Any]:
    item = {"source": source, "target": target, "kind": kind, "confidence": confidence}
    item.update(extra)
    return item


class _PythonInventory(ast.NodeVisitor):
    def __init__(self, source_id: str, file_id: str, path: str, logical_path: str) -> None:
        self.source_id = source_id
        self.file_id = file_id
        self.path = path
        self.logical_path = logical_path
        self.symbols: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.parents: list[dict[str, Any]] = []

    @property
    def owner(self) -> str:
        return self.parents[-1]["id"] if self.parents else self.file_id

    def _definition(self, node: ast.AST, kind: str, name: str) -> dict[str, Any]:
        qualified = ".".join([*(parent["name"] for parent in self.parents), name])
        item = _symbol(
            self.symbols,
            self.source_id,
            self.file_id,
            self.path,
            self.logical_path,
            kind,
            name,
            qualified,
            int(getattr(node, "lineno", 1)),
            int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
        )
        self.symbols.append(item)
        self.edges.append(_edge(self.owner, item["id"], "contains"))
        self.parents.append(item)
        for child in getattr(node, "body", []):
            self.visit(child)
        self.parents.pop()
        return item

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        item = self._definition(node, "class", node.name)
        for base in node.bases:
            try:
                name = ast.unparse(base)
            except Exception:
                continue
            self.edges.append(_edge(item["id"], f"symbol-name:{name}", "inherits", confidence=0.8, target_name=name))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._definition(node, "method" if self.parents and self.parents[-1]["kind"] == "class" else "function", node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.edges.append(_edge(self.owner, f"module:{alias.name}", "imports", target_name=alias.name))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        self.edges.append(_edge(self.owner, f"module:{module}", "imports", target_name=module))

    def visit_Call(self, node: ast.Call) -> None:
        try:
            name = ast.unparse(node.func)
        except Exception:
            name = ""
        if name:
            self.edges.append(_edge(self.owner, f"symbol-name:{name}", "calls", confidence=0.6, target_name=name))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if not self.parents or self.parents[-1]["kind"] == "class":
            for target in node.targets:
                if isinstance(target, ast.Name):
                    kind = "constant" if target.id.isupper() else "variable"
                    qualified = ".".join([*(parent["name"] for parent in self.parents), target.id])
                    item = _symbol(self.symbols, self.source_id, self.file_id, self.path, self.logical_path, kind, target.id, qualified, node.lineno, getattr(node, "end_lineno", node.lineno))
                    self.symbols.append(item)
                    self.edges.append(_edge(self.owner, item["id"], "contains"))
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and (not self.parents or self.parents[-1]["kind"] == "class"):
            name = node.target.id
            qualified = ".".join([*(parent["name"] for parent in self.parents), name])
            item = _symbol(self.symbols, self.source_id, self.file_id, self.path, self.logical_path, "constant" if name.isupper() else "variable", name, qualified, node.lineno, getattr(node, "end_lineno", node.lineno))
            self.symbols.append(item)
            self.edges.append(_edge(self.owner, item["id"], "contains"))
        if node.value:
            self.visit(node.value)


def _markdown_symbols(source_id: str, file_id: str, path: str, logical_path: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    hierarchy: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        name = re.sub(r"[*_`\[\]]", "", match.group(2)).strip()
        while hierarchy and hierarchy[-1]["level"] >= level:
            hierarchy.pop()
        qualified = " / ".join([*(item["name"] for item in hierarchy), name])
        item = _symbol(symbols, source_id, file_id, path, logical_path, "heading", name, qualified, number, level=level)
        symbols.append(item)
        edges.append(_edge(hierarchy[-1]["id"] if hierarchy else file_id, item["id"], "contains"))
        hierarchy.append(item)
    return symbols, edges


def _regex_code_symbols(source_id: str, file_id: str, path: str, logical_path: str, text: str, language: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    control = {"if", "for", "while", "switch", "catch", "return", "sizeof"}
    for number, line in enumerate(text.splitlines(), 1):
        defined_name = ""
        if language in {"c", "cpp"}:
            include = re.match(r'^\s*#\s*include\s*[<"]([^>"]+)', line)
            if include:
                edges.append(_edge(file_id, f"include:{include.group(1)}", "includes", target_name=include.group(1)))
            match = _CPP_TYPE_RE.match(line)
            if match:
                kind = line.lstrip().split(None, 1)[0]
                item = _symbol(symbols, source_id, file_id, path, logical_path, kind, match.group("name"), match.group("name"), number)
                symbols.append(item)
                edges.append(_edge(file_id, item["id"], "contains"))
            match = _CPP_DEF_RE.match(line)
            if match and match.group("name").split("::")[-1] not in control:
                name = match.group("name")
                defined_name = name.split("::")[-1]
                item = _symbol(symbols, source_id, file_id, path, logical_path, "function", name.split("::")[-1], name, number)
                symbols.append(item)
                edges.append(_edge(file_id, item["id"], "contains"))
        else:
            import_match = re.search(r"\bfrom\s*['\"]([^'\"]+)|\brequire\s*\(\s*['\"]([^'\"]+)", line)
            if import_match:
                target = import_match.group(1) or import_match.group(2)
                edges.append(_edge(file_id, f"module:{target}", "imports", target_name=target))
            match = _JS_TYPE_RE.match(line)
            kind = match.group("kind") if match else ""
            if not match:
                match = _JS_FUNCTION_RE.match(line)
                kind = "function"
            if not match:
                match = _JS_ARROW_RE.match(line)
                kind = "function"
            if match:
                name = match.group("name")
                defined_name = name
                item = _symbol(symbols, source_id, file_id, path, logical_path, kind, name, name, number)
                symbols.append(item)
                edges.append(_edge(file_id, item["id"], "contains"))
        for call in _CALL_RE.finditer(line):
            name = call.group("name")
            if name not in control | {defined_name, "function"}:
                edges.append(_edge(file_id, f"symbol-name:{name}", "calls", confidence=0.45, target_name=name, line=number))
    return symbols, edges


def _line_for_key(lines: list[str], key: str) -> int:
    pattern = re.compile(rf"(?:^|[\"']){re.escape(key)}[\"']?\s*[:=]")
    return next((number for number, line in enumerate(lines, 1) if pattern.search(line)), 1)


def _mapping_symbols(source_id: str, file_id: str, path: str, logical_path: str, data: Any, lines: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def walk(value: Any, parents: list[str], owner: str) -> None:
        if isinstance(value, dict):
            for key in sorted(value, key=str):
                name = str(key)
                if not name:
                    walk(value[key], parents, owner)
                    continue
                qualified = ".".join([*parents, name])
                kind = "config_section" if isinstance(value[key], (dict, list)) else "config_key"
                item = _symbol(symbols, source_id, file_id, path, logical_path, kind, name, qualified, _line_for_key(lines, name))
                symbols.append(item)
                edges.append(_edge(owner, item["id"], "contains"))
                walk(value[key], [*parents, name], item["id"])
        elif isinstance(value, list):
            for item in value:
                walk(item, parents, owner)
        elif isinstance(value, str) and re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", value):
            edges.append(_edge(owner, f"symbol-name:{value.rsplit('.', 1)[-1]}", "references", confidence=0.7, target_name=value))

    walk(data, [], file_id)
    return symbols, edges


def _config_symbols(source_id: str, file_id: str, path: str, logical_path: str, text: str, language: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    lines = text.splitlines()
    try:
        if language == "json":
            symbols, edges = _mapping_symbols(source_id, file_id, path, logical_path, json.loads(text), lines)
        elif language == "toml":
            symbols, edges = _mapping_symbols(source_id, file_id, path, logical_path, tomllib.loads(text), lines)
        elif language == "ini":
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            parser.read_string(text)
            data = {section: dict(parser.items(section, raw=True)) for section in parser.sections()}
            if parser.defaults():
                data["DEFAULT"] = dict(parser.defaults())
            symbols, edges = _mapping_symbols(source_id, file_id, path, logical_path, data, lines)
        elif language == "xml":
            root = ET.fromstring(text)
            data: dict[str, Any] = {root.tag: {"@" + key: value for key, value in root.attrib.items()}}
            for element in root.iter():
                data.setdefault(element.tag, {}).update({"@" + key: value for key, value in element.attrib.items()})
            symbols, edges = _mapping_symbols(source_id, file_id, path, logical_path, data, lines)
        elif language in {"yaml", "properties"}:
            symbols, edges = [], []
            parents: list[tuple[int, dict[str, Any]]] = []
            pattern = re.compile(r"^(?P<indent>\s*)(?P<key>[^#;\s][^:=]*?)\s*[:=](?P<value>.*)$")
            for number, line in enumerate(lines, 1):
                match = pattern.match(line)
                if not match:
                    continue
                indent = len(match.group("indent").replace("\t", "    "))
                name = match.group("key").strip().strip("\"'")
                while parents and parents[-1][0] >= indent:
                    parents.pop()
                qualified = ".".join([*(item[1]["name"] for item in parents), name])
                kind = "config_section" if not match.group("value").strip() else "config_key"
                item = _symbol(symbols, source_id, file_id, path, logical_path, kind, name, qualified, number)
                symbols.append(item)
                edges.append(_edge(parents[-1][1]["id"] if parents else file_id, item["id"], "contains"))
                value = match.group("value").strip().strip("\"'")
                if value and re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", value):
                    edges.append(_edge(item["id"], f"symbol-name:{value.rsplit('.', 1)[-1]}", "references", confidence=0.7, target_name=value))
                if kind == "config_section":
                    parents.append((indent, item))
        else:
            return [], [], None
        return symbols, edges, None
    except (ValueError, SyntaxError, configparser.Error, ET.ParseError) as exc:
        return [], [], str(exc)


def _aliases(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for symbol in symbols:
        name = symbol["name"]
        spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
        spaced = re.sub(r"[_\-.]+", " ", spaced).strip().casefold()
        values = {name.casefold(), spaced, symbol["qualified_name"].casefold()}
        for alias in sorted(value for value in values if value):
            key = (alias, symbol["id"])
            if key not in seen:
                seen.add(key)
                output.append({"alias": alias, "target": symbol["id"], "kind": "symbol"})
    return sorted(output, key=lambda item: (item["alias"], item["target"]))


def _resolve_edges(edges: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names: dict[str, list[str]] = {}
    for symbol in symbols:
        for name in {symbol["name"], symbol["qualified_name"]}:
            names.setdefault(name.casefold(), []).append(symbol["id"])
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in edges:
        target = edge["target"]
        if target.startswith("symbol-name:"):
            name = target.removeprefix("symbol-name:")
            matches = sorted(set(names.get(name.casefold(), [])))
            if len(matches) == 1:
                edge = {**edge, "target": matches[0], "resolved": True}
            else:
                edge = {**edge, "target": f"unresolved:{name}", "resolved": False}
        key = (edge["source"], edge["target"], edge["kind"])
        edge["id"] = _stable_id("edge", *key)
        output[key] = edge
    return sorted(output.values(), key=lambda item: (item["kind"], item["source"], item["target"]))


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for record in records)
    atomic_write_text(path, text + ("\n" if text else ""))


def _repo_map(files: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> str:
    by_file: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        by_file.setdefault(symbol["file_id"], []).append(symbol)
    lines = ["# Repository Map", ""]
    current = None
    for file in files:
        if file["source_id"] != current:
            current = file["source_id"]
            lines.extend([f"## {current}", ""])
        lines.append(f"- `{file['logical_path']}` — {file['language']}, {file['lines']} lines")
        for symbol in sorted(by_file.get(file["id"], []), key=lambda item: (item["line"], item["qualified_name"])):
            lines.append(f"  - {symbol['kind']} `{symbol['qualified_name']}` (line {symbol['line']})")
    return "\n".join(lines).rstrip() + "\n"


def _source_pages(vault: Path, entries: list[dict[str, Any]], files: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> None:
    by_source: dict[str, list[dict[str, Any]]] = {}
    by_file: dict[str, list[dict[str, Any]]] = {}
    for file in files:
        by_source.setdefault(file["source_id"], []).append(file)
    for symbol in symbols:
        by_file.setdefault(symbol["file_id"], []).append(symbol)
    for entry in entries:
        source_id = str(entry.get("id", "source"))
        lines = ["<!-- generated by expertctl scan -->", f"# Source: {source_id}", "", f"- Kind: {entry.get('kind', 'source')}", f"- URI: `{entry.get('uri', '')}`", "", "## Structure", ""]
        for file in by_source.get(source_id, []):
            lines.append(f"- `{file['logical_path']}`")
            for symbol in sorted(by_file.get(file["id"], []), key=lambda item: (item["line"], item["qualified_name"])):
                lines.append(f"  - {symbol['kind']} `{symbol['qualified_name']}` (line {symbol['line']})")
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", source_id).strip(".-_") or "source"
        atomic_write_text(vault / "wiki/sources" / f"{filename}.md", "\n".join(lines).rstrip() + "\n")


def scan(vault: Path) -> dict[str, Any]:
    """Build a deterministic structural inventory from current source snapshots."""
    root = Path(vault).expanduser().resolve()
    if not (root / "vault.json").is_file():
        raise FileNotFoundError(f"not an expertise vault: {root}")
    entries = _latest_sources(root) or _fallback_sources(root)
    config = read_json(root / "vault.json", {})
    lightweight = isinstance(config, dict) and config.get("structural_inventory") == "files"
    publish_source_pages = not (isinstance(config, dict) and config.get("source_storage") == "workspace-reference")
    files: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for entry in entries:
        source_id = str(entry.get("id", "source"))
        for path, relative, text, data, origin in _source_files(root, entry):
            logical_path = relative.as_posix()
            try:
                vault_path = path.relative_to(root).as_posix()
            except ValueError:
                raw_path = PurePosixPath(str(entry.get("raw_path", "")).replace("\\", "/"))
                vault_path = (raw_path / relative).as_posix()
            language = _LANGUAGES.get(path.suffix.casefold(), path.suffix.lstrip(".").casefold() or "text")
            file_id = _stable_id("file", source_id, logical_path)
            record: dict[str, Any] = {
                "id": file_id,
                "source_id": source_id,
                "path": vault_path,
                "logical_path": logical_path,
                "origin": origin,
                "language": language,
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "lines": len(text.splitlines()),
            }
            file_symbols: list[dict[str, Any]] = []
            file_edges: list[dict[str, Any]] = []
            parse_error: str | None = None
            if not lightweight:
                if language == "markdown":
                    file_symbols, file_edges = _markdown_symbols(source_id, file_id, vault_path, logical_path, text)
                elif language == "python":
                    try:
                        visitor = _PythonInventory(source_id, file_id, vault_path, logical_path)
                        visitor.visit(ast.parse(text, filename=logical_path))
                        file_symbols, file_edges = visitor.symbols, visitor.edges
                    except SyntaxError as exc:
                        parse_error = f"{exc.msg} (line {exc.lineno})"
                elif language in {"c", "cpp", "javascript", "typescript"}:
                    file_symbols, file_edges = _regex_code_symbols(source_id, file_id, vault_path, logical_path, text, language)
                elif language in {"json", "toml", "yaml", "ini", "properties", "xml"}:
                    file_symbols, file_edges, parse_error = _config_symbols(source_id, file_id, vault_path, logical_path, text, language)
            if parse_error:
                record["parse_error"] = parse_error
            record["symbol_count"] = len(file_symbols)
            files.append(record)
            symbols.extend(file_symbols)
            edges.extend(file_edges)

    files.sort(key=lambda item: (item["source_id"], item["logical_path"], item["path"]))
    symbols.sort(key=lambda item: (item["source_id"], item["path"], item["line"], item["kind"], item["qualified_name"]))
    edges = _resolve_edges(edges, symbols)
    aliases = _aliases(symbols)
    source_versions = [
        {
            "id": str(entry.get("id") or ""),
            "snapshot": entry.get("snapshot"),
            "sha256": entry.get("sha256"),
            "normalized_sha256": entry.get("normalized_sha256"),
            "commit": entry.get("commit"),
        }
        for entry in sorted(entries, key=lambda item: str(item.get("id") or ""))
    ]
    staging_parent = root / "state" / "staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="scan-", dir=staging_parent))
    staged_code = staging / "code"
    current_code = root / "code"
    if current_code.is_dir():
        shutil.copytree(current_code, staged_code)
    else:
        staged_code.mkdir(parents=True)
    staged_sources = staging / "wiki" / "sources"
    staged_sources.mkdir(parents=True)
    _write_jsonl(staged_code / "files.jsonl", files)
    _write_jsonl(staged_code / "symbols.jsonl", symbols)
    _write_jsonl(staged_code / "edges.jsonl", edges)
    _write_jsonl(staged_code / "aliases.jsonl", aliases)
    atomic_write_text(staged_code / "repo-map.md", _repo_map(files, symbols))
    if publish_source_pages:
        _source_pages(staging, entries, files, symbols)
    artifact_paths = [
        "code/files.jsonl",
        "code/symbols.jsonl",
        "code/edges.jsonl",
        "code/aliases.jsonl",
        "code/repo-map.md",
        *(
            path.relative_to(staging).as_posix()
            for path in sorted(staged_sources.rglob("*.md"))
            if path.is_file()
        ),
    ]
    artifacts = {
        relative: hashlib.sha256(staging.joinpath(*PurePosixPath(relative).parts).read_bytes()).hexdigest()
        for relative in artifact_paths
    }
    atomic_write_text(
        staged_code / "inventory.json",
        json.dumps(
            {"schema_version": 1, "sources": source_versions, "artifacts": artifacts},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    current_sources = root / "wiki" / "sources"
    backup_code = staging / "previous-code"
    backup_sources = staging / "previous-sources"
    had_code, had_sources = current_code.exists(), current_sources.exists()
    try:
        if had_sources:
            os.replace(current_sources, backup_sources)
        os.replace(staged_sources, current_sources)
        if had_code:
            os.replace(current_code, backup_code)
        os.replace(staged_code, current_code)
    except BaseException:
        if current_code.exists() and backup_code.exists():
            os.replace(current_code, staging / "failed-code")
        if backup_code.exists():
            os.replace(backup_code, current_code)
        elif not had_code and current_code.exists():
            shutil.rmtree(current_code)
        if current_sources.exists() and backup_sources.exists():
            os.replace(current_sources, staging / "failed-sources")
        if backup_sources.exists():
            os.replace(backup_sources, current_sources)
        elif not had_sources and current_sources.exists():
            shutil.rmtree(current_sources)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return {
        "sources": len(entries),
        "files": len(files),
        "symbols": len(symbols),
        "edges": len(edges),
        "aliases": len(aliases),
        "repo_map": "code/repo-map.md",
    }
