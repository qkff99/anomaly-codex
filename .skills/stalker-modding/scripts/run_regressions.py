#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from _skill_common import REPO_ROOT, load_json_file, read_text_auto


SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SCENARIOS_PATH = FIXTURES_DIR / "project_scenarios.json"
SUITE_ORDER = ("core", "logs", "localization", "project-toolchain", "distribution")


class RegressionFailure(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic repo-local regressions for the STALKER modding workbench.")
    parser.add_argument(
        "--suite",
        choices=(*SUITE_ORDER, "all"),
        default="all",
        help="Regression suite to run. Defaults to all.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser.parse_args()


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd or REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def require_success(completed: subprocess.CompletedProcess[str], *, label: str) -> str:
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()
    if completed.returncode != 0:
        raise RegressionFailure(f"{label} failed with exit {completed.returncode}: {output}")
    return output


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RegressionFailure(message)


def load_scenarios() -> dict[str, Any]:
    data = load_json_file(SCENARIOS_PATH)
    if not isinstance(data, dict):
        raise RegressionFailure(f"scenario file must contain an object: {SCENARIOS_PATH}")
    return data


def unique_project_name(prefix: str) -> str:
    return f"regression_{prefix}_{uuid.uuid4().hex[:8]}"


def project_root(name: str) -> Path:
    return REPO_ROOT / "projects" / name


def cleanup_project(name: str) -> None:
    shutil.rmtree(project_root(name), ignore_errors=True)


def script_path(name: str) -> str:
    return str(SCRIPT_DIR / name)


def python_cmd(script_name: str, *args: str) -> list[str]:
    return [sys.executable, script_path(script_name), *args]


def summarize_log(target: Path) -> dict[str, Any]:
    completed = run_command(python_cmd("log_triage.py", "summarize", str(target), "--json"))
    output = require_success(completed, label=f"log_triage summarize {target.name}")
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RegressionFailure(f"log_triage summarize did not emit valid JSON for {target}: {output}") from exc


def extract_log(target: Path, *, kind: str) -> str:
    completed = run_command(python_cmd("log_triage.py", "extract", str(target), "--kind", kind))
    return require_success(completed, label=f"log_triage extract {kind} {target.name}")


def read_project_metadata(name: str) -> dict[str, Any]:
    metadata_path = project_root(name) / ".codex-stalker" / "project.json"
    data = load_json_file(metadata_path)
    if not isinstance(data, dict):
        raise RegressionFailure(f"project metadata must be an object: {metadata_path}")
    return data


def run_core_suite() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    scenarios = load_scenarios()

    def case(name: str, fn: Callable[[], Any]) -> None:
        try:
            details = fn()
            results.append({"suite": "core", "name": name, "ok": True, "details": details})
        except Exception as exc:
            results.append({"suite": "core", "name": name, "ok": False, "details": str(exc)})

    def check_overlay() -> dict[str, Any]:
        completed = run_command(python_cmd("check_overlay.py", str(REPO_ROOT / ".codex-stalker" / "workspace.json")))
        output = require_success(completed, label="check_overlay")
        require("overlay: valid" in output, "check_overlay output did not confirm overlay validity")
        return {"overlay": ".codex-stalker/workspace.json"}

    def query_aliases() -> dict[str, Any]:
        aliases = scenarios.get("query_aliases", [])
        require(isinstance(aliases, list) and aliases, "query_aliases fixture must be a non-empty list")
        resolved: dict[str, str] = {}
        for alias in aliases:
            completed = run_command(python_cmd("query_hints.py", str(alias)))
            output = require_success(completed, label=f"query_hints {alias}")
            first_line = next((line for line in output.splitlines() if line.startswith("task_type: ")), "")
            require(first_line.startswith("task_type: "), f"query_hints did not return task_type for alias {alias}")
            resolved[str(alias)] = first_line.split(": ", 1)[1]
        return resolved

    def mcp_alignment() -> dict[str, Any]:
        plugin_path = REPO_ROOT / "plugins" / "stalker-modding-workbench" / ".mcp.json"
        vscode_path = REPO_ROOT / ".vscode" / "mcp.json"
        plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
        vscode = json.loads(vscode_path.read_text(encoding="utf-8"))
        require(plugin == vscode, "plugin .mcp.json and .vscode/mcp.json differ")
        servers = plugin.get("mcpServers", {})
        return {"entries": sorted(servers.keys()) if isinstance(servers, dict) else []}

    case("check_overlay", check_overlay)
    case("query_hints_aliases", query_aliases)
    case("mcp_alignment", mcp_alignment)
    return results


def run_logs_suite() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    fixtures = FIXTURES_DIR / "logs"
    temp_projects: list[str] = []

    def case(name: str, fn: Callable[[], Any]) -> None:
        try:
            details = fn()
            results.append({"suite": "logs", "name": name, "ok": True, "details": details})
        except Exception as exc:
            results.append({"suite": "logs", "name": name, "ok": False, "details": str(exc)})

    def runtime_summary() -> dict[str, Any]:
        summary = summarize_log(fixtures / "lua_runtime.log")
        require(summary["kind"] == "lua_runtime", f"expected lua_runtime, got {summary['kind']}")
        require("broken_table" in summary["headline"], "runtime headline did not preserve Lua error message")
        require(str(summary["source_file"]).lower().endswith("axr_main.script"), "runtime source_file mismatch")
        require(summary["line"] == 12, f"expected runtime line 12, got {summary['line']}")
        return {"headline": summary["headline"], "line": summary["line"]}

    def syntax_summary() -> dict[str, Any]:
        summary = summarize_log(fixtures / "lua_syntax.log")
        require(summary["kind"] == "lua_syntax", f"expected lua_syntax, got {summary['kind']}")
        require("unexpected symbol near '/'" in summary["headline"], "syntax headline mismatch")
        require(summary["line"] == 27, f"expected syntax line 27, got {summary['line']}")
        return {"headline": summary["headline"]}

    def engine_fatal_summary() -> dict[str, Any]:
        summary = summarize_log(fixtures / "engine_fatal.log")
        require(summary["kind"] == "engine_fatal", f"expected engine_fatal, got {summary['kind']}")
        inspect_points = summary.get("inspect_points", [])
        resolved = [point for point in inspect_points if point.get("local_path")]
        require(resolved, "engine fatal summary did not resolve any inspect points")
        target = next((point for point in resolved if str(point["local_path"]).replace("\\", "/").endswith("Layers/xrRenderDX10/dx10SH_Texture.cpp")), None)
        require(target is not None, "engine fatal summary did not resolve dx10SH_Texture.cpp inspect point")
        return {"resolved": target["local_path"], "line": target["line"]}

    def large_tail_summary() -> dict[str, Any]:
        template = (fixtures / "lua_runtime.log").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="stalker-codex-tail-") as temp_dir:
            target = Path(temp_dir) / "large_tail.log"
            prefix = ("[info] filler line for tail scan\n" * 5000)
            target.write_text(prefix + template, encoding="utf-8")
            summary = summarize_log(target)
        require(summary["kind"] == "lua_runtime", f"expected lua_runtime from large tail, got {summary['kind']}")
        require("broken_table" in summary["headline"], "large tail summary lost the Lua error headline")
        return {"headline": summary["headline"]}

    def local_lua_resolution() -> dict[str, Any]:
        project_name = unique_project_name("logs")
        temp_projects.append(project_name)
        require_success(run_command(python_cmd("init_project.py", "--name", project_name)), label="init_project logs fixture")
        require_success(
            run_command(python_cmd("scaffold_template.py", "--project", project_name, "--template", "lua_feature", "--script-name", "resolved_feature")),
            label="scaffold lua_feature for log resolution",
        )
        with tempfile.TemporaryDirectory(prefix="stalker-codex-log-") as temp_dir:
            target = Path(temp_dir) / "resolved_runtime.log"
            target.write_text(
                "\n".join(
                    [
                        "! [LUA] SCRIPT RUNTIME ERROR",
                        "! [LUA] E:\\Mods\\Sample\\bin\\..\\gamedata\\scripts\\resolved_feature.script:1: attempt to call global 'missing' (a nil value)",
                        "! [SCRIPT ERROR]: E:\\Mods\\Sample\\bin\\..\\gamedata\\scripts\\resolved_feature.script:1: attempt to call global 'missing' (a nil value)",
                        "stack traceback:",
                        "0- E:\\Mods\\Sample\\bin\\..\\gamedata\\scripts\\resolved_feature.script:1: in function 'on_game_start'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            summary = summarize_log(target)
        inspect_points = summary.get("inspect_points", [])
        resolved = next((point for point in inspect_points if point.get("local_path") and str(point["local_path"]).replace("\\", "/").endswith(f"projects/{project_name}/gamedata/scripts/resolved_feature.script")), None)
        require(resolved is not None, "lua inspect points did not resolve into the temporary project gamedata root")
        return {"resolved": resolved["local_path"], "line": resolved["line"]}

    def unresolved_lua_case() -> dict[str, Any]:
        summary = summarize_log(fixtures / "unresolved_lua_runtime.log")
        require(summary["kind"] == "lua_runtime", f"expected lua_runtime, got {summary['kind']}")
        inspect_points = summary.get("inspect_points", [])
        unresolved = [point for point in inspect_points if not point.get("local_path")]
        require(unresolved, "expected unresolved Lua inspect point for unknown source path")
        falsely_resolved = [point for point in inspect_points if point.get("local_path")]
        require(not falsely_resolved, f"unexpected false-positive resolution: {falsely_resolved}")
        return {"unresolved_points": len(unresolved)}

    def extract_runtime_block() -> dict[str, Any]:
        output = extract_log(fixtures / "lua_runtime.log", kind="lua_runtime")
        require("broken_table" in output, "extract did not return the runtime error block")
        require("stack traceback:" in output, "extract did not preserve traceback lines")
        return {"lines": len([line for line in output.splitlines() if line.strip()])}

    try:
        case("runtime_summary", runtime_summary)
        case("syntax_summary", syntax_summary)
        case("engine_fatal_summary", engine_fatal_summary)
        case("large_tail_summary", large_tail_summary)
        case("local_lua_resolution", local_lua_resolution)
        case("unresolved_lua_case", unresolved_lua_case)
        case("extract_runtime_block", extract_runtime_block)
        return results
    finally:
        for project_name in temp_projects:
            cleanup_project(project_name)


def run_localization_suite() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    fixtures = FIXTURES_DIR / "xml"

    def case(name: str, fn: Callable[[], Any]) -> None:
        try:
            details = fn()
            results.append({"suite": "localization", "name": name, "ok": True, "details": details})
        except Exception as exc:
            results.append({"suite": "localization", "name": name, "ok": False, "details": str(exc)})

    def inspect_utf8() -> dict[str, Any]:
        completed = run_command(python_cmd("xml_localization_tool.py", "inspect", str(fixtures / "localization_utf8.xml")))
        output = require_success(completed, label="xml inspect utf8")
        require("codec: utf-8" in output, "UTF-8 fixture was not detected as utf-8")
        require("is_localization_xml: yes" in output, "UTF-8 fixture was not recognized as localization XML")
        return {"codec": "utf-8"}

    def cp1251_roundtrip() -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="stalker-codex-xml-") as temp_dir:
            temp_root = Path(temp_dir)
            source = temp_root / "localization_cp1251.xml"
            state_dir = temp_root / "state"
            shutil.copy2(fixtures / "localization_cp1251.xml", source)
            original_bytes = source.read_bytes()

            output = require_success(
                run_command(python_cmd("xml_localization_tool.py", "inspect", str(source))),
                label="xml inspect cp1251",
            )
            require("codec: cp1251" in output, "cp1251 fixture was not detected as cp1251")

            require_success(
                run_command(python_cmd("xml_localization_tool.py", "prepare-edit", str(source), "--state-dir", str(state_dir))),
                label="xml prepare-edit cp1251",
            )
            prepared_text = source.read_text(encoding="utf-8")
            require('encoding="utf-8"' in prepared_text, "prepare-edit did not rewrite XML declaration to utf-8")

            require_success(
                run_command(python_cmd("xml_localization_tool.py", "finish-edit", str(source), "--state-dir", str(state_dir))),
                label="xml finish-edit cp1251",
            )
            restored_bytes = source.read_bytes()
            require(restored_bytes == original_bytes, "finish-edit did not restore the original cp1251 bytes")
            _, meta = read_text_auto(source, errors="strict")
            require(meta.get("codec") == "cp1251", f"restored XML codec mismatch: {meta.get('codec')}")
            return {"codec": meta.get("codec"), "bytes": len(restored_bytes)}

    case("inspect_utf8", inspect_utf8)
    case("cp1251_roundtrip", cp1251_roundtrip)
    return results


def run_project_toolchain_suite() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    scenarios = load_scenarios()
    scaffold_entries = scenarios.get("scaffold_templates", [])
    require(isinstance(scaffold_entries, list) and scaffold_entries, "scaffold_templates fixture must be a non-empty list")
    temp_projects: list[str] = []

    def case(name: str, fn: Callable[[], Any]) -> None:
        try:
            details = fn()
            results.append({"suite": "project-toolchain", "name": name, "ok": True, "details": details})
        except Exception as exc:
            results.append({"suite": "project-toolchain", "name": name, "ok": False, "details": str(exc)})

    def scaffold_validate_package() -> dict[str, Any]:
        project_name = unique_project_name("toolchain")
        temp_projects.append(project_name)
        require_success(run_command(python_cmd("init_project.py", "--name", project_name)), label="init_project toolchain")

        for entry in scaffold_entries:
            require(isinstance(entry, dict), f"invalid scaffold entry: {entry!r}")
            template = entry.get("template")
            extra_args = entry.get("args", [])
            require(isinstance(template, str), f"scaffold entry missing template: {entry!r}")
            require(isinstance(extra_args, list), f"scaffold entry args must be a list: {entry!r}")
            require_success(
                run_command(python_cmd("scaffold_template.py", "--project", project_name, "--template", template, *[str(item) for item in extra_args])),
                label=f"scaffold_template {template}",
            )

        require_success(run_command(python_cmd("validate_project.py", "--project", project_name)), label="validate_project")
        require_success(run_command(python_cmd("package_project.py", "--project", project_name)), label="package_project")

        metadata = read_project_metadata(project_name)
        templates = metadata.get("templates", [])
        require(isinstance(templates, list) and len(templates) == len(scaffold_entries), "project metadata did not record all scaffold templates")

        dist_root = project_root(project_name) / "dist" / project_name / "gamedata"
        require(dist_root.exists(), f"packaged gamedata root missing: {dist_root}")
        require((dist_root / "scripts" / "fixture_feature.script").exists(), "packaged lua_feature script missing")
        require((dist_root / "scripts" / "fixture_menu_mcm.script").exists(), "packaged lua_mcm menu script missing")
        require((dist_root / "configs" / f"mod_system_{project_name}.ltx").exists(), "packaged dltx file missing")
        require((dist_root / "configs" / "text" / "eng" / "ui_st_fixture_pack.xml").exists(), "packaged localization fixture missing")
        return {"templates": len(templates), "packaged": str(dist_root)}

    def import_mod_root() -> dict[str, Any]:
        project_name = unique_project_name("importmod")
        temp_projects.append(project_name)
        source = FIXTURES_DIR / "imports" / "mod_root"
        require_success(run_command(python_cmd("import_mod.py", "--source", str(source), "--name", project_name)), label="import_mod mod_root")
        metadata = read_project_metadata(project_name)
        source_meta = metadata.get("source", {})
        require(source_meta.get("kind") == "mod_root", "imported mod_root project metadata source.kind mismatch")
        require((project_root(project_name) / "README.txt").exists(), "mod_root import did not preserve top-level files")
        require_success(run_command(python_cmd("package_project.py", "--project", project_name)), label="package_project imported mod_root")
        dist_root = project_root(project_name) / "dist" / project_name
        require((dist_root / "gamedata" / "scripts" / "imported_feature.script").exists(), "packaged imported mod_root did not include gamedata payload")
        require(not (dist_root / "README.txt").exists(), "package_project should not copy non-gamedata top-level files from imported mod_root")
        return {"source_kind": source_meta.get("kind")}

    def import_gamedata_root() -> dict[str, Any]:
        project_name = unique_project_name("importdata")
        temp_projects.append(project_name)
        source = FIXTURES_DIR / "imports" / "gamedata_root" / "gamedata"
        require_success(run_command(python_cmd("import_mod.py", "--source", str(source), "--name", project_name)), label="import_mod gamedata_root")
        metadata = read_project_metadata(project_name)
        source_meta = metadata.get("source", {})
        require(source_meta.get("kind") == "gamedata_root", "imported gamedata_root project metadata source.kind mismatch")
        require((project_root(project_name) / "gamedata" / "scripts" / "imported_gamedata_feature.script").exists(), "gamedata_root import did not copy gamedata payload")
        return {"source_kind": source_meta.get("kind")}

    try:
        case("scaffold_validate_package", scaffold_validate_package)
        case("import_mod_root", import_mod_root)
        case("import_gamedata_root", import_gamedata_root)
        return results
    finally:
        for project_name in temp_projects:
            cleanup_project(project_name)


def run_distribution_suite() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    temp_projects: list[str] = []

    def case(name: str, fn: Callable[[], Any]) -> None:
        try:
            details = fn()
            results.append({"suite": "distribution", "name": name, "ok": True, "details": details})
        except Exception as exc:
            results.append({"suite": "distribution", "name": name, "ok": False, "details": str(exc)})

    def core_fomod_package() -> dict[str, Any]:
        project_name = unique_project_name("dist")
        temp_projects.append(project_name)
        require_success(run_command(python_cmd("init_project.py", "--name", project_name)), label="init_project distribution")
        require_success(
            run_command(python_cmd("scaffold_template.py", "--project", project_name, "--template", "lua_feature", "--script-name", "dist_feature")),
            label="scaffold distribution lua_feature",
        )
        require_success(run_command(python_cmd("package_project.py", "--project", project_name)), label="package_project distribution")
        require_success(
            run_command(
                python_cmd(
                    "fomod_tool.py",
                    "--project",
                    project_name,
                    "--module-name",
                    "Distribution Fixture",
                    "--author",
                    "Codex",
                    "--version",
                    "1.2.3",
                )
            ),
            label="fomod_tool",
        )
        dist_root = project_root(project_name) / "dist" / f"{project_name}-fomod"
        payload = dist_root / "00 Core" / "gamedata" / "scripts" / "dist_feature.script"
        info_xml = dist_root / "fomod" / "info.xml"
        module_config = dist_root / "fomod" / "ModuleConfig.xml"
        require(payload.exists(), f"FOMOD payload missing: {payload}")
        require(info_xml.exists(), f"FOMOD info.xml missing: {info_xml}")
        require(module_config.exists(), f"FOMOD ModuleConfig.xml missing: {module_config}")
        require("<moduleName>Distribution Fixture</moduleName>" in module_config.read_text(encoding="utf-8"), "ModuleConfig.xml missing moduleName")
        require('<folder source="00 Core" destination="" />' in module_config.read_text(encoding="utf-8"), "ModuleConfig.xml missing requiredInstallFiles core folder")
        return {"package_root": str(dist_root)}

    try:
        case("core_fomod_package", core_fomod_package)
        return results
    finally:
        for project_name in temp_projects:
            cleanup_project(project_name)


def run_suite(name: str) -> list[dict[str, Any]]:
    if name == "core":
        return run_core_suite()
    if name == "logs":
        return run_logs_suite()
    if name == "localization":
        return run_localization_suite()
    if name == "project-toolchain":
        return run_project_toolchain_suite()
    if name == "distribution":
        return run_distribution_suite()
    raise AssertionError(name)


def main() -> int:
    args = parse_args()
    suites = SUITE_ORDER if args.suite == "all" else (args.suite,)
    results: list[dict[str, Any]] = []
    for suite in suites:
        try:
            results.extend(run_suite(suite))
        except Exception as exc:
            results.append({"suite": suite, "name": "suite_setup", "ok": False, "details": str(exc)})

    passed = all(result["ok"] for result in results)
    summary = {
        "suite": args.suite,
        "passed": passed,
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for suite in suites:
            print(f"[{suite}]")
            suite_results = [result for result in results if result["suite"] == suite]
            for result in suite_results:
                status = "ok" if result["ok"] else "fail"
                print(f"- {status} {result['name']}")
                details = result.get("details")
                if details:
                    if isinstance(details, dict):
                        for key, value in details.items():
                            print(f"  {key}: {value}")
                    else:
                        print(f"  {details}")
            print()
        print(f"passed: {'yes' if passed else 'no'}")
        print(f"checks: {len(results)}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
