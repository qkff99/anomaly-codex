#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


SCRIPT_SUFFIXES = {".lua", ".script"}
ENV_OVERRIDES = ("STALKER_LUAC", "LUA_COMPILER", "LUAC")
WINDOWS_CANDIDATE_PATHS = (
    Path(r"C:\Lua\5.1\bin\luac.exe"),
    Path(r"C:\Lua\5.1\luac.exe"),
    Path(r"C:\Lua\5.1\bin\lua.exe"),
    Path(r"C:\Lua\5.1\lua.exe"),
    Path(r"C:\Program Files\Lua\5.1\bin\luac.exe"),
    Path(r"C:\Program Files\Lua\5.1\luac.exe"),
    Path(r"C:\Program Files\Lua\5.1\bin\lua.exe"),
    Path(r"C:\Program Files\Lua\5.1\lua.exe"),
    Path(r"C:\Program Files (x86)\Lua\5.1\bin\luac.exe"),
    Path(r"C:\Program Files (x86)\Lua\5.1\luac.exe"),
    Path(r"C:\Program Files (x86)\Lua\5.1\bin\lua.exe"),
    Path(r"C:\Program Files (x86)\Lua\5.1\lua.exe"),
    Path(r"C:\ProgramData\chocolatey\lib\lua51\tools\luac.exe"),
    Path(r"C:\ProgramData\chocolatey\lib\lua51\tools\lua.exe"),
    Path(r"C:\ProgramData\chocolatey\lib\lua\tools\luac.exe"),
    Path(r"C:\ProgramData\chocolatey\lib\lua\tools\lua.exe"),
)


@dataclass
class Compiler:
    label: str
    command: list[str]
    syntax_mode: str
    version: str | None = None


def command_exists(name: str) -> str | None:
    return shutil.which(name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect and use luac-style syntax checking for Lua 5.1 scripts.")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    detect = subparsers.add_parser("detect", help="Detect a usable Lua compiler/interpreter for syntax checks.")
    detect.add_argument("--install-hints", action="store_true", help="Print platform install hints when detection fails.")
    detect.add_argument("--install-if-missing", action="store_true", help="Attempt to install luac when missing.")

    check = subparsers.add_parser("check", help="Syntax-check files or directories with luac/loadfile.")
    check.add_argument("paths", nargs="+", help="Files or directories to check.")
    check.add_argument("--recursive", action="store_true", help="Recurse into directories.")
    check.add_argument(
        "--allow-non-51",
        action="store_true",
        help="Do not warn when the detected compiler version is not explicitly Lua 5.1.",
    )
    check.add_argument("--install-if-missing", action="store_true", help="Attempt to install luac when missing.")

    hints = subparsers.add_parser("install-hints", help="Print install guidance for luac/Lua 5.1.")
    hints.add_argument("--platform", choices=("auto", "windows", "linux", "darwin"), default="auto")

    return parser.parse_args()


def run_capture(command: list[str]) -> tuple[int, str]:
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def detect_compiler() -> Compiler | None:
    for env_name in ENV_OVERRIDES:
        raw = os.environ.get(env_name)
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if candidate.exists():
            command = [str(candidate.resolve())]
            compiler = Compiler(label=f"{env_name}", command=command, syntax_mode="luac")
            compiler.version = detect_version(compiler)
            return compiler

    candidates = (
        ("luac5.1", ["luac5.1"], "luac"),
        ("luac", ["luac"], "luac"),
        ("lua5.1", ["lua5.1"], "loadfile"),
        ("lua", ["lua"], "loadfile"),
    )
    for label, command, syntax_mode in candidates:
        resolved = command_exists(command[0])
        if resolved:
            compiler = Compiler(label=label, command=[resolved], syntax_mode=syntax_mode)
            compiler.version = detect_version(compiler)
            return compiler

    if os.name == "nt":
        for path in WINDOWS_CANDIDATE_PATHS:
            if path.exists():
                syntax_mode = "luac" if path.name.lower().startswith("luac") else "loadfile"
                compiler = Compiler(label="windows-path", command=[str(path.resolve())], syntax_mode=syntax_mode)
                compiler.version = detect_version(compiler)
                return compiler
    return None


def detect_version(compiler: Compiler) -> str | None:
    probe = compiler.command + ["-v"]
    code, output = run_capture(probe)
    if code == 0 and output:
        return output.splitlines()[0].strip()
    return None


def is_lua_file(path: Path) -> bool:
    return path.suffix.lower() in SCRIPT_SUFFIXES


def iter_targets(paths: list[str], recursive: bool):
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"path not found: {path}")
        if path.is_file():
            if is_lua_file(path):
                yield path
            continue
        if not path.is_dir():
            continue
        if recursive:
            iterator = path.rglob("*")
        else:
            iterator = path.iterdir()
        for candidate in iterator:
            if candidate.is_file() and is_lua_file(candidate):
                yield candidate.resolve()


def syntax_check(compiler: Compiler, path: Path) -> tuple[bool, str]:
    if compiler.syntax_mode == "luac":
        command = compiler.command + ["-p", str(path)]
    else:
        command = compiler.command + [
            "-e",
            (
                "local f, err = loadfile(arg[1]); "
                "if not f then io.stderr:write(err .. '\\n'); os.exit(1) end"
            ),
            str(path),
        ]
    code, output = run_capture(command)
    return code == 0, output


def print_install_hints(platform_name: str) -> None:
    if platform_name == "auto":
        platform_name = sys.platform

    if platform_name.startswith("linux"):
        print("Linux/WSL install hints:")
        print("- Debian/Ubuntu/WSL: sudo apt install lua5.1")
        print("- If only generic lua/luac is available, verify `luac -v` reports Lua 5.1 before using it for Anomaly scripts.")
        return

    if platform_name == "darwin":
        print("macOS install hints:")
        print("- Install a Lua 5.1 distribution that provides `luac` or `luac5.1`.")
        print("- If using Homebrew or another package manager, prefer a package that explicitly exposes Lua 5.1.")
        return

    if platform_name.startswith("win") or platform_name == "windows":
        print("Windows install hints:")
        print("- winget: winget install --id rjpcomputing.luaforwindows -e --accept-source-agreements --accept-package-agreements")
        print("- chocolatey: choco install lua51 -y")
        print("- Add the install directory to PATH, or set STALKER_LUAC to the full luac.exe path.")
        print("- The skill wrappers can then use `py -3 .../luac_tool.py check <path>` from PowerShell.")
        return

    print("Install a Lua 5.1 distribution that provides `luac` or `luac5.1`, then add it to PATH or set STALKER_LUAC.")


def try_install_luac() -> bool:
    script_dir = Path(__file__).resolve().parent
    if os.name == "nt":
        helper = script_dir / "bootstrap_env.ps1"
        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            "ensure",
            "luac",
        ]
    else:
        helper = script_dir / "bootstrap_env.sh"
        command = ["bash", str(helper), "ensure", "luac"]
    completed = subprocess.run(command, check=False)
    return completed.returncode == 0


def handle_detect(install_hints: bool, install_if_missing: bool) -> int:
    compiler = detect_compiler()
    if compiler is None and install_if_missing:
        if try_install_luac():
            compiler = detect_compiler()
    if compiler is None:
        print("luac: not found")
        if install_hints:
            print_install_hints("auto")
        return 1

    print(f"compiler: {compiler.label}")
    print(f"command: {' '.join(compiler.command)}")
    print(f"mode: {compiler.syntax_mode}")
    print(f"version: {compiler.version or 'unknown'}")
    return 0


def handle_check(paths: list[str], recursive: bool, allow_non_51: bool, install_if_missing: bool) -> int:
    compiler = detect_compiler()
    if compiler is None and install_if_missing:
        if try_install_luac():
            compiler = detect_compiler()
    if compiler is None:
        print("luac: not found")
        print_install_hints("auto")
        return 1

    if compiler.version and "5.1" not in compiler.version and not allow_non_51:
        print(f"warning: detected compiler is not explicitly Lua 5.1: {compiler.version}")

    failures = 0
    checked = 0
    seen: set[Path] = set()
    for path in iter_targets(paths, recursive):
        if path in seen:
            continue
        seen.add(path)
        checked += 1
        ok, output = syntax_check(compiler, path)
        if ok:
            print(f"OK {path}")
        else:
            failures += 1
            print(f"FAIL {path}")
            if output:
                print(output)

    if checked == 0:
        print("no Lua files matched")
        return 1

    print(f"checked: {checked}")
    print(f"failed: {failures}")
    return 1 if failures else 0


def main() -> int:
    args = parse_args()
    if args.subcommand == "detect":
        return handle_detect(args.install_hints, args.install_if_missing)
    if args.subcommand == "check":
        return handle_check(args.paths, args.recursive, args.allow_non_51, args.install_if_missing)
    if args.subcommand == "install-hints":
        print_install_hints(args.platform)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
