#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from _skill_common import (
    REPO_ROOT,
    load_json_file,
    load_workspace_overlay_data,
    save_workspace_overlay_data,
    write_json_file,
    write_text_exact,
    workspace_known_reference_repos,
)


GITHUB_REPO_RE = re.compile(r"""^(?:https?://github\.com/)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:/.*)?$""")
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
PLUGIN_MCP_PATH = REPO_ROOT / "plugins" / "stalker-modding-workbench" / ".mcp.json"
VSCODE_MCP_PATH = REPO_ROOT / ".vscode" / "mcp.json"
REPO_PROFILES_DIR = REPO_ROOT / ".skills" / "stalker-modding" / "references" / "repos"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover and persist curated GitHub/GitMCP reference repos.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search GitHub repositories relevant to an Anomaly modding query.")
    search.add_argument("--query", required=True, help="GitHub repository search query.")
    search.add_argument("--limit", type=int, default=10, help="Maximum results to print.")

    persist = subparsers.add_parser("persist", help="Persist a curated GitHub repo into MCP config and overlay.")
    persist.add_argument("--repo", required=True, help="owner/repo or GitHub repo URL.")
    persist.add_argument("--id", required=True, help="Stable slug used for MCP server id and repo profile file.")
    persist.add_argument("--role", required=True, help="Curated role such as modpack-index, addon, or script-reference.")

    subparsers.add_parser("list", help="List persisted known reference repos from the workspace overlay.")
    return parser


def normalize_repo_slug(raw: str) -> str:
    match = GITHUB_REPO_RE.match(raw.strip())
    if not match:
        raise ValueError(f"unsupported GitHub repo format: {raw}")
    return match.group(1)


def score_repo(entry: dict, query: str) -> tuple[int, int]:
    text = " ".join(
        str(value or "")
        for value in (
            entry.get("full_name"),
            entry.get("name"),
            entry.get("description"),
            " ".join(entry.get("topics") or []),
        )
    ).lower()
    score = 0
    for needle, bonus in (
        ("anomaly", 8),
        ("stalker", 8),
        ("gamma", 8),
        ("modpack", 5),
        ("addon", 4),
        ("lua", 3),
        ("script", 3),
        ("mod organizer", 2),
        ("install", 2),
    ):
        if needle in text:
            score += bonus
    lowered_query = query.lower()
    if lowered_query and lowered_query in text:
        score += 10
    return score, int(entry.get("stargazers_count") or 0)


def github_search(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "per_page": max(1, min(limit, 20))})
    request = urllib.request.Request(
        f"{GITHUB_SEARCH_URL}?{params}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "anomaly-codex-skill",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    items = payload.get("items", [])
    if not isinstance(items, list):
        return []
    ranked = sorted(items, key=lambda entry: score_repo(entry, query), reverse=True)
    return ranked[:limit]


def render_repo_profile(slug: str, role: str, mcp_server: str) -> str:
    if slug.lower() == "grokitach/stalker_gamma":
        return "\n".join(
            [
                "# Repo Profile: stalker-gamma",
                "",
                "Repository:",
                "- `Grokitach/Stalker_GAMMA`",
                "",
                "Use this repo as a curated online reference for:",
                "- modpack composition and addon discovery",
                "- install lists and external addon jump points",
                "- pack-specific glue scripts or custom overrides when they exist",
                "",
                "Do not use it as the primary truth for:",
                "- engine runtime semantics",
                "- vanilla Anomaly behavior when local refs differ",
                "",
                "Preferred role:",
                f"- `{role}`",
                "",
                "Preferred MCP server:",
                f"- `{mcp_server}`",
                "",
                "High-value search themes:",
                "- addon list",
                "- install",
                "- modpack",
                "- custom scripts",
                "- MO2",
                "",
            ]
        )

    return "\n".join(
        [
            f"# Repo Profile: {mcp_server}",
            "",
            "Repository:",
            f"- `{slug}`",
            "",
            "Use this repo as a curated online reference for:",
            f"- `{role}`",
            "- Anomaly add-on discovery and implementation comparison when local refs are insufficient",
            "",
            "Do not use it as the primary truth for:",
            "- engine runtime semantics",
            "- current workspace behavior when local code differs",
            "",
            "Preferred MCP server:",
            f"- `{mcp_server}`",
            "",
        ]
    )


def update_mcp_configs(server_id: str, repo_slug: str, note: str) -> None:
    server_payload = {
        "type": "http",
        "url": f"https://gitmcp.io/{repo_slug}",
        "note": note,
    }
    for path in (PLUGIN_MCP_PATH, VSCODE_MCP_PATH):
        data = load_json_file(path)
        servers = data.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            raise ValueError(f"mcpServers must be an object in {path}")
        servers[server_id] = server_payload
        write_json_file(path, data)


def update_known_reference_repos(server_id: str, repo_slug: str, role: str) -> Path:
    _, overlay = load_workspace_overlay_data()
    overlay.setdefault("known_reference_repos", [])
    entries = overlay["known_reference_repos"]
    if not isinstance(entries, list):
        raise ValueError("known_reference_repos must be a list in workspace overlay")

    filtered = [
        entry
        for entry in entries
        if not (
            isinstance(entry, dict)
            and (entry.get("id") == server_id or entry.get("repo") == repo_slug)
        )
    ]
    filtered.append(
        {
            "id": server_id,
            "repo": repo_slug,
            "mcp_server": server_id,
            "role": role,
        }
    )
    overlay["known_reference_repos"] = filtered
    return save_workspace_overlay_data(overlay)


def command_search(args: argparse.Namespace) -> int:
    try:
        results = github_search(args.query, args.limit)
    except urllib.error.URLError as exc:
        print(f"github search failed: {exc}")
        return 1

    if not results:
        print("no GitHub repository results found")
        return 1

    for entry in results:
        description = (entry.get("description") or "").strip()
        print(f"{entry.get('full_name')}")
        print(f"  html_url: {entry.get('html_url')}")
        print(f"  stars: {entry.get('stargazers_count', 0)}")
        print(f"  description: {description or 'none'}")
    return 0


def command_persist(args: argparse.Namespace) -> int:
    repo_slug = normalize_repo_slug(args.repo)
    server_id = args.id.strip()
    role = args.role.strip()
    if not server_id or not role:
        print("--id and --role must be non-empty")
        return 1

    note = f"Curated GitMCP endpoint for {repo_slug} ({role})."
    update_mcp_configs(server_id, repo_slug, note)
    overlay_path = update_known_reference_repos(server_id, repo_slug, role)

    profile_path = REPO_PROFILES_DIR / f"{server_id}.md"
    write_text_exact(profile_path, render_repo_profile(repo_slug, role, server_id) + "\n")

    print(f"repo: {repo_slug}")
    print(f"mcp_server: {server_id}")
    print(f"overlay: {overlay_path}")
    print(f"profile: {profile_path}")
    return 0


def command_list() -> int:
    entries = workspace_known_reference_repos()
    if not entries:
        print("known_reference_repos: none")
        return 0
    for entry in entries:
        print(f"{entry.get('id')}: {entry.get('repo')} [{entry.get('role')}] -> {entry.get('mcp_server')}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "search":
            return command_search(args)
        if args.command == "persist":
            return command_persist(args)
        if args.command == "list":
            return command_list()
    except ValueError as exc:
        print(exc)
        return 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
