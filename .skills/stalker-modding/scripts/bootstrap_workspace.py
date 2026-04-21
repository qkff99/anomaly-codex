#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _skill_common import REPO_ROOT
from graphify_workspace import build_index, build_lua_map, build_workspace_submaps, discover_workspace_submap_targets
from luac_tool import detect_compiler
from patch_graphify_for_stalker import patch_graphify_for_stalker, patch_status


SCRIPT_DIR = Path(__file__).resolve().parent
BOOTSTRAP_STATE_VERSION = 2
BOOTSTRAP_STATE_PATH = REPO_ROOT / ".codex-stalker" / "state" / "bootstrap_state.json"
LUA_GRAPH_ROOT = REPO_ROOT / "ai_workspace"
LUA_GRAPH_OUTPUT_NAME = "lua-graphify-out"
LUA_GRAPH_JSON = LUA_GRAPH_ROOT / LUA_GRAPH_OUTPUT_NAME / "graph.json"
MAP_INDEX_PATH = LUA_GRAPH_ROOT / "map_index.html"


def ensure_python_package(module_name: str, package_name: str) -> tuple[bool, str]:
    if importlib.util.find_spec(module_name) is not None:
        return True, f"{package_name} available"

    commands: list[list[str]] = [
        [sys.executable, "-m", "pip", "install", package_name],
    ]
    if sys.platform != "win32":
        commands.append([sys.executable, "-m", "pip", "install", package_name, "--break-system-packages"])

    outputs: list[str] = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        if output:
            outputs.append(output)
        if completed.returncode == 0 and importlib.util.find_spec(module_name) is not None:
            return True, f"{package_name} installed"

    return False, "\n".join(outputs) if outputs else f"failed to install {package_name}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repo-local readiness checks for the STALKER modding workbench.")
    parser.add_argument(
        "--run-regressions",
        action="store_true",
        help="After the quick readiness checks, run run_regressions.py --suite all.",
    )
    parser.add_argument(
        "--skip-lua-graph",
        action="store_true",
        help="Skip building or refreshing ai_workspace graph artifacts during bootstrap.",
    )
    parser.add_argument(
        "--force-lua-graph",
        action="store_true",
        help="Rebuild ai_workspace graph artifacts even if bootstrap state already says they are ready.",
    )
    return parser.parse_args()


def run_check(label: str, command: list[str]) -> tuple[bool, str]:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode == 0:
        print(f"[ok] {label}")
    else:
        print(f"[fail] {label}")
    if output.strip():
        print(output.strip())
    return completed.returncode == 0, output


def verify_mcp_alignment() -> tuple[bool, str]:
    plugin_mcp = REPO_ROOT / "plugins" / "stalker-modding-workbench" / ".mcp.json"
    vscode_mcp = REPO_ROOT / ".vscode" / "mcp.json"
    if not plugin_mcp.exists():
        return False, f"missing plugin MCP config: {plugin_mcp}"
    if not vscode_mcp.exists():
        return False, f"missing VS Code MCP config: {vscode_mcp}"

    plugin_data = json.loads(plugin_mcp.read_text(encoding="utf-8"))
    vscode_data = json.loads(vscode_mcp.read_text(encoding="utf-8"))
    if plugin_data != vscode_data:
        return False, ".vscode/mcp.json does not match plugins/stalker-modding-workbench/.mcp.json"
    return True, "MCP configs aligned"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_bootstrap_state() -> dict[str, Any]:
    try:
        return json.loads(BOOTSTRAP_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_bootstrap_state(state: dict[str, Any]) -> None:
    BOOTSTRAP_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _collect_submap_state() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for target in discover_workspace_submap_targets(LUA_GRAPH_ROOT):
        output_dir = target.root / target.output_name
        graph_json = output_dir / "graph.json"
        folder_map = output_dir / "folder_map.html"
        if not graph_json.exists():
            continue
        entry: dict[str, Any] = {
            "root": _repo_rel(target.root),
            "output_name": target.output_name,
            "graph_json": _repo_rel(graph_json),
            "folder_map": _repo_rel(folder_map) if folder_map.exists() else None,
        }
        folder_map_json = output_dir / "folder_map.json"
        if folder_map_json.exists():
            try:
                summary = json.loads(folder_map_json.read_text(encoding="utf-8"))
            except Exception:
                summary = {}
            for key in ("lua_files", "graph_nodes", "graph_edges", "communities", "wiki_articles"):
                if key in summary:
                    entry[key] = summary[key]
        entries.append(entry)
    return entries


def _graph_artifacts_ready(state: dict[str, Any]) -> bool:
    lua_graph = state.get("lua_graph", {})
    if state.get("version") != BOOTSTRAP_STATE_VERSION:
        return False
    if not (lua_graph.get("ready") and LUA_GRAPH_JSON.exists() and MAP_INDEX_PATH.exists()):
        return False
    expected_roots = {_repo_rel(target.root) for target in discover_workspace_submap_targets(LUA_GRAPH_ROOT)}
    state_roots = {entry.get("root", "") for entry in state.get("submaps", [])}
    if expected_roots != state_roots:
        return False
    return all((REPO_ROOT / entry["graph_json"]).exists() for entry in state.get("submaps", []))


def ensure_graph_artifacts(force: bool) -> tuple[bool, str, dict[str, Any] | None, list[dict[str, Any]]]:
    if not force and LUA_GRAPH_JSON.exists() and MAP_INDEX_PATH.exists():
        submaps = _collect_submap_state()
        expected_roots = {_repo_rel(target.root) for target in discover_workspace_submap_targets(LUA_GRAPH_ROOT)}
        if {entry["root"] for entry in submaps} == expected_roots:
            print("[ok] workspace graph artifacts available")
            return True, "workspace graph artifacts available", {
                "ready": True,
                "root": "ai_workspace",
                "output_name": LUA_GRAPH_OUTPUT_NAME,
                "graph_json": "ai_workspace/lua-graphify-out/graph.json",
                "map_index": "ai_workspace/map_index.html",
            }, submaps

    print("[run] building workspace graph artifacts")
    try:
        summary = build_lua_map(LUA_GRAPH_ROOT, LUA_GRAPH_OUTPUT_NAME)
        submaps = build_workspace_submaps(LUA_GRAPH_ROOT)
        build_index(LUA_GRAPH_ROOT)
    except Exception as exc:
        return False, str(exc), None, []

    return True, "workspace graph artifacts ready", {
        "ready": True,
        "root": "ai_workspace",
        "output_name": LUA_GRAPH_OUTPUT_NAME,
        "graph_json": "ai_workspace/lua-graphify-out/graph.json",
        "map_index": "ai_workspace/map_index.html",
        "lua_files": summary["lua_files"],
        "graph_nodes": summary["graph_nodes"],
        "graph_edges": summary["graph_edges"],
        "communities": summary["communities"],
        "wiki_articles": summary["wiki_articles"],
    }, submaps


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    previous_state = load_bootstrap_state()

    package_ok, package_message = ensure_python_package("graphify", "graphifyy")
    if package_ok:
        print(f"[ok] {package_message}")
    else:
        print("[fail] graphifyy bootstrap")
        if package_message.strip():
            print(package_message.strip())
        errors.append("graphifyy bootstrap")

    patch_applied = False
    patch_message = ""
    if package_ok:
        try:
            patch_applied, patch_message = patch_graphify_for_stalker()
            patch_state = patch_status()
            if all(patch_state.values()):
                print(f"[ok] {patch_message}")
            else:
                print("[fail] graphify .script patch incomplete")
                errors.append("graphify .script patch incomplete")
        except Exception as exc:
            print("[fail] graphify .script patch")
            print(str(exc))
            errors.append("graphify .script patch")
    else:
        patch_state = {}

    compiler = detect_compiler()
    if compiler is None:
        errors.append("luac compiler not detected")
    else:
        print(f"[ok] luac: {compiler.label} ({compiler.version or 'unknown version'})")

    aligned, message = verify_mcp_alignment()
    if aligned:
        print(f"[ok] {message}")
    else:
        print(f"[fail] {message}")
        errors.append(message)

    commands = [
        ("check_overlay", [sys.executable, str(SCRIPT_DIR / "check_overlay.py"), str(REPO_ROOT / ".codex-stalker" / "workspace.json")]),
        ("query_hints_mcm", [sys.executable, str(SCRIPT_DIR / "query_hints.py"), "mcm"]),
        ("query_hints_log", [sys.executable, str(SCRIPT_DIR / "query_hints.py"), "log"]),
        ("query_hints_fomod", [sys.executable, str(SCRIPT_DIR / "query_hints.py"), "fomod"]),
        ("query_hints_gamma", [sys.executable, str(SCRIPT_DIR / "query_hints.py"), "gamma"]),
        ("discover_refs_list", [sys.executable, str(SCRIPT_DIR / "discover_github_refs.py"), "list"]),
        ("scan_workspace", [sys.executable, str(SCRIPT_DIR / "scan_workspace.py"), str(REPO_ROOT)]),
    ]
    for label, command in commands:
        ok, _ = run_check(label, command)
        if not ok:
            errors.append(label)

    lua_graph_state: dict[str, Any] = {}
    submap_state: list[dict[str, Any]] = []
    if not args.skip_lua_graph and not errors:
        graph_force = args.force_lua_graph or not _graph_artifacts_ready(previous_state)
        graph_ok, graph_message, graph_state, current_submaps = ensure_graph_artifacts(force=graph_force)
        if graph_ok:
            print(f"[ok] {graph_message}")
            if graph_state is not None:
                graph_state["generated_at"] = _utc_now()
                lua_graph_state = graph_state
            for entry in current_submaps:
                entry["generated_at"] = _utc_now()
            submap_state = current_submaps
        else:
            print("[fail] workspace graph bootstrap")
            if graph_message.strip():
                print(graph_message.strip())
            errors.append("workspace graph bootstrap")
    elif args.skip_lua_graph:
        print("[ok] workspace graph bootstrap skipped")
        if LUA_GRAPH_JSON.exists() and MAP_INDEX_PATH.exists():
            lua_graph_state = {
                "ready": True,
                "root": "ai_workspace",
                "output_name": LUA_GRAPH_OUTPUT_NAME,
                "graph_json": "ai_workspace/lua-graphify-out/graph.json",
                "map_index": "ai_workspace/map_index.html",
                "generated_at": previous_state.get("lua_graph", {}).get("generated_at"),
            }
            submap_state = previous_state.get("submaps", [])

    if not errors and args.run_regressions:
        ok, _ = run_check(
            "run_regressions",
            [sys.executable, str(SCRIPT_DIR / "run_regressions.py"), "--suite", "all"],
        )
        if not ok:
            errors.append("run_regressions")

    if errors:
        print("bootstrap_workspace: failed")
        for error in errors:
            print(f"- {error}")
        return 1

    state = {
        "version": BOOTSTRAP_STATE_VERSION,
        "completed_at": _utc_now(),
        "graphify": {
            "package": package_message,
            "script_patch": patch_message,
            "patch_applied": patch_applied,
            "patch_state": patch_state,
        },
        "luac": {
            "label": compiler.label if compiler else None,
            "version": compiler.version if compiler else None,
        },
        "mcp_alignment": aligned,
        "lua_graph": lua_graph_state,
        "submaps": submap_state,
    }
    write_bootstrap_state(state)

    print(f"[ok] bootstrap state written: {BOOTSTRAP_STATE_PATH}")
    print("bootstrap_workspace: ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
