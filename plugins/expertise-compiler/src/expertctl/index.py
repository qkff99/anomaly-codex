from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import unicodedata
from collections import Counter, deque
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .vault import _publication_integrity_match, read_json, read_jsonl


INDEX_VERSION = 2
FIELD_WEIGHTS = {"title": 4.0, "aliases": 4.0, "headings": 2.0, "body": 1.0, "symbol": 8.0, "path": 2.0}
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_SCALAR = re.compile(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$")


def tokenize(text: str) -> list[str]:
    """Tokenize Unicode text, including snake_case and Unicode camelCase."""
    value = unicodedata.normalize("NFKC", str(text))
    words: list[str] = []
    current: list[str] = []
    for index, char in enumerate(value):
        if not char.isalnum():
            if current:
                words.append("".join(current).casefold())
                current = []
            continue
        previous = current[-1] if current else ""
        following = value[index + 1] if index + 1 < len(value) else ""
        boundary = bool(
            current
            and (
                (char.isupper() and (previous.islower() or (previous.isupper() and following.islower())))
                or (char.isdigit() != previous.isdigit())
            )
        )
        if boundary:
            words.append("".join(current).casefold())
            current = []
        current.append(char)
    if current:
        words.append("".join(current).casefold())
    return [word for word in words if word]


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return None
    if value[:1] == value[-1:] == '"':
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if value[:1] == value[-1:] == "'":
        return value[1:-1].replace("''", "'")
    folded = value.casefold()
    if folded in {"true", "false"}:
        return folded == "true"
    if folded in {"null", "~"}:
        return None
    if re.fullmatch(r"[+-]?\d+", value):
        return int(value)
    if re.fullmatch(r"[+-]?(?:(?:\d+\.\d*|\.\d+)(?:e[+-]?\d+)?|\d+e[+-]?\d+)", value, re.IGNORECASE):
        return float(value)
    if value[:1] in "[{" and value[-1:] in "]}":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            if value.startswith("["):
                return [_parse_scalar(part) for part in value[1:-1].split(",") if part.strip()]
    return value


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Read the small YAML subset used by vault pages (no YAML dependency)."""
    lines = text.replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        return {}, text
    block = lines[1:end]
    data: dict[str, Any] = {}
    index = 0
    while index < len(block):
        match = _SCALAR.match(block[index])
        if not match:
            index += 1
            continue
        key, raw = match.groups()
        if raw:
            data[key] = _parse_scalar(raw)
            index += 1
            continue
        values: list[Any] = []
        index += 1
        while index < len(block) and not _SCALAR.match(block[index]):
            line = block[index]
            item = re.match(r"^\s+-\s*(.*)$", line)
            if item:
                value = item.group(1).strip()
                mapping = re.match(r"^([\w-]+):\s*(.*)$", value)
                if mapping:
                    item_data: dict[str, Any] = {}
                    field, field_value = mapping.groups()
                    item_data[field] = _parse_scalar(field_value)
                    cursor = index + 1
                    while cursor < len(block):
                        nested = re.match(r"^\s{4,}([\w-]+):\s*(.*?)\s*$", block[cursor])
                        if not nested:
                            break
                        item_data[nested.group(1)] = _parse_scalar(nested.group(2))
                        cursor += 1
                    values.append(item_data)
                    index = cursor
                    continue
                values.append(_parse_scalar(value))
            index += 1
        data[key] = values
    return data, "\n".join(lines[end + 1 :]).lstrip()


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [str(item) for item in value.values() if isinstance(item, (str, int, float))]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_strings(item))
        return result
    return [str(value)] if isinstance(value, (int, float)) else []


def _identifier(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()


def _wiki_documents(vault: Path) -> list[dict[str, Any]]:
    root = vault / "wiki"
    documents: list[dict[str, Any]] = []
    if not root.is_dir():
        return documents
    provenance: dict[str, list[dict[str, Any]]] = {}
    claim_provenance: dict[str, list[dict[str, Any]]] = {}
    stale_pages = {
        str(item.get("page") or "").replace("\\", "/").removeprefix("wiki/")
        for item in read_jsonl(vault / "state" / "errors.jsonl")
        if isinstance(item, dict) and item.get("kind") == "stale-source" and item.get("page")
    }
    for item in read_jsonl(vault / "state" / "provenance.jsonl"):
        if not isinstance(item, dict):
            continue
        owner = str(item.get("page") or item.get("page_id") or item.get("target") or "").replace("\\", "/").removeprefix("wiki/")
        span = item.get("source_span") or item.get("span")
        if owner and isinstance(span, dict):
            provenance.setdefault(owner, []).append(span)
            if item.get("kind") == "claim" and isinstance(item.get("paragraph"), int) and item.get("paragraph_sha256"):
                claim_provenance.setdefault(owner, []).append(
                    {
                        "paragraph": item["paragraph"],
                        "paragraph_sha256": item["paragraph_sha256"],
                        "source_span": span,
                    }
                )
    for path in sorted(root.rglob("*.md"), key=lambda item: item.as_posix().casefold()):
        if path.relative_to(root).parts[:1] == ("sources",):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        meta, body = _frontmatter(text)
        relative = path.relative_to(vault).as_posix()
        page_id = str(meta.get("id") or path.relative_to(root).with_suffix("").as_posix())
        headings = _HEADING.findall(body)
        title = str(meta.get("title") or (headings[0] if headings else path.stem.replace("-", " ").replace("_", " ")))
        aliases = _strings(meta.get("aliases"))
        stored_spans = provenance.get(path.relative_to(root).as_posix(), []) + provenance.get(page_id, [])
        declared_spans = [item for item in meta.get("sources", []) if isinstance(item, dict)]
        if str(meta.get("type") or "").casefold() == "verified-recipe":
            declared_spans.extend(
                item
                for item in meta.get("evidence", [])
                if isinstance(item, dict) and item.get("source") and item.get("path")
            )
        source_spans = _dedupe(stored_spans or declared_spans)
        documents.append(
            {
                "id": page_id,
                "kind": "page",
                "type": str(meta.get("type") or "page"),
                "title": title,
                "path": relative,
                "summary": str(meta.get("summary") or ""),
                "aliases": aliases,
                "headings": headings,
                "status": "stale" if path.relative_to(root).as_posix() in stale_pages else str(meta.get("status") or ""),
                "versions": _strings(meta.get("versions")) + _strings(meta.get("applies_to")),
                "authority": meta.get("authority"),
                "verification": meta.get("verification"),
                "source_spans": source_spans,
                "claims": _dedupe(claim_provenance.get(path.relative_to(root).as_posix(), []) + claim_provenance.get(page_id, [])),
                "related": _strings(meta.get("related")),
                "fields": {
                    "title": title,
                    "aliases": " ".join(aliases),
                    "headings": " ".join(headings),
                    "body": " ".join((str(meta.get("summary") or ""), body)),
                    "symbol": " ".join(_strings(meta.get("symbols"))),
                    "path": " ".join((relative, page_id)),
                },
                "identifiers": [page_id, path.stem, *_strings(meta.get("symbols"))],
            }
        )
    return documents


def _code_documents(vault: Path) -> list[dict[str, Any]]:
    root = vault / "code"
    documents: list[dict[str, Any]] = []
    if not root.is_dir():
        return documents
    source_authority: dict[str, Any] = {}
    for item in read_jsonl(vault / "sources" / "registry.jsonl"):
        if isinstance(item, dict) and item.get("id"):
            source_authority[str(item["id"])] = item.get("authority")
    for jsonl in sorted(root.glob("*.jsonl"), key=lambda item: item.name):
        category = jsonl.stem[:-1] if jsonl.stem.endswith("s") else jsonl.stem
        for number, record in enumerate(read_jsonl(jsonl), 1):
            if not isinstance(record, dict):
                continue
            is_symbol = jsonl.name == "symbols.jsonl"
            names = _strings(record.get("name")) + _strings(record.get("title")) + _strings(record.get("id"))
            symbol_names = (
                _strings(record.get("name"))
                + _strings(record.get("qualified_name"))
                + _strings(record.get("symbol"))
                + _strings(record.get("symbols"))
            )
            aliases = _strings(record.get("aliases")) + _strings(record.get("alias"))
            paths = _strings(record.get("path")) + _strings(record.get("file")) + _strings(record.get("module"))
            title = (names or symbol_names or paths or [f"{category}-{number}"])[0]
            doc_id = str(record.get("id") or f"code:{category}:{number}:{title}")
            body_values = [value for key, value in record.items() if key not in {"aliases", "path", "file"}]
            documents.append(
                {
                    "id": doc_id,
                    "kind": "symbol" if is_symbol else category,
                    "type": str(record.get("kind") or record.get("type") or category),
                    "symbol_kind": str(record.get("kind") or record.get("type") or "") if is_symbol else "",
                    "title": str(title),
                    "path": (paths or [jsonl.relative_to(vault).as_posix()])[0],
                    "aliases": aliases,
                    "authority": source_authority.get(str(record.get("source_id") or "")),
                    "record": record,
                    "fields": {
                        "title": " ".join(names),
                        "aliases": " ".join(aliases),
                        "headings": "",
                        "body": " ".join(_strings(body_values)),
                        "symbol": " ".join(symbol_names),
                        "path": " ".join(paths),
                    },
                    "identifiers": symbol_names + _strings(record.get("id")),
                }
            )
    return documents


def _index_path(vault: Path) -> Path:
    return vault / "state" / "lexical-index.json.gz"


def _assert_stable(vault: Path) -> None:
    root = Path(vault).expanduser().resolve()
    if (root / "state" / "publish-journal.json").is_file():
        raise RuntimeError("expertise vault has an interrupted publication; rerun expertctl apply-build to recover")
    if (root / "state" / "pending-update.json").is_file():
        raise RuntimeError("expertise vault has an interrupted source update; rerun expertctl add/update to recover")
    impact = read_json(root / "state" / "impact.json", {})
    if isinstance(impact, dict) and (
        impact.get("targeted_recompile_required")
        or impact.get("extraction_required")
        or impact.get("impacted_pages")
    ):
        raise RuntimeError("expertise vault has pending source impact; complete extraction and synthesis")
    if not _publication_integrity_match(root):
        raise ValueError("published Wiki/state differs from the accepted publication manifest")


def _publication_fingerprint(vault: Path) -> str:
    manifest = read_json(Path(vault) / "state" / "publication.json", {})
    payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_index(vault: Path) -> dict[str, Any]:
    root = Path(vault).expanduser().resolve()
    _assert_stable(root)
    if not _publication_integrity_match(root):
        raise ValueError("cannot index Wiki content that differs from the accepted publication manifest")
    config = read_json(root / "vault.json", {})
    include_code = not isinstance(config, dict) or config.get("runtime_index") != "wiki"
    documents = _wiki_documents(root) + (_code_documents(root) if include_code else [])
    field_totals = Counter[str]()
    document_frequency = Counter[str]()
    for document in documents:
        encoded: dict[str, dict[str, int]] = {}
        seen: set[str] = set()
        for field in FIELD_WEIGHTS:
            counts = Counter(tokenize(document["fields"].get(field, "")))
            encoded[field] = dict(sorted(counts.items()))
            field_totals[field] += sum(counts.values())
            seen.update(counts)
        document["terms"] = encoded
        document["lengths"] = {field: sum(values.values()) for field, values in encoded.items()}
        document["identifiers"] = sorted({_identifier(item) for item in document.get("identifiers", []) if str(item).strip()})
        document.pop("fields", None)
        document_frequency.update(seen)
    count = len(documents)
    data = {
        "version": INDEX_VERSION,
        "publication_sha256": _publication_fingerprint(root),
        "documents": documents,
        "df": dict(sorted(document_frequency.items())),
        "average_lengths": {field: (field_totals[field] / count if count else 0.0) for field in FIELD_WEIGHTS},
    }
    target = _index_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(gzip.compress(payload, compresslevel=6, mtime=0))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(target), "version": INDEX_VERSION, "documents": count, "terms": len(document_frequency)}


def _load_index(vault: Path) -> dict[str, Any]:
    _assert_stable(vault)
    path = _index_path(vault)
    if not path.is_file():
        build_index(vault)
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        if data.get("version") != INDEX_VERSION or data.get("publication_sha256") != _publication_fingerprint(vault):
            raise ValueError("outdated index")
        return data
    except (OSError, ValueError, json.JSONDecodeError, AttributeError):
        build_index(vault)
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)


def _public(document: dict[str, Any], score: float) -> dict[str, Any]:
    result = dict(document.get("record") or {})
    for key in ("id", "kind", "type", "symbol_kind", "title", "path", "summary", "aliases", "headings", "status", "versions", "authority", "verification", "source_spans", "claims", "related"):
        if key in document and document[key] not in (None, "", [], {}):
            result[key] = document[key]
    result["score"] = round(score, 6)
    return result


def search(
    vault: Path,
    query: str,
    limit: int = 10,
    kind: str | None = None,
    version: str | None = None,
    authority: str | None = None,
) -> list[dict[str, Any]]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    terms = tokenize(query)
    if not terms or limit == 0:
        return []
    data = _load_index(Path(vault).expanduser().resolve())
    documents = data.get("documents", [])
    total = len(documents)
    exact = _identifier(query)
    vocabulary = data.get("df", {})
    expanded_terms: list[tuple[str, float]] = []
    for term in terms:
        expanded_terms.append((term, 1.0))
        if term in vocabulary or len(term) < 4:
            continue
        matches = sorted(
            ((SequenceMatcher(None, term, candidate).ratio(), candidate) for candidate in vocabulary if abs(len(candidate) - len(term)) <= 3),
            reverse=True,
        )[:2]
        expanded_terms.extend((candidate, ratio * 0.7) for ratio, candidate in matches if ratio >= 0.82)
    scored: list[tuple[float, dict[str, Any]]] = []
    for document in documents:
        if kind and kind.casefold() not in {str(document.get("kind", "")).casefold(), str(document.get("type", "")).casefold()}:
            continue
        if version and _identifier(version) not in {_identifier(item) for item in document.get("versions", [])}:
            continue
        if authority and _identifier(authority) != _identifier(document.get("authority", "")):
            continue
        score = 8.0 if exact in document.get("identifiers", []) else 0.0
        for term, similarity in expanded_terms:
            frequency = data.get("df", {}).get(term, 0)
            inverse = math.log(1.0 + (total - frequency + 0.5) / (frequency + 0.5)) if total else 0.0
            for field, weight in FIELD_WEIGHTS.items():
                count = document.get("terms", {}).get(field, {}).get(term, 0)
                if not count:
                    continue
                length = document.get("lengths", {}).get(field, 0)
                average = data.get("average_lengths", {}).get(field, 0.0) or 1.0
                denominator = count + 1.2 * (0.25 + 0.75 * length / average)
                score += similarity * weight * inverse * count * 2.2 / denominator
        if score > 0:
            scored.append((score, document))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("title", "")).casefold(), str(item[1].get("path", "")), str(item[1].get("id", ""))))
    return [_public(document, score) for score, document in scored[:limit]]


def symbol(vault: Path, name: str) -> list[dict[str, Any]]:
    hits = search(vault, name, limit=100, kind="symbol")
    exact = _identifier(name)
    exact_hits = [item for item in hits if exact in {_identifier(item.get(key, "")) for key in ("name", "qualified_name", "title", "id")}]
    return exact_hits or hits[:20]


def references(vault: Path, name: str) -> list[dict[str, Any]]:
    """Return deterministic incoming structural references to a symbol/name."""
    root = Path(vault).expanduser().resolve()
    wanted = _node_keys(root, name)
    result = []
    for edge in _edges(root):
        nodes = _edge_nodes(edge)
        if nodes and _identifier(nodes[1]) in wanted and str(edge.get("kind") or edge.get("type") or "") in {"references", "calls", "inherits", "contains"}:
            result.append(edge)
    return sorted(result, key=lambda item: (str(item.get("kind", "")), str(item.get("source", "")), str(item.get("target", "")), str(item.get("id", ""))))


def callers(vault: Path, name: str) -> list[dict[str, Any]]:
    """Return approximate call edges whose resolved target matches a symbol/name."""
    root = Path(vault).expanduser().resolve()
    wanted = _node_keys(root, name)
    result = []
    for edge in _edges(root):
        nodes = _edge_nodes(edge)
        if nodes and _identifier(nodes[1]) in wanted and str(edge.get("kind") or edge.get("type") or "") == "calls":
            result.append(edge)
    return sorted(result, key=lambda item: (str(item.get("source", "")), str(item.get("target", "")), str(item.get("id", ""))))


def _edge_nodes(edge: dict[str, Any]) -> tuple[str, str] | None:
    source = next((edge.get(key) for key in ("source", "src", "from", "caller", "parent") if edge.get(key) not in (None, "")), None)
    target = next((edge.get(key) for key in ("target", "dst", "to", "callee", "child") if edge.get(key) not in (None, "")), None)
    return (str(source), str(target)) if source is not None and target is not None else None


def _edges(vault: Path) -> list[dict[str, Any]]:
    _assert_stable(vault)
    edges: list[dict[str, Any]] = []
    for relative in ("code/edges.jsonl", "state/edges.jsonl", "state/graph.jsonl"):
        for item in read_jsonl(vault / relative):
            if isinstance(item, dict) and _edge_nodes(item):
                edges.append(item)
    for page in _wiki_documents(vault):
        for target in page.get("related", []):
            edges.append({"source": page["id"], "target": target, "type": "related"})
    unique = {json.dumps(item, ensure_ascii=False, sort_keys=True, default=str): item for item in edges}
    return [unique[key] for key in sorted(unique)]


def _node_keys(vault: Path, node: str) -> set[str]:
    wanted = _identifier(node)
    keys = {wanted}
    for item in read_jsonl(vault / "code" / "symbols.jsonl"):
        if not isinstance(item, dict):
            continue
        values = {_identifier(item.get(key, "")) for key in ("id", "name", "qualified_name")}
        if wanted in values and item.get("id"):
            keys.add(_identifier(item["id"]))
    for item in read_jsonl(vault / "code" / "aliases.jsonl"):
        if isinstance(item, dict) and wanted == _identifier(item.get("alias", "")) and item.get("target"):
            keys.add(_identifier(item["target"]))
    return keys


def neighbors(vault: Path, node: str, direction: str = "both") -> list[dict[str, Any]]:
    if direction not in {"in", "out", "both"}:
        raise ValueError("direction must be 'in', 'out', or 'both'")
    root = Path(vault).expanduser().resolve()
    wanted = _node_keys(root, node)
    result: list[dict[str, Any]] = []
    for edge in _edges(root):
        nodes = _edge_nodes(edge)
        if not nodes:
            continue
        source, target = nodes
        if direction in {"out", "both"} and _identifier(source) in wanted:
            result.append({**edge, "node": source, "neighbor": target, "direction": "out"})
        if direction in {"in", "both"} and _identifier(target) in wanted:
            result.append({**edge, "node": target, "neighbor": source, "direction": "in"})
    result.sort(key=lambda item: (_identifier(item["neighbor"]), item["direction"], json.dumps(item, sort_keys=True, default=str)))
    return result


def find_path(vault: Path, start: str, end: str, max_depth: int = 6) -> list[str]:
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    if _identifier(start) == _identifier(end):
        return [start]
    root = Path(vault).expanduser().resolve()
    starts, goals = _node_keys(root, start), _node_keys(root, end)
    if starts & goals:
        return [start] if _identifier(start) == _identifier(end) else [start, end]
    adjacency: dict[str, set[str]] = {}
    names: dict[str, str] = {_identifier(start): start, _identifier(end): end}
    for edge in _edges(root):
        nodes = _edge_nodes(edge)
        if not nodes:
            continue
        source, target = nodes
        left, right = _identifier(source), _identifier(target)
        names.setdefault(left, source)
        names.setdefault(right, target)
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    queue: deque[tuple[str, list[str]]] = deque((item, [item]) for item in sorted(starts))
    visited = set(starts)
    while queue:
        current, path = queue.popleft()
        if len(path) - 1 >= max_depth:
            continue
        for following in sorted(adjacency.get(current, ()), key=lambda item: names.get(item, item).casefold()):
            if following in visited:
                continue
            next_path = [*path, following]
            if following in goals:
                result = [names.get(item, item) for item in next_path]
                result[0], result[-1] = start, end
                return result
            visited.add(following)
            queue.append((following, next_path))
    return []


def _dedupe(items: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def context(vault: Path, query: str, budget: int = 8000) -> dict[str, Any]:
    if budget <= 0:
        raise ValueError("budget must be positive")
    root = Path(vault).expanduser().resolve()
    hits = search(root, query, limit=16)
    pages = [item for item in hits if item.get("kind") == "page"][:6]
    symbols = [item for item in hits if item.get("kind") == "symbol"][:8]
    route = [str(item.get("id") or item.get("path")) for item in pages[:5]]
    source_spans = _dedupe(span for page in pages for span in page.get("source_spans", []) if isinstance(span, dict))
    config = read_json(root / "vault.json", {})
    include_graph = not isinstance(config, dict) or config.get("runtime_index") != "wiki"
    nodes = route[:3] + [str(item.get("name") or item.get("title")) for item in symbols[:3]]
    graph_neighbors = _dedupe(edge for node in nodes if node for edge in neighbors(root, node))[:16] if include_graph else []
    version_warnings: list[dict[str, Any]] = []
    for item in pages + symbols:
        versions = item.get("versions", [])
        status = str(item.get("status", "")).casefold()
        if status in {"stale", "conflict", "deprecated"} or len(versions) > 1:
            version_warnings.append({"id": item.get("id"), "status": item.get("status"), "versions": versions})
    knowledge_gaps: list[str] = []
    if not hits:
        knowledge_gaps.append("No indexed evidence matches the query.")
    if hits and not source_spans:
        knowledge_gaps.append("Matching entries have no page-level source spans; verify primary sources before relying on claims.")
    suggested = _dedupe(
        [item.get("path") for item in pages + symbols if item.get("path")]
        + [span.get("path") for span in source_spans if span.get("path")]
    )
    pack: dict[str, Any] = {
        "route": route,
        "pages": pages,
        "symbols": symbols,
        "source_spans": source_spans,
        "graph_neighbors": graph_neighbors,
        "version_warnings": version_warnings,
        "knowledge_gaps": knowledge_gaps,
        "suggested_next_reads": suggested,
    }
    # Budget is an approximate token budget (four UTF-8-ish characters per token).
    order = ("graph_neighbors", "suggested_next_reads", "symbols", "pages", "source_spans", "route", "version_warnings", "knowledge_gaps")
    while len(json.dumps(pack, ensure_ascii=False, default=str)) > budget * 4:
        key = next((name for name in order if pack[name]), None)
        if key is None:
            break
        pack[key].pop()
    return pack
