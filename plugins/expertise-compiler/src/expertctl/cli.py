from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import __version__
from .compiler import (
    apply_build,
    compile_plan,
    generate_domain_skill,
    record_recipe,
    repair_plan,
    research_plan,
    validate_research_manifest,
)
from .index import build_index, callers, context, find_path, neighbors, references, search, symbol
from .inventory import scan
from .sources import _changed_files, _snapshot_content_map, add_sources, materialize_workspace_references, migrate_workspace_paths, redact_secrets, refresh_sources, workspace_reference_path
from .vault import _file_lock, _publication_manifest, append_jsonl, atomic_write_bytes, atomic_write_text, doctor, evaluate, init_vault, load_config, read_json, read_jsonl, status, vault_path, vault_reference, write_json


def _emit(value: Any, as_json: bool = False) -> None:
    if as_json or not isinstance(value, str):
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        print(value)


def _vault(args: argparse.Namespace) -> Path:
    path = vault_path(Path(args.workspace), args.domain)
    if not path.is_dir():
        raise FileNotFoundError(f"vault not found: {path}")
    return path


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("path escapes the allowed root")
    return candidate


def _install_dir(agent: str) -> Path:
    home = Path.home()
    return {
        "codex": home / ".codex" / "skills",
        "claude": home / ".claude" / "skills",
        "hermes": home / ".hermes" / "skills",
    }[agent]


def _copy_skill(source: Path, target_root: Path) -> Path:
    source = Path(source).expanduser().resolve()
    target_root = Path(target_root).expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    skill_file = source / "SKILL.md"
    match = re.search(r"^name:\s*([a-z0-9-]+)\s*$", skill_file.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise ValueError(f"skill has no valid frontmatter name: {skill_file}")
    target = target_root / match.group(1)
    resolved_target = target.resolve()
    if source == resolved_target or source in resolved_target.parents or resolved_target in source.parents:
        raise ValueError(f"skill source and install target overlap: {source} -> {target}")
    if target.exists() and (target.is_symlink() or resolved_target != target.absolute()):
        raise ValueError(f"skill install target must not be a link: {target}")

    staging_parent = Path(tempfile.mkdtemp(prefix=f".{target.name}-install-", dir=target_root))
    backup_parent: Path | None = None
    staged = staging_parent / target.name
    try:
        shutil.copytree(source, staged)
        if target.exists():
            backup_parent = Path(tempfile.mkdtemp(prefix=f".{target.name}-backup-", dir=target_root))
            os.replace(target, backup_parent / target.name)
        try:
            os.replace(staged, target)
        except Exception:
            if backup_parent is not None and (backup_parent / target.name).exists() and not target.exists():
                os.replace(backup_parent / target.name, target)
            raise
        if backup_parent is not None:
            shutil.rmtree(backup_parent)
            backup_parent = None
        return target
    finally:
        if staging_parent.exists():
            shutil.rmtree(staging_parent)
        if backup_parent is not None and backup_parent.exists() and not (backup_parent / target.name).exists():
            shutil.rmtree(backup_parent)


def _cmd_init(args: argparse.Namespace) -> Any:
    goal = Path(args.goal_file).read_text(encoding="utf-8") if args.goal_file else ""
    return {"vault": vault_reference(init_vault(Path(args.workspace), args.domain, goal))}


def _add_to_vault(
    vault: Path,
    sources: list[str],
    declared_metadata: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pending_path = vault / "state" / "pending-update.json"
    recovered = _recover_pending_update(vault, pending_path)
    old_latest = _latest_registry(vault)
    old_files = read_jsonl(vault / "code" / "files.jsonl")
    old_symbols = read_jsonl(vault / "code" / "symbols.jsonl")
    prepared = {
        "schema_version": 1,
        "status": "prepared",
        "operation": "add",
        "old_latest": old_latest,
        "old_files": old_files,
        "old_symbols": old_symbols,
    }
    write_json(pending_path, prepared)
    try:
        records = add_sources(vault, sources, declared_metadata)
    except BaseException:
        if _latest_registry(vault) == old_latest:
            pending_path.unlink(missing_ok=True)
        raise
    reports = _source_change_reports(vault, old_latest, records)
    write_json(pending_path, {**prepared, "status": "sources-written", "reports": reports})
    changes = _process_source_changes(vault, reports, old_files, old_symbols, force=False)
    pending_path.unlink(missing_ok=True)
    changes["index"] = _build_index_if_stable(vault)
    result = {"sources": records, **{key: value for key, value in changes.items() if key != "sources"}}
    if recovered:
        result["recovered_update"] = recovered
        if not result.get("impact") and recovered.get("impact"):
            result["impact"] = recovered["impact"]
        result["changed"] = int(result.get("changed", 0)) + int(recovered.get("changed", 0))
    if changes.get("changed"):
        result["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        append_jsonl(vault / "state" / "update-log.jsonl", result)
    return result


def _cmd_add(args: argparse.Namespace) -> Any:
    return _add_to_vault(_vault(args), args.sources)


def _cmd_scan(args: argparse.Namespace) -> Any:
    result = scan(_vault(args))
    result["index"] = _build_index_if_stable(_vault(args))
    return result


def _cmd_search(args: argparse.Namespace) -> Any:
    return search(_vault(args), args.query, args.limit, args.kind, args.version, args.authority)


def _cmd_context(args: argparse.Namespace) -> Any:
    return context(_vault(args), args.query, args.budget)


def _latest_registry(vault: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in read_jsonl(vault / "sources" / "registry.jsonl"):
        if isinstance(item, dict) and item.get("id"):
            latest[str(item["id"])] = item
    return latest


def _source_change_reports(
    vault: Path,
    old_latest: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for new in records:
        source_id = str(new.get("id") or "")
        if not source_id:
            continue
        old = old_latest.get(source_id)
        if old is None:
            reports.append(
                {
                    "id": source_id,
                    "kind": new.get("kind"),
                    "uri": new.get("uri"),
                    "status": "changed",
                    "content_changed": True,
                    "version_changed": False,
                    "derived_changed": True,
                    "old_sha256": None,
                    "new_sha256": new.get("sha256"),
                    "old_snapshot": None,
                    "new_snapshot": new.get("snapshot"),
                    "old_commit": None,
                    "new_commit": new.get("commit"),
                    "changed_files": [
                        {"path": path, "status": "added"}
                        for path in sorted(_snapshot_content_map(vault, new))
                    ],
                    "diff_method": "new-source",
                }
            )
            continue
        content_changed = new.get("sha256") != old.get("sha256")
        version_changed = any(new.get(field) != old.get(field) for field in ("commit", "etag", "last_modified", "version"))
        derived_changed = any(
            new.get(field) != old.get(field)
            for field in ("normalized_sha256", "normalizer_version", "normalization_profile", "normalized_path")
        )
        reports.append(
            {
                "id": source_id,
                "kind": new.get("kind"),
                "uri": new.get("uri"),
                "status": "changed" if content_changed or version_changed or derived_changed else "unchanged",
                "content_changed": content_changed,
                "version_changed": version_changed,
                "derived_changed": derived_changed,
                "old_sha256": old.get("sha256"),
                "new_sha256": new.get("sha256"),
                "old_snapshot": old.get("snapshot"),
                "new_snapshot": new.get("snapshot"),
                "old_commit": old.get("commit"),
                "new_commit": new.get("commit"),
                "changed_files": _changed_files(vault, old, new) if content_changed else [],
                "diff_method": "snapshot-diff",
            }
        )
    return reports


def _recover_pending_update(vault: Path, pending_path: Path) -> dict[str, Any] | None:
    pending = read_json(pending_path, {})
    if not isinstance(pending, dict) or not pending:
        return None
    reports_value = pending.get("reports")
    if isinstance(reports_value, list):
        reports = [item for item in reports_value if isinstance(item, dict)]
    else:
        old_value = pending.get("old_latest")
        if not isinstance(old_value, dict):
            raise ValueError("invalid pending source update journal")
        old_latest = {
            str(source_id): item
            for source_id, item in old_value.items()
            if isinstance(source_id, str) and isinstance(item, dict)
        }
        reports = _source_change_reports(vault, old_latest, list(_latest_registry(vault).values()))
        write_json(pending_path, {**pending, "status": "sources-written", "reports": reports})
    result = _process_source_changes(
        vault,
        reports,
        pending.get("old_files", []) if isinstance(pending.get("old_files"), list) else [],
        pending.get("old_symbols", []) if isinstance(pending.get("old_symbols"), list) else [],
        force=False,
    )
    pending_path.unlink(missing_ok=True)
    result["index"] = _build_index_if_stable(vault)
    return result


def _build_index_if_stable(vault: Path) -> dict[str, Any]:
    state = status(vault)
    if (
        state.get("publication_pending")
        or state.get("update_pending")
        or state.get("impact_pending")
        or not state.get("publication_integrity")
    ):
        return {"stale": True, "reason": "publication or source recompilation is pending"}
    return build_index(vault)


def _span_line_range(span: dict[str, Any]) -> tuple[int | None, int | None]:
    start, end = span.get("start_line", span.get("start")), span.get("end_line", span.get("end"))
    if start is None and end is None and isinstance(span.get("lines"), str):
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", str(span["lines"]))
        if match:
            start, end = int(match.group(1)), int(match.group(2) or match.group(1))
    return (start if isinstance(start, int) else None, end if isinstance(end, int) else None)


def _intersects(ranges: Any, start: int | None, end: int | None) -> bool:
    if not isinstance(ranges, list) or not ranges or start is None or end is None:
        return True
    return any(
        isinstance(item, dict)
        and isinstance(item.get("start_line"), int)
        and isinstance(item.get("end_line"), int)
        and item["start_line"] <= end
        and start <= item["end_line"]
        for item in ranges
    )


def _process_source_changes(
    vault: Path,
    reports: list[dict[str, Any]],
    old_files: list[Any],
    old_symbols: list[Any],
    *,
    force: bool,
) -> dict[str, Any]:
    changed = [item for item in reports if item.get("status") == "changed"]
    content_changed = [item for item in changed if item.get("content_changed")]
    result: dict[str, Any] = {"sources": reports, "changed": len(changed)}
    if not (changed or force or not status(vault).get("inventory_fresh", False)):
        return result
    result["inventory"] = scan(vault)
    new_files = read_jsonl(vault / "code" / "files.jsonl")
    new_symbols = read_jsonl(vault / "code" / "symbols.jsonl")
    affected_sources = {str(item.get("id")) for item in content_changed}
    history = [item for item in read_jsonl(vault / "sources" / "registry.jsonl") if isinstance(item, dict)]
    changes_by_source: dict[str, dict[str, dict[str, Any]]] = {}
    changed_file_records: list[dict[str, Any]] = []
    for report in content_changed:
        source_id = str(report.get("id") or "")
        relevant_entries = [
            entry
            for entry in history
            if str(entry.get("id") or "") == source_id
            and entry.get("snapshot") in {report.get("old_snapshot"), report.get("new_snapshot")}
        ]
        for change in report.get("changed_files", []):
            if not isinstance(change, dict) or not change.get("path"):
                continue
            raw_path = str(change["path"]).replace("\\", "/")
            variants = {raw_path}
            for entry in relevant_entries:
                for mapping in entry.get("normalization_map", []):
                    if isinstance(mapping, dict) and str(mapping.get("raw") or "").replace("\\", "/") == raw_path:
                        variants.add(str(mapping.get("normalized") or "").replace("\\", "/"))
            for variant in variants:
                changes_by_source.setdefault(source_id, {})[variant] = change
            changed_file_records.append({"source": source_id, **change})

    def affected_symbol_names(files: list[Any], symbols: list[Any], range_key: str) -> set[str]:
        file_changes: dict[str, dict[str, Any]] = {}
        for item in files:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source_id") or "")
            change = changes_by_source.get(source_id, {}).get(str(item.get("logical_path") or "").replace("\\", "/"))
            if change is not None:
                file_changes[str(item.get("id") or "")] = change
        names: set[str] = set()
        for item in symbols:
            if not isinstance(item, dict):
                continue
            change = file_changes.get(str(item.get("file_id") or ""))
            if change is None:
                continue
            start = item.get("line") if isinstance(item.get("line"), int) else None
            end = item.get("end_line") if isinstance(item.get("end_line"), int) else start
            if _intersects(change.get(range_key), start, end):
                names.add(str(item.get("qualified_name") or item.get("name")))
        return names

    changed_symbols = sorted(
        affected_symbol_names(old_files, old_symbols, "old_line_ranges")
        | affected_symbol_names(new_files, new_symbols, "new_line_ranges")
    )
    old_snapshots = {str(item.get("id")): item.get("old_snapshot") for item in content_changed}
    recipe_pages = {
        str(item.get("recipe") or "").replace("\\", "/").removeprefix("wiki/")
        for item in read_jsonl(vault / "state" / "task-ledger.jsonl")
        if isinstance(item, dict) and item.get("recipe")
    }
    impacted: dict[str, list[dict[str, Any]]] = {}
    impacted_recipes: dict[str, list[dict[str, Any]]] = {}
    for item in read_jsonl(vault / "state" / "provenance.jsonl"):
        if not isinstance(item, dict):
            continue
        span = item.get("source_span") or item.get("span")
        if not isinstance(span, dict) or str(span.get("source") or "") not in affected_sources:
            continue
        source_id = str(span.get("source"))
        span_path = str(span.get("path") or span.get("file") or "").replace("\\", "/")
        logical_path = span_path
        for entry in history:
            prefix = str(entry.get("raw_path") or "").rstrip("/") + "/"
            if str(entry.get("id") or "") == source_id and span_path.startswith(prefix):
                logical_path = span_path[len(prefix) :]
                break
        source_changes = changes_by_source.get(source_id, {})
        change = source_changes.get(logical_path)
        if source_changes and change is None:
            continue
        start, end = _span_line_range(span)
        if change is not None and not _intersects(change.get("old_line_ranges"), start, end):
            continue
        if span.get("snapshot") and span.get("snapshot") != old_snapshots.get(source_id):
            continue
        owner = str(item.get("page") or item.get("page_id") or item.get("target") or "").replace("\\", "/").removeprefix("wiki/")
        if owner:
            bucket = impacted_recipes if owner in recipe_pages else impacted
            bucket.setdefault(owner, []).append(span)

    old_symbol_ids = {str(item.get("id") or "") for item in old_symbols if isinstance(item, dict)}
    new_symbol_ids = {str(item.get("id") or "") for item in new_symbols if isinstance(item, dict)}
    additions = bool(content_changed) or any(item.get("status") == "added" for item in changed_file_records) or bool(new_symbol_ids - old_symbol_ids)
    derived_changes = [item for item in changed if item.get("derived_changed")]
    impact = {
        "sources": sorted(affected_sources),
        "version_changed_sources": sorted(str(item.get("id")) for item in changed if item.get("version_changed")),
        "derived_changed_sources": sorted(str(item.get("id")) for item in changed if item.get("derived_changed")),
        "changed_files": sorted({str(item.get("path")) for item in changed_file_records}),
        "changed_file_records": sorted(changed_file_records, key=lambda item: (str(item.get("source")), str(item.get("path")), str(item.get("status")))),
        "changed_symbols": changed_symbols,
        "impacted_pages": sorted(impacted),
        "impacted_recipes": sorted(impacted_recipes),
        "new_content_discovered": additions,
        "targeted_recompile_required": bool(impacted) or bool(impacted_recipes) or additions or bool(derived_changes),
        "extraction_required": additions or bool(derived_changes),
    }
    previous_impact = read_json(vault / "state" / "impact.json", {})
    if isinstance(previous_impact, dict) and previous_impact.get("targeted_recompile_required"):
        for key in (
            "sources",
            "version_changed_sources",
            "derived_changed_sources",
            "changed_files",
            "changed_symbols",
            "impacted_pages",
            "impacted_recipes",
        ):
            impact[key] = sorted({str(value) for value in previous_impact.get(key, [])} | {str(value) for value in impact.get(key, [])})
        records = [
            item
            for item in [*previous_impact.get("changed_file_records", []), *impact.get("changed_file_records", [])]
            if isinstance(item, dict)
        ]
        impact["changed_file_records"] = sorted(
            {json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in records}.values(),
            key=lambda item: (str(item.get("source")), str(item.get("path")), str(item.get("status"))),
        )
        for key in ("new_content_discovered", "targeted_recompile_required", "extraction_required"):
            impact[key] = bool(previous_impact.get(key)) or bool(impact.get(key))
    write_json(vault / "state" / "impact.json", impact)
    latest = _latest_registry(vault)
    stale_records: list[dict[str, Any]] = []
    for page, spans in sorted(impacted.items()):
        source_ids = sorted({str(span.get("source") or "") for span in spans if span.get("source")})
        stale_records.append(
            {
                "kind": "stale-source",
                "page": page,
                "sources": source_ids,
                "required_sources": [
                    {
                        "id": source_id,
                        "snapshot": latest.get(source_id, {}).get("snapshot"),
                        "sha256": latest.get(source_id, {}).get("sha256"),
                        "commit": latest.get(source_id, {}).get("commit"),
                    }
                    for source_id in source_ids
                ],
                "affected_spans": spans,
            }
        )
    if stale_records:
        errors_path = vault / "state" / "errors.jsonl"
        error_records = read_jsonl(errors_path)
        seen = {
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in error_records
        }
        error_records.extend(
            item
            for item in stale_records
            if json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) not in seen
        )
        atomic_write_text(
            errors_path,
            "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in error_records),
        )
    result["impact"] = impact
    result["index"] = {"stale": True, "reason": "source change processing is not committed yet"}
    return result


def _cmd_update(args: argparse.Namespace) -> Any:
    vault = _vault(args)
    pending_path = vault / "state" / "pending-update.json"
    pending = read_json(pending_path, {})
    if isinstance(pending, dict) and pending.get("operation") not in {None, "update"}:
        pending_path.unlink(missing_ok=True)
    recovered = _recover_pending_update(vault, pending_path)
    old_latest = _latest_registry(vault)
    old_files = read_jsonl(vault / "code" / "files.jsonl")
    old_symbols = read_jsonl(vault / "code" / "symbols.jsonl")
    prepared = {
        "schema_version": 1,
        "status": "prepared",
        "operation": "update",
        "old_latest": old_latest,
        "old_files": old_files,
        "old_symbols": old_symbols,
    }
    write_json(pending_path, prepared)
    try:
        refreshed = refresh_sources(vault)
    except BaseException:
        if _latest_registry(vault) == old_latest:
            pending_path.unlink(missing_ok=True)
        raise
    write_json(pending_path, {**prepared, "status": "sources-written", "reports": refreshed})
    result = _process_source_changes(vault, refreshed, old_files, old_symbols, force=args.force)
    pending_path.unlink(missing_ok=True)
    result["index"] = _build_index_if_stable(vault)
    if recovered:
        result["recovered_update"] = recovered
        if not result.get("impact") and recovered.get("impact"):
            result["impact"] = recovered["impact"]
        result["changed"] = int(result.get("changed", 0)) + int(recovered.get("changed", 0))
    result["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    append_jsonl(vault / "state" / "update-log.jsonl", result)
    return result


def _runtime_skill(vault: Path) -> Path:
    diagnostics = evaluate(vault)
    write_json(vault / "state" / "diagnostics.json", diagnostics)
    if not diagnostics.get("healthy", False):
        raise ValueError("cannot install a runtime skill from an unhealthy vault; run doctor/eval and repair it first")
    for name in ("ROUTER.md", "INDEX.md"):
        if not (vault / "wiki" / name).is_file():
            raise ValueError(f"cannot install a runtime skill before synthesis publishes wiki/{name}")
    factual_provenance = [
        item
        for item in read_jsonl(vault / "state" / "provenance.jsonl")
        if isinstance(item, dict)
        and str(item.get("page") or "") not in {"ROUTER.md", "INDEX.md"}
        and (vault / "wiki" / Path(*str(item.get("page") or "").replace("\\", "/").removeprefix("wiki/").split("/"))).is_file()
    ]
    if not factual_provenance:
        raise ValueError("cannot install a runtime skill before a source-backed factual page is published")
    return generate_domain_skill(vault)


def _cmd_install_skill(args: argparse.Namespace) -> Any:
    generated = _runtime_skill(_vault(args))
    target_root = Path(args.target) if args.target else _install_dir(args.agent)
    return {"installed": str(_copy_skill(generated, target_root))}


def _cmd_apply_research(args: argparse.Namespace) -> Any:
    vault = _vault(args)
    manifest, bundle = validate_research_manifest(vault, Path(args.output))
    sources = [str(item["url"]) for item in manifest["sources"]]

    def clean(value: str) -> str:
        return redact_secrets(value)[0]

    sanitized_sources = [
        {
            key: ([clean(str(part)) for part in value] if key == "covers" else clean(str(value)))
            for key, value in item.items()
        }
        for item in manifest["sources"]
    ]
    sanitized_coverage = [
        {
            key: ([clean(str(part)) for part in value] if key == "queries" else clean(str(value)))
            for key, value in item.items()
        }
        for item in manifest["coverage"]
    ]
    metadata = [
        {
            "discovery": {
                "task_id": manifest["task_id"],
                **{key: value for key, value in item.items() if key != "url"},
            }
        }
        for item in sanitized_sources
    ]
    result = _add_to_vault(vault, sources, metadata)
    for item, record in zip(sanitized_sources, result.get("sources", []), strict=False):
        item["url"] = str(record.get("uri") or item["url"])
    sanitized_manifest = {
        **manifest,
        "queries": [clean(value) for value in manifest["queries"]],
        "coverage": sanitized_coverage,
        "sources": sanitized_sources,
        "gaps": [clean(value) for value in manifest["gaps"]],
    }
    applied = {
        "schema_version": 1,
        "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "manifest": sanitized_manifest,
        "source_ids": [str(item.get("id") or "") for item in result.get("sources", [])],
    }
    write_json(bundle / "APPLIED.json", applied)
    result["research"] = {
        "task": manifest["task_id"],
        "queries": sanitized_manifest["queries"],
        "coverage": sanitized_manifest["coverage"],
        "gaps": sanitized_manifest["gaps"],
        "applied": str(bundle / "APPLIED.json"),
    }
    return result


def _prepare_agents_block(path: Path, start: str, end: str, block: str) -> bytes:
    if path.is_symlink():
        raise ValueError(f"AGENTS.md must not be a link: {path}")
    raw = path.read_bytes() if path.is_file() else b""
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    current = raw[len(bom):].decode("utf-8")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    managed = block.replace("\n", newline)
    starts, ends = current.count(start), current.count(end)
    if starts != ends or starts > 1:
        raise ValueError(f"malformed managed expertise block in {path}")
    if starts:
        updated = re.sub(
            re.escape(start) + r".*?" + re.escape(end),
            lambda _match: managed,
            current,
            count=1,
            flags=re.DOTALL,
        )
    else:
        separator = "" if not current else newline if current.endswith(newline) else newline * 2
        if current.endswith(newline * 2):
            separator = ""
        updated = current + separator + managed
    if not updated.endswith(("\n", "\r")):
        updated += newline
    return bom + updated.encode("utf-8")


def _remove_install_target(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _cmd_install_harness(args: argparse.Namespace) -> Any:
    vault = _vault(args)
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        raise FileNotFoundError(f"project directory not found: {project}")
    generated = _runtime_skill(vault)
    config = read_json(vault / "vault.json", {})
    domain = str(config.get("name") or vault.name)
    skill_match = re.search(r"^name:\s*([a-z0-9-]+)\s*$", (generated / "SKILL.md").read_text(encoding="utf-8"), re.MULTILINE)
    if not skill_match:
        raise ValueError("generated runtime skill has no valid name")
    skill_name = skill_match.group(1)
    agents_path = _safe_child(project, "AGENTS.md")
    start = f"<!-- expertise-compiler:{domain}:start -->"
    end = f"<!-- expertise-compiler:{domain}:end -->"
    block = (
        f"{start}\n"
        f"## Mandatory {domain} Wiki workflow\n\n"
        f"For every user task in this repository, gather a concise evidence pack from the {domain} expertise vault before making a plan, code change, review finding, or final repository decision. "
        "Gather it yourself or, when the current Codex host supports delegation, use an available subagent. The active agent chooses whether to delegate and is solely responsible for every subagent type, name, model, reasoning level, and lifecycle; do not require or assume a particular subagent configuration.\n\n"
        "The evidence pack must include freshness and version, relevant Wiki routes, verified source paths and ranges, conflicts, and missing evidence. "
        "If the vault is stale, unhealthy, conflicting, or incomplete, disclose and repair that condition instead of substituting model memory.\n\n"
        f"Follow the project skill `${skill_name}` and use the vault at `{vault_reference(vault)}` relative to the workspace root. Treat Wiki pages as navigation and immutable source spans as proof.\n"
        f"{end}"
    )

    skills_root = _safe_child(project, ".agents/skills")
    installed_skill = skills_root / skill_name
    harness_lock = project / ".expertise-compiler-harness"
    with _file_lock(harness_lock, timeout=30.0):
        agents_bytes = _prepare_agents_block(agents_path, start, end, block)
        agents_before = agents_path.read_bytes() if agents_path.is_file() else None
        with tempfile.TemporaryDirectory(prefix="expertise-harness-backup-") as temporary:
            skill_backup = Path(temporary) / skill_name
            skill_existed = installed_skill.exists()
            if skill_existed:
                if installed_skill.is_symlink() or not installed_skill.is_dir():
                    raise ValueError(f"skill install target must be a regular directory: {installed_skill}")
                shutil.copytree(installed_skill, skill_backup)
            try:
                installed_skill = _copy_skill(generated, skills_root)
                atomic_write_bytes(agents_path, agents_bytes)
            except Exception as exc:
                rollback_errors: list[str] = []
                try:
                    _remove_install_target(installed_skill)
                    if skill_existed:
                        _copy_tree(skill_backup, installed_skill)
                except Exception as rollback_exc:
                    rollback_errors.append(f"skill: {rollback_exc}")
                try:
                    if agents_before is None:
                        agents_path.unlink(missing_ok=True)
                    else:
                        atomic_write_bytes(agents_path, agents_before)
                except Exception as rollback_exc:
                    rollback_errors.append(f"AGENTS.md: {rollback_exc}")
                if rollback_errors:
                    raise RuntimeError(f"harness install failed ({exc}); rollback failed: {'; '.join(rollback_errors)}") from exc
                raise
    return {
        "agents_md": str(agents_path),
        "installed_skill": str(installed_skill),
        "activation": "new Codex thread",
    }


def _cmd_install_builder(args: argparse.Namespace) -> Any:
    source = Path(__file__).resolve().parents[2] / "skills" / "expertise-compiler"
    if not source.is_dir():
        source = Path(sys.prefix) / "share" / "expertise-compiler" / "skills" / "expertise-compiler"
    if not source.is_dir():
        source = Path(args.plugin_root).resolve() / "skills" / "expertise-compiler"
    if not source.is_dir():
        raise FileNotFoundError("builder skill not found; pass --plugin-root")
    target_root = Path(args.target) if args.target else _install_dir(args.agent)
    return {"installed": str(_copy_skill(source, target_root))}


def _copy_tree(source: Path, target: Path) -> Path:
    """Copy a directory tree into target (atomic staging + backup)."""
    source = Path(source).expanduser().resolve()
    target_root = Path(target).parent.expanduser().resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    if source == target or source in target.parents or target in source.parents:
        raise ValueError(f"source and target overlap: {source} -> {target}")
    if target.exists() and (target.is_symlink() or target.resolve() != target.absolute()):
        raise ValueError(f"target must not be a link: {target}")

    staging_parent = Path(tempfile.mkdtemp(prefix=f".{target.name}-install-", dir=target_root))
    backup_parent: Path | None = None
    staged = staging_parent / target.name
    try:
        shutil.copytree(source, staged)
        if target.exists():
            backup_parent = Path(tempfile.mkdtemp(prefix=f".{target.name}-backup-", dir=target_root))
            os.replace(target, backup_parent / target.name)
        try:
            os.replace(staged, target)
        except Exception:
            if backup_parent is not None and (backup_parent / target.name).exists() and not target.exists():
                os.replace(backup_parent / target.name, target)
            raise
        if backup_parent is not None:
            shutil.rmtree(backup_parent)
            backup_parent = None
        return target
    finally:
        if staging_parent.exists():
            shutil.rmtree(staging_parent)
        if backup_parent is not None and backup_parent.exists() and not (backup_parent / target.name).exists():
            shutil.rmtree(backup_parent)


def _hermes_plugins_dir() -> Path:
    home = Path.home()
    env = os.environ.get("HERMES_HOME")
    base = Path(env).expanduser().resolve() if env else home / ".hermes"
    return base / "plugins"


def _cmd_install_hermes_plugin(args: argparse.Namespace) -> Any:
    """Install expertise-compiler as a native Hermes plugin.

    Copies the ``.hermes-plugin/`` directory tree *and* the builder skill
    into ``$HERMES_HOME/plugins/expertise-compiler/`` so the plugin is
    self-contained and Hermes auto-discovers it on next start. The plugin
    registers the builder skill as ``expertise-compiler:expertise-compiler``
    (explicit-load only).
    """
    root = Path(__file__).resolve().parents[2]
    plugin_source = root / ".hermes-plugin"
    if not plugin_source.is_dir():
        plugin_source = Path(sys.prefix) / "share" / "expertise-compiler" / ".hermes-plugin"
    if not plugin_source.is_dir():
        plugin_source = Path(args.plugin_root).resolve() / ".hermes-plugin"
    if not plugin_source.is_dir():
        raise FileNotFoundError("hermes plugin source not found; pass --plugin-root")
    if not (plugin_source / "plugin.yaml").is_file():
        raise FileNotFoundError(f"plugin.yaml not found in {plugin_source}")

    skill_source = root / "skills" / "expertise-compiler"
    if not skill_source.is_dir():
        skill_source = Path(sys.prefix) / "share" / "expertise-compiler" / "skills" / "expertise-compiler"
    if not skill_source.is_dir():
        skill_source = Path(args.plugin_root).resolve() / "skills" / "expertise-compiler"
    if not skill_source.is_dir():
        raise FileNotFoundError("builder skill not found; pass --plugin-root")

    target_root = Path(args.target) if args.target else _hermes_plugins_dir()
    target = target_root / "expertise-compiler"
    installed = _copy_tree(plugin_source, target)
    # Copy the builder skill into the plugin tree so __init__.py finds it.
    skill_target = target / "expertise-compiler"
    if skill_target.exists():
        shutil.rmtree(skill_target)
    shutil.copytree(skill_source, skill_target)
    return {"installed": str(installed), "skill": str(skill_target)}


def _cmd_read_page(args: argparse.Namespace) -> str:
    if (_vault(args) / "state" / "publish-journal.json").is_file():
        raise RuntimeError("expertise vault has an interrupted publication; rerun expertctl apply-build to recover")
    value = args.page.replace("\\", "/")
    if value.startswith("wiki/"):
        value = value.removeprefix("wiki/")
    page = _safe_child(_vault(args) / "wiki", value)
    return page.read_text(encoding="utf-8")


def _cmd_read_source(args: argparse.Namespace) -> str:
    value = args.path.replace("\\", "/")
    if value.startswith("sources/"):
        value = value.removeprefix("sources/")
    vault = _vault(args)
    source = _safe_child(vault / "sources", value)
    if not source.is_file():
        requested = PurePosixPath("sources") / PurePosixPath(value)
        for entry in reversed([item for item in read_jsonl(vault / "sources" / "registry.jsonl") if isinstance(item, dict)]):
            raw_path = PurePosixPath(str(entry.get("raw_path") or "").replace("\\", "/"))
            if not raw_path.parts or requested.parts[: len(raw_path.parts)] != raw_path.parts:
                continue
            relative = PurePosixPath(*requested.parts[len(raw_path.parts) :])
            resolved = workspace_reference_path(vault, entry, relative)
            if resolved is not None:
                source = resolved
                break
    if source.suffix.casefold() == ".pdf":
        raise ValueError("binary PDF cannot be read as lines; install a document converter and re-ingest it")
    text, _ = redact_secrets(source.read_text(encoding="utf-8", errors="replace"))
    lines = text.splitlines()
    start = max(1, args.start or 1)
    end = min(len(lines), args.end or len(lines))
    if end < start:
        raise ValueError("--end must be greater than or equal to --start")
    return "\n".join(f"{number}: {lines[number - 1]}" for number in range(start, end + 1))


def _cmd_eval(args: argparse.Namespace) -> Any:
    report = evaluate(_vault(args))
    write_json(_vault(args) / "state" / "diagnostics.json", report)
    checks = report.get("checks", [])
    passed = sum(1 for check in checks if check.get("ok"))
    return {
        "passed": passed,
        "total": len(checks),
        "healthy": report.get("healthy", False),
        "checks": checks,
        "diagnostic_pass_rate": report.get("diagnostic_pass_rate"),
        "diagnostics_passed": report.get("diagnostics_passed"),
        "diagnostics_total": report.get("diagnostics_total"),
        "diagnostics": report.get("diagnostics", []),
    }


def _cmd_doctor(args: argparse.Namespace) -> Any:
    report = doctor(_vault(args))
    write_json(_vault(args) / "state" / "diagnostics.json", report)
    return report


def _cmd_rebase_workspace_reference(args: argparse.Namespace) -> Any:
    """Accept deterministic thin-vault metadata changes without changing facts."""
    vault = _vault(args)
    config = load_config(vault)
    if config.get("source_storage") != "workspace-reference":
        raise ValueError("rebase-workspace-reference requires a workspace-reference vault")
    impact = read_json(vault / "state" / "impact.json", {})
    if isinstance(impact, dict) and impact:
        changed_sources = {
            str(item.get("source") or "")
            for item in impact.get("changed_file_records", [])
            if isinstance(item, dict) and item.get("source")
        }
        cited_sources = {
            str(span.get("source") or span.get("source_id") or "")
            for item in read_jsonl(vault / "state" / "provenance.jsonl")
            if isinstance(item, dict)
            for span in [item.get("source_span")]
            if isinstance(span, dict)
        }
        if (
            not changed_sources
            or changed_sources & cited_sources
            or impact.get("impacted_pages")
            or impact.get("impacted_recipes")
        ):
            raise ValueError("workspace-reference impact requires an evidence rebuild")
        write_json(vault / "state" / "impact.json", {})
        atomic_write_text(vault / "state" / "errors.jsonl", "")
    report = doctor(vault)
    failures = [
        item
        for item in report.get("checks", [])
        if not item.get("ok") and item.get("name") != "publication integrity"
    ]
    if failures:
        raise ValueError(f"cannot rebase an unhealthy workspace-reference vault: {failures[0].get('name')}")
    current = read_json(vault / "state" / "publication.json", {})
    expected = _publication_manifest(vault)
    if not isinstance(current, dict):
        raise ValueError("published manifest is missing or invalid")
    for field in ("wiki", "state"):
        before = dict(current.get(field, {}))
        after = dict(expected.get(field, {}))
        if field == "wiki":
            for navigation in ("INDEX.md", "ROUTER.md"):
                before.pop(navigation, None)
                after.pop(navigation, None)
        if before != after:
            raise ValueError(f"cannot rebase: published {field} differs beyond deterministic reference metadata")
    write_json(vault / "state" / "publication.json", expected)
    return {"rebased": True, "sources": len(expected.get("sources", {})), "wiki_pages": len(expected.get("wiki", {}))}


def _add_domain(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("domain")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="expertctl", description="Compile local sources into agent expertise")
    parser.add_argument("--workspace", default=".", help="workspace containing .expertise (default: current directory)")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("init", help="create a vault")
    _add_domain(command)
    command.add_argument("--goal-file")
    command.set_defaults(run=_cmd_init)

    command = sub.add_parser("add", help="snapshot local, Git, or web sources")
    _add_domain(command)
    command.add_argument("sources", nargs="+")
    command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(run=_cmd_add)

    command = sub.add_parser("research-plan", help="create an Internet source-discovery task")
    _add_domain(command)
    command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(run=lambda a: {"task": str(research_plan(_vault(a)))})

    command = sub.add_parser("apply-research", help="validate and snapshot a discovered source manifest")
    _add_domain(command)
    command.add_argument("output")
    command.set_defaults(run=_cmd_apply_research)

    for name, help_text, handler in (
        ("scan", "build deterministic inventory", _cmd_scan),
        ("hydrate", "materialize workspace-reference sources before extending a thin vault", lambda a: materialize_workspace_references(_vault(a))),
        ("migrate-workspace-paths", "replace host-specific paths in a thin vault", lambda a: migrate_workspace_paths(_vault(a))),
        ("status", "show vault status", lambda a: status(_vault(a))),
        ("doctor", "validate vault integrity", _cmd_doctor),
        ("rebase-workspace-reference", "accept verified thin-vault metadata", _cmd_rebase_workspace_reference),
        ("compile-plan", "create an agent task bundle", lambda a: {"task": str(compile_plan(_vault(a)))}),
        ("repair-plan", "create a targeted repair bundle", lambda a: {"task": str(repair_plan(_vault(a)))}),
        ("eval", "run deterministic checks", _cmd_eval),
    ):
        command = sub.add_parser(name, help=help_text)
        _add_domain(command)
        command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
        command.set_defaults(run=handler)

    command = sub.add_parser("apply-build", help="validate and publish an agent-produced build")
    _add_domain(command)
    command.add_argument("output")
    command.set_defaults(run=lambda a: apply_build(_vault(a), Path(a.output)))

    command = sub.add_parser("search", help="search pages and symbols")
    _add_domain(command)
    command.add_argument("query")
    command.add_argument("--limit", type=int, default=10)
    command.add_argument("--kind")
    command.add_argument("--version")
    command.add_argument("--authority")
    command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(run=_cmd_search)

    command = sub.add_parser("symbol", aliases=["definitions"], help="look up exact symbols")
    _add_domain(command)
    command.add_argument("name")
    command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(run=lambda a: symbol(_vault(a), a.name))

    command = sub.add_parser("neighbors", help="traverse one graph hop")
    _add_domain(command)
    command.add_argument("node")
    command.add_argument("--direction", choices=("in", "out", "both"), default="both")
    command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(run=lambda a: neighbors(_vault(a), a.node, a.direction))

    for name, help_text, handler in (
        ("references", "find structural references to a symbol", references),
        ("callers", "find approximate callers of a symbol", callers),
    ):
        command = sub.add_parser(name, help=help_text)
        _add_domain(command)
        command.add_argument("name")
        command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
        command.set_defaults(run=lambda a, handler=handler: handler(_vault(a), a.name))

    command = sub.add_parser("path", help="find a graph path")
    _add_domain(command)
    command.add_argument("start")
    command.add_argument("end")
    command.add_argument("--max-depth", type=int, default=6)
    command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(run=lambda a: {"path": find_path(_vault(a), a.start, a.end, a.max_depth)})

    command = sub.add_parser("context", help="build a vectorless evidence pack")
    _add_domain(command)
    command.add_argument("query")
    command.add_argument("--budget", type=int, default=8000)
    command.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    command.set_defaults(run=_cmd_context)

    command = sub.add_parser("read-page", help="read one Wiki page")
    _add_domain(command)
    command.add_argument("page")
    command.set_defaults(run=_cmd_read_page, raw=True)

    command = sub.add_parser("read-source", help="read a narrow source range")
    _add_domain(command)
    command.add_argument("path")
    command.add_argument("--start", type=int)
    command.add_argument("--end", type=int)
    command.set_defaults(run=_cmd_read_source, raw=True)

    command = sub.add_parser("update", help="refresh sources and rebuild changed state")
    _add_domain(command)
    command.add_argument("--force", action="store_true")
    command.set_defaults(run=_cmd_update)

    command = sub.add_parser("install-skill", help="generate and install the domain runtime skill")
    _add_domain(command)
    command.add_argument("--agent", choices=("codex", "claude", "hermes"), required=True)
    command.add_argument("--target")
    command.set_defaults(run=_cmd_install_skill)

    command = sub.add_parser("install-harness", help="install a project runtime skill and AGENTS.md evidence workflow")
    _add_domain(command)
    command.add_argument("--project", default=".")
    command.set_defaults(run=_cmd_install_harness)

    command = sub.add_parser("install-builder-skill", help="install the builder skill")
    command.add_argument("--agent", choices=("codex", "claude", "hermes"), required=True)
    command.add_argument("--target")
    command.add_argument("--plugin-root", default=".")
    command.set_defaults(run=_cmd_install_builder)

    command = sub.add_parser("install-hermes-plugin", help="install as a native Hermes plugin")
    command.add_argument("--target")
    command.add_argument("--plugin-root", default=".")
    command.set_defaults(run=_cmd_install_hermes_plugin)

    command = sub.add_parser("record-recipe", help="promote verified work into the vault")
    _add_domain(command)
    command.add_argument("recipe")
    command.set_defaults(run=lambda a: {"recipe": str(record_recipe(_vault(a), Path(a.recipe)))})

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = _build_parser().parse_args(argv)
    try:
        mutating = {
            "add",
            "scan",
            "migrate-workspace-paths",
            "doctor",
            "rebase-workspace-reference",
            "eval",
            "compile-plan",
            "research-plan",
            "apply-research",
            "repair-plan",
            "apply-build",
            "update",
            "install-skill",
            "install-harness",
            "record-recipe",
        }
        if args.command in mutating:
            with _file_lock(_vault(args) / "state" / "vault-mutation", timeout=300.0):
                result = args.run(args)
        else:
            result = args.run(args)
        _emit(result, getattr(args, "raw", False) is False)
        if args.command in {"doctor", "eval"} and isinstance(result, dict) and not result.get("healthy", False):
            return 1
        if args.command == "update" and isinstance(result, dict) and any(
            item.get("status") == "error" for item in result.get("sources", []) if isinstance(item, dict)
        ):
            return 1
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"expertctl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
