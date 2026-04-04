#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

from _project_toolchain import load_project, packaging_ignore_entries, validate_project_metadata


DEFAULT_AUTHOR = "Unknown"
DEFAULT_VERSION = "1.0.0"
DEFAULT_CORE_FOLDER = "00 Core"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a simple core-only FOMOD package for a project under projects/."
    )
    parser.add_argument("--project", required=True, help="Project name under projects/.")
    parser.add_argument("--module-name", help="Visible FOMOD module name. Defaults to project display_name.")
    parser.add_argument("--author", default=DEFAULT_AUTHOR, help="FOMOD metadata author.")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="FOMOD metadata version.")
    parser.add_argument("--website", default="", help="Optional FOMOD metadata website.")
    parser.add_argument("--description", default="", help="Optional FOMOD metadata description.")
    parser.add_argument(
        "--dist-name",
        help="Custom dist folder name under projects/<name>/dist. Defaults to <project-name>-fomod.",
    )
    parser.add_argument(
        "--core-folder",
        default=DEFAULT_CORE_FOLDER,
        help="Top-level folder used as the required core payload. Defaults to '00 Core'.",
    )
    return parser.parse_args()


def render_info_xml(
    *,
    module_name: str,
    author: str,
    version: str,
    description: str,
    website: str,
) -> str:
    lines = [
        '<?xml version="1.0" encoding="utf-8" ?>',
        "",
        "<fomod>",
        f"    <Name>{escape(module_name)}</Name>",
        f"    <Author>{escape(author)}</Author>",
        f'    <Version MachineVersion="{escape(version)}">{escape(version)}</Version>',
        f"    <Description>{escape(description)}</Description>",
    ]
    if website:
        lines.append(f"    <Website>{escape(website)}</Website>")
    lines.extend(
        [
            "</fomod>",
            "",
        ]
    )
    return "\n".join(lines)


def render_module_config_xml(*, module_name: str, core_folder: str) -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="utf-8" ?>',
            "",
            '<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
            '        xsi:noNamespaceSchemaLocation="http://qconsulting.ca/fo3/ModConfig5.0.xsd">',
            f"    <moduleName>{escape(module_name)}</moduleName>",
            "    <requiredInstallFiles>",
            f'        <folder source="{escape(core_folder)}" destination="" />',
            "    </requiredInstallFiles>",
            "</config>",
            "",
        ]
    )


def main() -> int:
    args = parse_args()
    project_root, metadata = load_project(args.project)
    errors = validate_project_metadata(metadata)
    if errors:
        print("project metadata is invalid:")
        for error in errors:
            print(f"- {error}")
        return 1

    mod_root_name = str(metadata["mod_root"])
    source_root = project_root / mod_root_name
    if not source_root.exists():
        print(f"mod root not found: {source_root}")
        return 1

    project_name = str(metadata["project_name"])
    module_name = args.module_name or str(metadata["display_name"])
    description = args.description or f"Core files for {module_name}."
    dist_name = args.dist_name or f"{project_name}-fomod"
    core_folder = args.core_folder.strip() or DEFAULT_CORE_FOLDER

    dist_root = project_root / "dist" / dist_name
    core_root = dist_root / core_folder
    payload_root = core_root / mod_root_name
    fomod_root = dist_root / "fomod"
    info_xml = fomod_root / "info.xml"
    module_config = fomod_root / "ModuleConfig.xml"

    if dist_root.exists():
        shutil.rmtree(dist_root)
    fomod_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, payload_root, ignore=packaging_ignore_entries, dirs_exist_ok=True)

    info_xml.write_text(
        render_info_xml(
            module_name=module_name,
            author=args.author,
            version=args.version,
            description=description,
            website=args.website,
        ),
        encoding="utf-8",
    )
    module_config.write_text(
        render_module_config_xml(module_name=module_name, core_folder=core_folder),
        encoding="utf-8",
    )

    print(f"project_root: {project_root}")
    print(f"source: {source_root}")
    print(f"package_root: {dist_root}")
    print(f"payload_root: {payload_root}")
    print(f"info_xml: {info_xml}")
    print(f"module_config: {module_config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
