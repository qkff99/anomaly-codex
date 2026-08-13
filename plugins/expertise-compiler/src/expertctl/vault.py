from __future__ import annotations

import json
import hashlib
import os
import re
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from . import __version__


VAULT_DIRNAME = ".expertise"
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_WINDOWS_RESERVED = {"con", "prn", "aux", "nul", *(f"com{number}" for number in range(1, 10)), *(f"lpt{number}" for number in range(1, 10))}
_DIRECTORIES = (
    "sources/raw",
    "sources/normalized",
    "wiki/maps",
    "wiki/concepts",
    "wiki/systems",
    "wiki/components",
    "wiki/recipes",
    "wiki/decisions",
    "wiki/comparisons",
    "wiki/errors",
    "wiki/sources",
    "code",
    "state",
    "generated-skill/references",
)
_JSONL_FILES = (
    "sources/registry.jsonl",
    "code/repositories.jsonl",
    "code/files.jsonl",
    "code/symbols.jsonl",
    "code/edges.jsonl",
    "code/aliases.jsonl",
    "state/provenance.jsonl",
    "state/build-log.jsonl",
    "state/update-log.jsonl",
    "state/task-ledger.jsonl",
    "state/diagnostic-probes.jsonl",
    "state/diagnostic-retirements.jsonl",
    "state/candidates.jsonl",
    "state/errors.jsonl",
)


def validate_name(name: str) -> str:
    """Validate a portable vault name and return its trimmed form."""
    if not isinstance(name, str):
        raise TypeError("vault name must be a string")
    value = name.strip()
    if (
        value in {"", ".", ".."}
        or not _NAME_RE.fullmatch(value)
        or value.endswith((".", " "))
        or value.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
    ):
        raise ValueError("vault name must use 1-64 lowercase ASCII letters, digits, or '-'")
    return value


def vault_path(workspace: Path, name: str) -> Path:
    root = Path(workspace).expanduser().resolve()
    container = root / VAULT_DIRNAME
    resolved_container = container.resolve()
    try:
        resolved_container.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{VAULT_DIRNAME} escapes workspace: {container}") from exc
    target = container / validate_name(name)
    resolved_target = target.resolve()
    try:
        resolved_target.relative_to(resolved_container)
    except ValueError as exc:
        raise ValueError(f"vault escapes {VAULT_DIRNAME}: {target}") from exc
    return target


def vault_reference(vault: Path) -> str:
    """Return the portable workspace-relative identity for a vault."""
    root = Path(vault).expanduser().resolve()
    if root.parent.name == VAULT_DIRNAME:
        return f"{VAULT_DIRNAME}/{root.name}"
    return root.name


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@contextmanager
def _file_lock(path: Path, timeout: float = 10.0) -> Any:
    """Small cross-platform lock for short metadata writes."""
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + timeout
    descriptor: int | None = None
    token = f"{os.getpid()}:{time.time_ns()}"
    while descriptor is None:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, token.encode("ascii"))
        except FileExistsError:
            try:
                owner = lock.read_text(encoding="ascii", errors="ignore").partition(":")[0]
                owner_alive = True
                if owner.isdigit():
                    try:
                        os.kill(int(owner), 0)
                    except ProcessLookupError:
                        owner_alive = False
                    except PermissionError:
                        owner_alive = True
                    except OSError:
                        # Windows reports an invalid (already exited) PID as
                        # a generic OSError instead of ProcessLookupError.
                        owner_alive = False
                if not owner_alive or (not owner.isdigit() and time.time() - lock.stat().st_mtime > max(60.0, timeout * 2)):
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for lock: {lock}")
            time.sleep(0.05)
    os.close(descriptor)
    try:
        yield
    finally:
        try:
            if lock.read_text(encoding="ascii", errors="ignore") == token:
                lock.unlink()
        except FileNotFoundError:
            pass


def atomic_write_text(path: Path, text: str) -> None:
    """Replace a UTF-8 text file atomically within its directory."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(target):
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = handle.name
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary:
                try:
                    Path(temporary).unlink()
                except FileNotFoundError:
                    pass


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Replace a binary file atomically within its directory."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(target):
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False) as handle:
                temporary = handle.name
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)


def write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


def append_jsonl(path: Path, item: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with _file_lock(target):
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())


def read_jsonl(path: Path) -> list[Any]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    records: list[Any] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{number}: {exc.msg}") from exc
    return records


def _inventory_artifacts_match(vault: Path, manifest: Any) -> bool:
    if not isinstance(manifest, dict):
        return False
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return not manifest.get("sources")
    required = {
        "code/files.jsonl",
        "code/symbols.jsonl",
        "code/edges.jsonl",
        "code/aliases.jsonl",
        "code/repo-map.md",
    }
    if not required <= set(artifacts):
        return False
    root = Path(vault).resolve()
    declared_source_pages: set[str] = set()
    for relative, expected in artifacts.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            return False
        portable = PurePosixPath(relative.replace("\\", "/"))
        if portable.is_absolute() or ".." in portable.parts:
            return False
        if not (relative.startswith("code/") or relative.startswith("wiki/sources/")):
            return False
        path = root.joinpath(*portable.parts).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return False
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return False
        if relative.startswith("wiki/sources/"):
            declared_source_pages.add(portable.as_posix())
    actual_source_pages = {
        path.relative_to(root).as_posix()
        for path in (root / "wiki" / "sources").rglob("*.md")
        if path.is_file()
    }
    return declared_source_pages == actual_source_pages


def _publication_manifest(vault: Path) -> dict[str, Any]:
    root = Path(vault).resolve()
    wiki = root / "wiki"
    pages = {
        path.relative_to(wiki).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(wiki.rglob("*.md"))
        if path.is_file() and not (path.relative_to(wiki).parts and path.relative_to(wiki).parts[0].casefold() == "sources")
    }
    state_files = (
        "provenance.jsonl",
        "errors.jsonl",
        "candidates.jsonl",
        "diagnostic-probes.jsonl",
        "diagnostic-retirements.jsonl",
        "task-ledger.jsonl",
    )
    latest_sources: dict[str, dict[str, Any]] = {}
    for item in read_jsonl(root / "sources" / "registry.jsonl"):
        if isinstance(item, dict) and item.get("id"):
            latest_sources[str(item["id"])] = {
                "snapshot": item.get("snapshot"),
                "sha256": item.get("sha256"),
                "normalized_sha256": item.get("normalized_sha256"),
            }
    config = read_json(root / "vault.json", {})
    if isinstance(config, dict) and config.get("source_storage") == "workspace-reference":
        cited_sources = {
            str(span.get("source") or span.get("source_id") or "")
            for item in read_jsonl(root / "state" / "provenance.jsonl")
            if isinstance(item, dict)
            for span in [item.get("source_span")]
            if isinstance(span, dict)
        }
        latest_sources = {source_id: value for source_id, value in latest_sources.items() if source_id in cited_sources}
    return {
        "schema_version": 2,
        "wiki": pages,
        "sources": dict(sorted(latest_sources.items())),
        "state": {
            name: hashlib.sha256((root / "state" / name).read_bytes()).hexdigest()
            if (root / "state" / name).is_file()
            else None
            for name in state_files
        },
    }


def _publication_integrity_match(vault: Path, manifest: Any | None = None) -> bool:
    root = Path(vault).resolve()
    semantic_pages = [
        path
        for path in (root / "wiki").rglob("*.md")
        if path.is_file()
        and path.name not in {"ROUTER.md", "INDEX.md"}
        and (not path.relative_to(root / "wiki").parts or path.relative_to(root / "wiki").parts[0].casefold() not in {"sources", "recipes"})
    ]
    if not semantic_pages:
        return True
    current = manifest if manifest is not None else read_json(root / "state/publication.json", {})
    expected = _publication_manifest(root)
    config = read_json(root / "vault.json", {})
    if isinstance(config, dict) and config.get("source_storage") == "workspace-reference" and isinstance(current, dict):
        current = dict(current)
        expected_sources = expected.get("sources", {})
        current["sources"] = {
            source_id: value
            for source_id, value in dict(current.get("sources", {})).items()
            if source_id in expected_sources
        }
    return isinstance(current, dict) and current == expected


def init_vault(workspace: Path, name: str, goal_text: str = "") -> Path:
    """Create an empty, portable expertise vault."""
    value = validate_name(name)
    vault = vault_path(workspace, value)
    vault.mkdir(parents=True, exist_ok=False)
    for relative in _DIRECTORIES:
        (vault / relative).mkdir(parents=True, exist_ok=True)
    config = {
        "created_at": _utc_now(),
        "name": value,
        "schema_version": 1,
    }
    write_json(vault / "vault.json", config)
    goal = goal_text.strip()
    competency = f"# {value}\n\n## Goal\n\n{goal or 'Not specified.'}\n"
    atomic_write_text(vault / "COMPETENCY.md", competency)
    for relative in _JSONL_FILES:
        atomic_write_text(vault / relative, "")
    write_json(vault / "state/hashes.json", {})
    write_json(vault / "state/backlinks.json", {})
    write_json(vault / "state/diagnostics.json", {})
    write_json(vault / "code/inventory.json", {"schema_version": 1, "sources": []})
    atomic_write_text(vault / "code/repo-map.md", "# Repository Map\n")
    return vault


def load_config(vault: Path) -> dict[str, Any]:
    config = read_json(Path(vault) / "vault.json")
    if not isinstance(config, dict):
        raise ValueError(f"missing or invalid vault config: {Path(vault) / 'vault.json'}")
    if config.get("schema_version") != 1:
        raise ValueError(f"unsupported vault schema version: {config.get('schema_version')!r}")
    validate_name(config.get("name", ""))
    return config


def _count_jsonl(path: Path) -> int | None:
    try:
        return len(read_jsonl(path))
    except (OSError, ValueError):
        return None


def _status_event(event: dict[str, Any] | None, fields: tuple[str, ...]) -> dict[str, Any] | None:
    """Keep routine harness status bounded even when a build log is large."""
    if not isinstance(event, dict):
        return None
    summary = {field: event[field] for field in fields if field in event}
    if "published" in event and isinstance(event["published"], list):
        summary["published_count"] = len(event["published"])
    if "sources" in event and isinstance(event["sources"], list):
        summary["source_count"] = len(event["sources"])
    return summary


def status(vault: Path) -> dict[str, Any]:
    root = Path(vault).expanduser().resolve()
    config: dict[str, Any] = {}
    initialized = False
    try:
        config = load_config(root)
        initialized = True
    except (OSError, TypeError, ValueError):
        pass
    wiki = root / "wiki"
    registry = [item for item in read_jsonl(root / "sources/registry.jsonl") if isinstance(item, dict)]
    latest_sources: dict[str, dict[str, Any]] = {}
    for item in registry:
        source_id = str(item.get("id") or "")
        if source_id:
            latest_sources[source_id] = item
    source_versions = [
        {
            "id": source_id,
            "kind": item.get("kind"),
            "snapshot": item.get("snapshot"),
            "commit": item.get("commit"),
            "retrieved_at": item.get("added_at"),
        }
        for source_id, item in sorted(latest_sources.items())
    ]
    inventory_manifest = read_json(root / "code/inventory.json", {})
    expected_inventory = [
        {
            "id": item["id"],
            "snapshot": item["snapshot"],
            "sha256": latest_sources[item["id"]].get("sha256"),
            "normalized_sha256": latest_sources[item["id"]].get("normalized_sha256"),
            "commit": item["commit"],
        }
        for item in source_versions
    ]
    inventory_fresh = (
        isinstance(inventory_manifest, dict)
        and inventory_manifest.get("schema_version") == 1
        and inventory_manifest.get("sources") == expected_inventory
        and _inventory_artifacts_match(root, inventory_manifest)
    )
    builds = [item for item in read_jsonl(root / "state/build-log.jsonl") if isinstance(item, dict)]
    updates = [item for item in read_jsonl(root / "state/update-log.jsonl") if isinstance(item, dict)]
    stale_pages = sorted(
        {
            str(item.get("page") or "").replace("\\", "/").removeprefix("wiki/")
            for item in read_jsonl(root / "state/errors.jsonl")
            if isinstance(item, dict) and item.get("kind") == "stale-source" and item.get("page")
        }
    )
    unresolved_candidates = sorted(
        str(item.get("candidate_id") or "")
        for item in read_jsonl(root / "state/candidates.jsonl")
        if isinstance(item, dict) and item.get("candidate_id") and item.get("status") != "resolved"
    )
    publication_pending = (root / "state/publish-journal.json").is_file()
    update_pending = (root / "state/pending-update.json").is_file()
    impact = read_json(root / "state/impact.json", {})
    impact_pending = bool(
        isinstance(impact, dict)
        and (
            impact.get("targeted_recompile_required")
            or impact.get("extraction_required")
            or impact.get("impacted_pages")
        )
    )
    publication_integrity = _publication_integrity_match(root)
    return {
        "vault": vault_reference(root),
        "exists": root.is_dir(),
        "initialized": initialized,
        "name": config.get("name"),
        "schema_version": config.get("schema_version"),
        "tool": {"name": "expertctl", "version": __version__},
        "implementation": config.get("implementation") or config.get("name"),
        "version": config.get("version"),
        "sources": len(latest_sources),
        "source_history": len(registry),
        "source_versions": source_versions,
        "inventory_fresh": inventory_fresh,
        "latest_source_at": max((str(item.get("added_at")) for item in latest_sources.values() if item.get("added_at")), default=None),
        "latest_build": _status_event(builds[-1] if builds else None, ("build", "created_at", "phase", "diagnostic_pass_rate")),
        "latest_update": _status_event(updates[-1] if updates else None, ("checked_at", "changed")),
        "stale_pages": stale_pages,
        "stale_count": len(stale_pages),
        "unresolved_candidates": unresolved_candidates,
        "publication_pending": publication_pending,
        "update_pending": update_pending,
        "impact_pending": impact_pending,
        "impacted_recipes": sorted(str(item) for item in impact.get("impacted_recipes", [])) if isinstance(impact, dict) else [],
        "targeted_recompile_required": bool(isinstance(impact, dict) and impact.get("targeted_recompile_required")),
        "extraction_required": bool(isinstance(impact, dict) and impact.get("extraction_required")),
        "publication_integrity": publication_integrity,
        "fresh": (
            inventory_fresh
            and publication_integrity
            and not stale_pages
            and not unresolved_candidates
            and not publication_pending
            and not update_pending
            and not impact_pending
        ),
        "files": _count_jsonl(root / "code/files.jsonl"),
        "symbols": _count_jsonl(root / "code/symbols.jsonl"),
        "edges": _count_jsonl(root / "code/edges.jsonl"),
        "wiki_pages": sum(1 for path in wiki.rglob("*.md") if path.is_file()) if wiki.is_dir() else 0,
    }


def doctor(vault: Path) -> dict[str, Any]:
    root = Path(vault).expanduser().resolve()
    checks: list[dict[str, Any]] = []

    def check(name: str, operation: Any) -> None:
        try:
            detail = operation()
            checks.append({"name": name, "ok": True, "detail": detail} if detail else {"name": name, "ok": True})
        except Exception as exc:  # doctor must report all independent failures
            checks.append({"name": name, "ok": False, "error": str(exc)})

    check("vault directory", lambda: vault_reference(root) if root.is_dir() else (_ for _ in ()).throw(FileNotFoundError(root)))
    check("vault config", lambda: load_config(root))
    config = read_json(root / "vault.json", {})
    reference_mode = isinstance(config, dict) and config.get("source_storage") == "workspace-reference"
    required_directories = ("sources", "wiki", "code", "state")
    if not reference_mode:
        required_directories = ("sources", "sources/raw", "sources/normalized", "wiki", "code", "state")
    for relative in required_directories:
        check(relative, lambda relative=relative: None if (root / relative).is_dir() else (_ for _ in ()).throw(FileNotFoundError(relative)))
    for relative in ("sources/registry.jsonl", "code/files.jsonl", "code/symbols.jsonl", "code/edges.jsonl", "code/aliases.jsonl"):
        check(relative, lambda relative=relative: f"{len(read_jsonl(root / relative))} records")

    def record_schemas() -> str:
        schemas: dict[str, tuple[str, ...]] = {
            "sources/registry.jsonl": ("id", "kind", "uri", "raw_path", "normalized_path", "sha256", "snapshot"),
            "code/files.jsonl": ("id", "source_id", "path", "logical_path", "language", "sha256"),
            "code/symbols.jsonl": ("id", "source_id", "file_id", "path", "logical_path", "kind", "name", "qualified_name", "line"),
            "code/edges.jsonl": ("id", "source", "target", "kind"),
            "code/aliases.jsonl": ("alias", "target", "kind"),
            "state/provenance.jsonl": ("page", "source_span"),
        }
        records: dict[str, list[dict[str, Any]]] = {}
        for relative, required in schemas.items():
            values = read_jsonl(root / relative)
            typed: list[dict[str, Any]] = []
            seen: set[str] = set()
            for number, item in enumerate(values, 1):
                if not isinstance(item, dict):
                    raise ValueError(f"{relative}:{number} must be an object")
                missing = [field for field in required if item.get(field) in (None, "")]
                if missing:
                    raise ValueError(f"{relative}:{number} missing {', '.join(missing)}")
                if relative != "sources/registry.jsonl" and item.get("id"):
                    identifier = str(item["id"])
                    if identifier in seen:
                        raise ValueError(f"{relative}:{number} duplicate id {identifier!r}")
                    seen.add(identifier)
                for field in ("path", "logical_path", "raw_path", "normalized_path", "page"):
                    if not item.get(field):
                        continue
                    path = PurePosixPath(str(item[field]).replace("\\", "/"))
                    if path.is_absolute() or ".." in path.parts:
                        raise ValueError(f"{relative}:{number} unsafe {field}: {item[field]!r}")
                typed.append(item)
            records[relative] = typed

        source_ids = {str(item["id"]) for item in records["sources/registry.jsonl"]}
        file_ids = {str(item["id"]) for item in records["code/files.jsonl"]}
        symbol_ids = {str(item["id"]) for item in records["code/symbols.jsonl"]}
        if any(str(item["source_id"]) not in source_ids for item in records["code/files.jsonl"]):
            raise ValueError("code/files.jsonl references an unknown source")
        if any(str(item["file_id"]) not in file_ids for item in records["code/symbols.jsonl"]):
            raise ValueError("code/symbols.jsonl references an unknown file")
        if any(str(item["target"]) not in symbol_ids for item in records["code/aliases.jsonl"]):
            raise ValueError("code/aliases.jsonl references an unknown symbol")
        return f"{sum(len(items) for items in records.values())} typed records satisfy required fields and references"

    check("record schemas", record_schemas)

    def symlink_safety() -> str:
        for current, directories, names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            kept: list[str] = []
            for name in sorted(directories):
                path = current_path / name
                resolved = path.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ValueError(f"directory link escapes vault: {path.relative_to(root)}") from exc
                if path.is_symlink() or resolved != path.absolute():
                    continue
                kept.append(name)
            directories[:] = kept
            for name in names:
                path = current_path / name
                try:
                    path.resolve().relative_to(root)
                except ValueError as exc:
                    raise ValueError(f"file link escapes vault: {path.relative_to(root)}") from exc
        return "no escaping symlinks"

    def wiki_links() -> str:
        from .compiler import _validate_links

        _validate_links(root / "wiki")
        return "all internal links resolve"

    def raw_integrity() -> str:
        from .sources import NORMALIZER_VERSION, _collect_tree, _tree_digest, workspace_reference_files

        checked = 0
        raw_parent = (root / "sources" / "raw").resolve()
        registry = [item for item in read_jsonl(root / "sources" / "registry.jsonl") if isinstance(item, dict)]
        latest = {str(item.get("id") or ""): item for item in registry if item.get("id")}
        entries = list(latest.values()) if reference_mode else registry
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            reference_files = workspace_reference_files(root, entry)
            if reference_files is not None:
                if _tree_digest(reference_files) != entry.get("sha256"):
                    raise ValueError(f"workspace-reference source hash mismatch: {entry.get('id')}@{entry.get('snapshot')}")
                checked += 1
                continue
            snapshot = (root / str(entry.get("raw_path", ""))).resolve()
            try:
                snapshot.relative_to(raw_parent)
            except ValueError as exc:
                raise ValueError(f"raw snapshot escapes vault: {entry.get('id')}") from exc
            if not snapshot.is_dir():
                raise FileNotFoundError(f"raw snapshot missing: {snapshot}")
            files, _ = _collect_tree(snapshot)
            if _tree_digest(files) != entry.get("sha256"):
                raise ValueError(f"raw snapshot hash mismatch: {entry.get('id')}@{entry.get('snapshot')}")
            normalized = (root / str(entry.get("normalized_path", ""))).resolve()
            normalized_parent = (root / "sources" / "normalized").resolve()
            try:
                normalized.relative_to(normalized_parent)
            except ValueError as exc:
                raise ValueError(f"normalized snapshot escapes vault: {entry.get('id')}") from exc
            if not normalized.is_dir():
                raise FileNotFoundError(f"normalized snapshot missing: {normalized}")
            normalized_files, _ = _collect_tree(normalized)
            if _tree_digest(normalized_files) != entry.get("normalized_sha256"):
                raise ValueError(f"normalized snapshot hash/version mismatch: {entry.get('id')}@{entry.get('snapshot')}")
            if latest.get(str(entry.get("id") or "")) is entry and entry.get("normalizer_version") != NORMALIZER_VERSION:
                raise ValueError(f"latest normalized snapshot uses an obsolete normalizer: {entry.get('id')}@{entry.get('snapshot')}")
            checked += 1
        storage = "workspace references" if reference_mode else "raw and normalized snapshots"
        return f"{checked} {storage} match registry hashes"

    def inventory_freshness() -> str:
        registry: dict[str, dict[str, Any]] = {}
        for item in read_jsonl(root / "sources/registry.jsonl"):
            if isinstance(item, dict) and item.get("id"):
                registry[str(item["id"])] = item
        expected = [
            {
                "id": source_id,
                "snapshot": item.get("snapshot"),
                "sha256": item.get("sha256"),
                "normalized_sha256": item.get("normalized_sha256"),
                "commit": item.get("commit"),
            }
            for source_id, item in sorted(registry.items())
        ]
        manifest = read_json(root / "code/inventory.json", {})
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("sources") != expected
            or not _inventory_artifacts_match(root, manifest)
        ):
            raise ValueError("structural inventory is stale; run expertctl scan")
        return f"inventory matches {len(expected)} latest source snapshots"

    def wiki_provenance() -> str:
        from .compiler import _factual_paragraphs, _validate_recipe_evidence, _validate_span
        from .index import _frontmatter, _wiki_documents

        checked = 0
        for page in _wiki_documents(root):
            relative = str(page.get("path") or "")
            if relative in {"wiki/ROUTER.md", "wiki/INDEX.md"}:
                continue
            path = root / Path(*relative.split("/"))
            text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
            if page.get("type") == "verified-recipe":
                if not relative.startswith("wiki/recipes/"):
                    raise ValueError(f"verified recipe is outside wiki/recipes: {relative}")
                meta, _ = _frontmatter(text)
                _validate_recipe_evidence(root, meta.get("verification"), meta.get("evidence") or meta.get("sources"))
                checked += 1
                continue
            if relative.startswith("wiki/sources/") and text.startswith("<!-- generated by expertctl scan -->"):
                continue
            spans = page.get("source_spans", [])
            if not spans:
                raise ValueError(f"Wiki page has no provenance: {relative}")
            for span in spans:
                _validate_span(root, span)
            paragraphs = _factual_paragraphs(text)
            if paragraphs:
                covered: set[int] = set()
                for claim in page.get("claims", []):
                    if not isinstance(claim, dict):
                        continue
                    paragraph = claim.get("paragraph")
                    if not isinstance(paragraph, int) or isinstance(paragraph, bool) or not 1 <= paragraph <= len(paragraphs):
                        raise ValueError(f"Wiki page has invalid paragraph provenance: {relative}")
                    expected_hash = hashlib.sha256(paragraphs[paragraph - 1].encode("utf-8")).hexdigest()
                    if claim.get("paragraph_sha256") != expected_hash or not isinstance(claim.get("source_span"), dict):
                        raise ValueError(f"Wiki paragraph hash/provenance mismatch: {relative}#{paragraph}")
                    _validate_span(root, claim["source_span"])
                    covered.add(paragraph)
                required = (95 * len(paragraphs) + 99) // 100
                if len(covered) < required:
                    raise ValueError(f"Wiki paragraph provenance coverage is below 95%: {relative}")
            checked += 1
        return f"{checked} factual pages have resolvable provenance"

    def publication_state() -> str:
        if (root / "state/publish-journal.json").is_file():
            raise ValueError("interrupted publication journal requires recovery by expertctl apply-build")
        if (root / "state/pending-update.json").is_file():
            raise ValueError("interrupted source update journal requires recovery by expertctl add/update")
        factual = [
            path
            for path in (root / "wiki").rglob("*.md")
            if path.is_file() and path.name not in {"ROUTER.md", "INDEX.md"} and "sources" not in path.relative_to(root / "wiki").parts[:1]
        ]
        if factual:
            for name in ("ROUTER.md", "INDEX.md"):
                if not (root / "wiki" / name).is_file():
                    raise FileNotFoundError(f"published Wiki is missing {name}")
            unresolved = [
                str(item.get("candidate_id"))
                for item in read_jsonl(root / "state/candidates.jsonl")
                if isinstance(item, dict) and item.get("status") != "resolved"
            ]
            if unresolved:
                raise ValueError("published Wiki has unresolved candidates: " + ", ".join(sorted(unresolved)))
        stale = sorted(
            str(item.get("page"))
            for item in read_jsonl(root / "state/errors.jsonl")
            if isinstance(item, dict) and item.get("kind") == "stale-source" and item.get("page")
        )
        if stale:
            raise ValueError("stale Wiki pages: " + ", ".join(stale))
        impact = read_json(root / "state/impact.json", {})
        if isinstance(impact, dict) and (
            impact.get("targeted_recompile_required")
            or impact.get("extraction_required")
            or impact.get("impacted_pages")
        ):
            raise ValueError("pending source impact requires extraction and synthesis")
        ledger: dict[str, dict[str, Any]] = {}
        ledger_ids: dict[str, str] = {}
        for item in read_jsonl(root / "state/task-ledger.jsonl"):
            if not isinstance(item, dict) or not item.get("id") or not item.get("recipe") or not item.get("sha256"):
                raise ValueError("task ledger contains an invalid recipe record")
            recipe_path = str(item["recipe"]).replace("\\", "/")
            recipe_id = str(item["id"])
            if recipe_id in ledger_ids and ledger_ids[recipe_id] != recipe_path:
                raise ValueError(f"task ledger reuses a recipe identity for another path: {recipe_id}")
            previous = ledger.get(recipe_path)
            if previous is not None and (
                previous.get("id") != recipe_id
                or item.get("supersedes_sha256") != previous.get("sha256")
            ):
                raise ValueError(f"task ledger contains an invalid recipe revision chain: {recipe_id}")
            if previous is None and item.get("supersedes_sha256"):
                raise ValueError(f"task ledger begins with an invalid recipe revision: {recipe_id}")
            ledger[recipe_path] = item
            ledger_ids[recipe_id] = recipe_path
        recipe_pages = sorted((root / "wiki" / "recipes").rglob("*.md"))
        for page in recipe_pages:
            relative = page.relative_to(root).as_posix()
            item = ledger.get(relative)
            digest = hashlib.sha256(page.read_bytes()).hexdigest()
            if item is None or item.get("sha256") != digest:
                raise ValueError(f"verified recipe does not match its task-ledger record: {relative}")
        missing_recipes = sorted(relative for relative in ledger if not (root / Path(*PurePosixPath(relative).parts)).is_file())
        if missing_recipes:
            raise FileNotFoundError("task ledger references missing recipes: " + ", ".join(missing_recipes))
        return f"{len(factual)} published factual pages; no unresolved candidates or stale pages"

    def publication_integrity() -> str:
        if not _publication_integrity_match(root):
            raise ValueError("published Wiki/state hashes do not match the accepted publication manifest")
        return "published Wiki and provenance match the accepted generation"

    check("symlink safety", symlink_safety)
    check("raw snapshot hashes", raw_integrity)
    check("inventory freshness", inventory_freshness)
    check("Wiki links", wiki_links)
    check("Wiki provenance", wiki_provenance)
    check("publication integrity", publication_integrity)
    check("publication state", publication_state)

    errors = [item for item in checks if not item["ok"]]
    healthy = not errors
    return {
        "vault": vault_reference(root),
        "healthy": healthy,
        "ok": healthy,
        "checks": checks,
        "errors": errors,
    }


def _evidence_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value).strip().replace("\\", "/").casefold()
        if normalized:
            keys.update({normalized, normalized.removeprefix("wiki/")})
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"id", "path", "page", "source", "source_id", "name", "qualified_name", "route", "neighbor"}:
                keys.update(_evidence_keys(item))
            elif isinstance(item, (dict, list, tuple)):
                keys.update(_evidence_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_evidence_keys(item))
    return keys


def evaluate_probes(vault: Path) -> dict[str, Any]:
    """Run persisted retrieval/evidence probes without mutating or health-checking a vault."""
    from .index import _load_index, _wiki_documents, context, find_path, search, symbol, tokenize

    root = Path(vault).expanduser().resolve()
    probes = read_jsonl(root / "state/diagnostic-probes.jsonl")
    results: list[dict[str, Any]] = []
    for number, probe in enumerate(probes, 1):
        if not isinstance(probe, dict):
            results.append({"id": f"invalid-{number}", "passed": False, "error": "probe must be an object"})
            continue
        probe_id = str(probe.get("id") or f"probe-{number}")
        kind = str(probe.get("kind") or "exact-fact")
        query = str(probe.get("query") or "")
        try:
            if kind == "symbol-lookup":
                actual_value: Any = symbol(root, query)
            elif kind == "multi-hop":
                actual_value = find_path(root, str(probe.get("start") or ""), str(probe.get("end") or ""), int(probe.get("max_depth", 6)))
            elif kind == "prompt-injection":
                actual_value = [
                    item
                    for item in read_jsonl(root / "sources/registry.jsonl")
                    if isinstance(item, dict) and item.get("prompt_injection_flags")
                ]
            elif kind == "stale-source":
                actual_value = [
                    item
                    for item in read_jsonl(root / "state/errors.jsonl")
                    if isinstance(item, dict) and item.get("kind") == "stale-source"
                ]
            elif kind == "missing-evidence":
                vocabulary = _load_index(root).get("df", {})
                actual_value = search(root, query, limit=20) if any(term in vocabulary for term in tokenize(query)) else []
            elif kind == "version-conflict":
                actual_value = [
                    item
                    for item in _wiki_documents(root)
                    if str(item.get("status") or "").casefold() == "conflict" or len(item.get("versions", [])) > 1
                ]
            else:
                actual_value = {"search": search(root, query, limit=20), "context": context(root, query, budget=4000)}
            actual = _evidence_keys(actual_value)
            expected_values = probe.get("expected_evidence", [])
            expected = _evidence_keys(expected_values)
            abstention = bool(probe.get("expect_abstention"))
            passed = (not actual) if abstention else bool(expected) and expected <= actual
            results.append(
                {
                    "id": probe_id,
                    "kind": kind,
                    "query": query,
                    "passed": passed,
                    "expected_evidence": sorted(expected),
                    "actual_evidence": sorted(actual),
                    **({"error": "expected evidence was not retrieved"} if not passed else {}),
                }
            )
        except Exception as exc:
            results.append({"id": probe_id, "kind": kind, "query": query, "passed": False, "error": str(exc)})
    passed_count = sum(1 for item in results if item.get("passed"))
    pass_rate = passed_count / len(results) if results else 0.0
    config = read_json(root / "vault.json", {})
    threshold = float(config.get("diagnostic_threshold", 0.9)) if isinstance(config, dict) else 0.9
    semantic_healthy = bool(results) and pass_rate >= threshold
    return {
        "vault": vault_reference(root),
        "healthy": semantic_healthy,
        "ok": semantic_healthy,
        "diagnostic_threshold": threshold,
        "diagnostic_pass_rate": pass_rate,
        "diagnostics_passed": passed_count,
        "diagnostics_total": len(results),
        "diagnostics": results,
    }


def evaluate(vault: Path) -> dict[str, Any]:
    """Run deterministic health plus persisted retrieval/evidence probes."""
    root = Path(vault).expanduser().resolve()
    deterministic = doctor(root)
    semantic = evaluate_probes(root)
    healthy = bool(deterministic.get("healthy")) and bool(semantic.get("healthy"))
    return {
        **semantic,
        "vault": vault_reference(root),
        "healthy": healthy,
        "ok": healthy,
        "checks": deterministic.get("checks", []),
        "errors": deterministic.get("errors", []),
    }
