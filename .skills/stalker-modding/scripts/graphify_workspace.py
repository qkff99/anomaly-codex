#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from _skill_common import REPO_ROOT


DEFAULT_ROOT = REPO_ROOT / "ai_workspace"
GRAPH_OUTPUT_NAMES = ("graphify-out", "lua-graphify-out")


@dataclass
class OutputEntry:
    rel_dir: str
    output_name: str
    title: str
    primary_link: str | None
    report_link: str | None
    wiki_link: str | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Workspace-local graphify helper for the STALKER modding workbench. "
            "Builds Lua-only maps for *.script and *.lua corpora and regenerates a "
            "single HTML index over graphify artifacts."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    lua_map = subparsers.add_parser("lua-map", help="Build a Lua-only graphify map for a workspace root.")
    lua_map.add_argument("--root", default=str(DEFAULT_ROOT), help="Root to scan for *.script and *.lua files.")
    lua_map.add_argument(
        "--output-name",
        default="lua-graphify-out",
        help="Output directory name created under the root.",
    )

    index = subparsers.add_parser("index", help="Generate an HTML index over existing graphify outputs.")
    index.add_argument("--root", default=str(DEFAULT_ROOT), help="Root that contains graphify output folders.")

    both = subparsers.add_parser("all", help="Build the Lua-only map and then regenerate the HTML index.")
    both.add_argument("--root", default=str(DEFAULT_ROOT), help="Root to scan for *.script and *.lua files.")
    both.add_argument(
        "--output-name",
        default="lua-graphify-out",
        help="Output directory name created under the root.",
    )
    return parser


def _require_graphify() -> dict[str, Any]:
    try:
        from graphify.extract import extract
        from graphify.build import build_from_json
        from graphify.cluster import cluster, score_all
        from graphify.analyze import god_nodes, surprising_connections, suggest_questions
        from graphify.report import generate
        from graphify.export import to_json
        from graphify.wiki import to_wiki
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "graphifyy is not installed. Run bootstrap_workspace or install graphifyy first."
        ) from exc

    return {
        "extract": extract,
        "build_from_json": build_from_json,
        "cluster": cluster,
        "score_all": score_all,
        "god_nodes": god_nodes,
        "surprising_connections": surprising_connections,
        "suggest_questions": suggest_questions,
        "generate": generate,
        "to_json": to_json,
        "to_wiki": to_wiki,
    }


def _normalize_rel(path: Path) -> str:
    raw = str(path).replace("\\", "/")
    return raw if raw not in ("", ".") else "."


def _path_relative_to_root(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        rel = path
    return _normalize_rel(rel)


def _iter_lua_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    skip_names = set(GRAPH_OUTPUT_NAMES)
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        if any(part in skip_names for part in candidate.parts):
            continue
        suffix = candidate.suffix.lower()
        if suffix in {".script", ".lua"}:
            paths.append(candidate.resolve())
    return sorted(set(paths))


def _invert_communities(communities: dict[int, list[str]]) -> dict[str, int]:
    return {node_id: cid for cid, nodes in communities.items() for node_id in nodes}


def _top_community_label(stats: dict[str, Any]) -> str:
    counter: Counter[int] = stats["communities"]
    if not counter:
        return "-"
    cid, count = counter.most_common(1)[0]
    return f"Community {cid} ({count})"


def _build_folder_stats(
    root: Path,
    paths: list[Path],
    graph: Any,
    communities: dict[int, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    folder_stats: dict[str, dict[str, Any]] = {}

    def ensure_folder(rel_folder: str) -> dict[str, Any]:
        key = rel_folder if rel_folder else "."
        if key not in folder_stats:
            folder_stats[key] = {
                "path": key,
                "direct_files": 0,
                "recursive_files": 0,
                "graph_nodes": 0,
                "communities": Counter(),
                "children": set(),
            }
        return folder_stats[key]

    ensure_folder(".")
    for path in paths:
        rel_path = _path_relative_to_root(path, root)
        parts = rel_path.split("/")
        parent = "/".join(parts[:-1]) if len(parts) > 1 else "."
        ensure_folder(parent)["direct_files"] += 1
        for depth in range(len(parts)):
            folder = "/".join(parts[:depth]) if depth > 0 else "."
            stats = ensure_folder(folder)
            stats["recursive_files"] += 1
            child = "/".join(parts[: depth + 1]) if depth + 1 < len(parts) else None
            if child:
                stats["children"].add(child)

    node_to_community = _invert_communities(communities)
    for node_id, data in graph.nodes(data=True):
        source = str(data.get("source_file", "") or "")
        if not source:
            continue
        parent = _normalize_rel(Path(_path_relative_to_root(Path(source), root)).parent)
        folders = [parent]
        if parent != ".":
            parent_path = Path(parent)
            for probe in parent_path.parents:
                rel = _normalize_rel(probe)
                folders.append(rel)

        seen: set[str] = set()
        for rel in folders:
            if rel in seen:
                continue
            seen.add(rel)
            stats = ensure_folder(rel)
            stats["graph_nodes"] += 1
            cid = node_to_community.get(node_id)
            if cid is not None:
                stats["communities"][cid] += 1

    edge_weights: Counter[tuple[str, str]] = Counter()
    for source_id, target_id, _edge_data in graph.edges(data=True):
        source_file = str(graph.nodes[source_id].get("source_file", "") or "")
        target_file = str(graph.nodes[target_id].get("source_file", "") or "")
        if not source_file or not target_file:
            continue
        source_dir = _normalize_rel(Path(_path_relative_to_root(Path(source_file), root)).parent)
        target_dir = _normalize_rel(Path(_path_relative_to_root(Path(target_file), root)).parent)
        if source_dir == target_dir:
            continue
        pair = tuple(sorted((source_dir, target_dir)))
        edge_weights[pair] += 1

    folder_items = []
    for path_key, stats in sorted(folder_stats.items()):
        folder_items.append(
            {
                "path": path_key,
                "direct_files": stats["direct_files"],
                "recursive_files": stats["recursive_files"],
                "graph_nodes": stats["graph_nodes"],
                "top_community": _top_community_label(stats),
                "children": sorted(stats["children"]),
            }
        )
    edge_items = [{"source": a, "target": b, "weight": w} for (a, b), w in edge_weights.most_common(120)]
    return folder_items, edge_items


def _write_folder_map(
    root: Path,
    output_dir: Path,
    paths: list[Path],
    graph: Any,
    communities: dict[int, list[str]],
    wiki_count: int,
) -> dict[str, Any]:
    folders, edges = _build_folder_stats(root, paths, graph, communities)
    script_count = sum(1 for path in paths if path.suffix.lower() == ".script")
    lua_count = sum(1 for path in paths if path.suffix.lower() == ".lua")
    summary = {
        "root": str(root),
        "lua_files": len(paths),
        "script_files": script_count,
        "lua_ext_files": lua_count,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "communities": len(communities),
        "wiki_articles": wiki_count,
        "folders": folders,
        "top_cross_folder_edges": edges,
    }
    (output_dir / "folder_map.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    folder_lookup = {item["path"]: item for item in folders}

    lines = [
        f"# {root.name} Lua Folder Map",
        "",
        f"- Lua-family files: {len(paths)}",
        f"- .script files: {script_count}",
        f"- .lua files: {lua_count}",
        f"- Graph: {graph.number_of_nodes()} nodes · {graph.number_of_edges()} edges · {len(communities)} communities",
        f"- Wiki articles written: {wiki_count}",
        "",
        "## Heaviest Folders",
    ]
    for item in sorted((entry for entry in folders if entry["path"] != "."), key=lambda entry: entry["recursive_files"], reverse=True)[:60]:
        lines.append(
            f"- `{item['path']}` — {item['recursive_files']} Lua files · "
            f"{item['graph_nodes']} graph nodes · dominant {item['top_community']}"
        )
    lines.extend(["", "## Strongest Cross-Folder Links"])
    for edge in edges[:60]:
        lines.append(f"- `{edge['source']}` ↔ `{edge['target']}` — {edge['weight']} graph edges")
    lines.extend(["", "## Full Folder Tree"])

    def walk(folder: str, depth: int = 0) -> None:
        entry = folder_lookup[folder]
        indent = "  " * depth
        label = root.name if folder == "." else folder
        lines.append(
            f"{indent}- `{label}` — {entry['recursive_files']} Lua files / "
            f"{entry['graph_nodes']} graph nodes"
        )
        for child in sorted(entry["children"]):
            if child != folder:
                walk(child, depth + 1)

    walk(".")
    (output_dir / "folder_map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def tree_html(folder: str) -> str:
        entry = folder_lookup[folder]
        label = root.name if folder == "." else folder
        header = (
            f"<summary><code>{escape(label)}</code> "
            f"<span class='muted'>{entry['recursive_files']} Lua files</span> "
            f"<span class='muted'>{entry['graph_nodes']} graph nodes</span> "
            f"<span class='muted'>dominant {escape(entry['top_community'])}</span></summary>"
        )
        children = "".join(tree_html(child) for child in sorted(entry["children"]) if child != folder)
        if children:
            return f"<details open>{header}<div class='children'>{children}</div></details>"
        return f"<details>{header}</details>"

    edge_rows = "".join(
        f"<tr><td><code>{escape(edge['source'])}</code></td>"
        f"<td><code>{escape(edge['target'])}</code></td><td>{edge['weight']}</td></tr>"
        for edge in edges[:100]
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(root.name)} Lua Folder Map</title>
<style>
body {{ font-family: Segoe UI, Arial, sans-serif; background:#111318; color:#e8ecf1; margin:0; padding:24px; }}
h1,h2 {{ margin:0 0 12px; }}
section {{ margin:0 0 24px; padding:16px; background:#1a1f29; border:1px solid #2b3340; border-radius:12px; }}
code {{ color:#b9d4ff; }}
.muted {{ color:#98a4b5; margin-left:8px; font-size:12px; }}
details {{ margin:4px 0; padding-left:8px; }}
summary {{ cursor:pointer; line-height:1.6; }}
.children {{ margin-left:18px; border-left:1px solid #2b3340; padding-left:12px; }}
table {{ width:100%; border-collapse:collapse; }}
th,td {{ text-align:left; padding:8px; border-bottom:1px solid #2b3340; vertical-align:top; }}
</style>
</head>
<body>
<section>
<h1>{escape(root.name)} Lua Folder Map</h1>
<p>Lua-family files: {len(paths)} | .script: {script_count} | .lua: {lua_count}</p>
<p>Graph: {graph.number_of_nodes()} nodes · {graph.number_of_edges()} edges · {len(communities)} communities</p>
<p>Artifacts: <code>graph.json</code>, <code>GRAPH_REPORT.md</code>, <code>wiki/</code>, <code>folder_map.json</code>, <code>folder_map.md</code></p>
</section>
<section>
<h2>Folder Tree</h2>
{tree_html(".")}
</section>
<section>
<h2>Strongest Cross-Folder Links</h2>
<table>
<thead><tr><th>Source folder</th><th>Target folder</th><th>Edge weight</th></tr></thead>
<tbody>{edge_rows}</tbody>
</table>
</section>
</body>
</html>
"""
    (output_dir / "folder_map.html").write_text(html, encoding="utf-8")
    return summary


def build_lua_map(root: Path, output_name: str) -> dict[str, Any]:
    modules = _require_graphify()
    output_dir = root / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = _iter_lua_paths(root)
    if not paths:
        raise RuntimeError(f"No *.script or *.lua files found under {root}")

    print(f"[graphify-workspace] extracting {len(paths)} Lua-family files from {root}")
    result = modules["extract"](paths, cache_root=root)
    graph = modules["build_from_json"](result)
    communities = modules["cluster"](graph)
    cohesion = modules["score_all"](graph, communities)
    gods = modules["god_nodes"](graph)
    surprises = modules["surprising_connections"](graph, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    questions = modules["suggest_questions"](graph, communities, labels)
    detection = {
        "files": {
            "code": [_path_relative_to_root(path, root) for path in paths],
            "document": [],
            "paper": [],
            "image": [],
        },
        "total_files": len(paths),
        "total_words": 0,
    }
    report = modules["generate"](
        graph,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        {"input": 0, "output": 0},
        str(root),
        suggested_questions=questions,
    )
    (output_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    modules["to_json"](graph, communities, str(output_dir / "graph.json"))
    wiki_count = modules["to_wiki"](
        graph,
        communities,
        output_dir / "wiki",
        community_labels=labels,
        cohesion=cohesion,
        god_nodes_data=gods,
    )
    summary = _write_folder_map(root, output_dir, paths, graph, communities, wiki_count)
    print(
        json.dumps(
            {
                "output": str(output_dir),
                "lua_files": summary["lua_files"],
                "graph_nodes": summary["graph_nodes"],
                "graph_edges": summary["graph_edges"],
                "communities": summary["communities"],
                "wiki_articles": summary["wiki_articles"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return summary


def _entry_title(root: Path, rel_dir: str, output_name: str) -> str:
    if rel_dir == ".":
        return f"{root.name} Lua overview" if output_name == "lua-graphify-out" else f"{root.name} overview"
    if output_name == "lua-graphify-out":
        return f"{rel_dir} Lua overview"
    return rel_dir


def _discover_outputs(root: Path) -> list[OutputEntry]:
    entries: list[OutputEntry] = []
    for output_name in GRAPH_OUTPUT_NAMES:
        for directory in sorted(root.rglob(output_name)):
            rel_dir = _normalize_rel(directory.parent.relative_to(root))
            primary = None
            for candidate in ("folder_map.html", "graph.html", "folder_map.md"):
                if (directory / candidate).exists():
                    primary = _normalize_rel((directory / candidate).relative_to(root))
                    break
            report_link = None
            if (directory / "GRAPH_REPORT.md").exists():
                report_link = _normalize_rel((directory / "GRAPH_REPORT.md").relative_to(root))
            wiki_link = None
            if (directory / "wiki" / "index.md").exists():
                wiki_link = _normalize_rel((directory / "wiki" / "index.md").relative_to(root))
            entries.append(
                OutputEntry(
                    rel_dir=rel_dir,
                    output_name=output_name,
                    title=_entry_title(root, rel_dir, output_name),
                    primary_link=primary,
                    report_link=report_link,
                    wiki_link=wiki_link,
                )
            )
    return entries


def _category_name(entry: OutputEntry) -> str:
    if entry.rel_dir == ".":
        return "Global Overviews"
    if entry.rel_dir.startswith("src/xrGame/"):
        return "xrGame Slices"
    if entry.rel_dir.startswith("src/"):
        return "Engine Source"
    return "Reference Packs"


def build_index(root: Path) -> Path:
    entries = _discover_outputs(root)
    categories: dict[str, list[OutputEntry]] = defaultdict(list)
    for entry in entries:
        categories[_category_name(entry)].append(entry)

    order = ("Global Overviews", "Reference Packs", "Engine Source", "xrGame Slices")
    sections: list[str] = []
    for category in order:
        items = categories.get(category, [])
        if not items:
            continue
        items = sorted(items, key=lambda entry: (entry.rel_dir != ".", entry.rel_dir, entry.output_name))
        rows = []
        for entry in items:
            links = []
            if entry.primary_link:
                links.append(f"<a href=\"{escape(entry.primary_link)}\">open map</a>")
            if entry.report_link:
                links.append(f"<a href=\"{escape(entry.report_link)}\">report</a>")
            if entry.wiki_link:
                links.append(f"<a href=\"{escape(entry.wiki_link)}\">wiki</a>")
            row = (
                f"<li><strong>{escape(entry.title)}</strong>"
                + (f" <span class='hint'>({escape(entry.rel_dir)})</span>" if entry.rel_dir != "." else "")
                + " — "
                + " · ".join(links)
                + "</li>"
            )
            rows.append(row)
        sections.append(
            f"<section><h2>{escape(category)}</h2><ul>{''.join(rows)}</ul></section>"
        )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{escape(root.name)} Map Index</title>
<style>
body {{ margin: 0; padding: 24px; background: #0f1318; color: #e6edf3; font-family: "Segoe UI", Arial, sans-serif; }}
h1, h2 {{ margin: 0 0 12px; }}
section {{ margin: 0 0 20px; padding: 18px; background: #171d25; border: 1px solid #2a3440; border-radius: 12px; }}
p {{ margin: 0 0 12px; color: #aeb9c6; }}
ul {{ margin: 0; padding-left: 20px; }}
li {{ margin: 8px 0; }}
a {{ color: #8ec5ff; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
code {{ color: #c8e1ff; }}
.hint {{ color: #8a97a6; font-size: 13px; }}
</style>
</head>
<body>
<section>
  <h1>{escape(root.name)} Map Index</h1>
  <p>Entry point for generated graphify artifacts in this workspace root.</p>
  <p class="hint">Prefer folder maps for giant corpora and per-folder graph.html pages where the native renderer fits.</p>
</section>
{''.join(sections)}
</body>
</html>
"""
    target = root / "map_index.html"
    target.write_text(html, encoding="utf-8")
    print(f"[graphify-workspace] wrote index: {target}")
    return target


def main() -> int:
    args = build_parser().parse_args()
    root = Path(getattr(args, "root")).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"root does not exist: {root}")

    if args.command == "lua-map":
        build_lua_map(root, args.output_name)
        return 0
    if args.command == "index":
        build_index(root)
        return 0
    if args.command == "all":
        build_lua_map(root, args.output_name)
        build_index(root)
        return 0
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
