#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from _skill_common import REPO_ROOT
from luac_tool import detect_compiler


SCRIPT_DIR = Path(__file__).resolve().parent


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


def main() -> int:
    args = parse_args()
    errors: list[str] = []

    package_ok, package_message = ensure_python_package("graphify", "graphifyy")
    if package_ok:
        print(f"[ok] {package_message}")
    else:
        print(f"[fail] graphifyy bootstrap")
        if package_message.strip():
            print(package_message.strip())
        errors.append("graphifyy bootstrap")

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

    print("bootstrap_workspace: ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
