---
name: graphify
description: "STALKER workspace graph skill for Lua-first corpus maps, subsystem routing, and dependency/path lookups."
---

# Graphify

Use this plugin-local copy for this workbench, not the generic upstream graphify workflow.

This workspace already has repo-specific graphify behavior:
- local `graphify` is patched so `*.script` is treated as Lua
- giant corpora are routed through `folder_map.html`, `GRAPH_REPORT.md`, and `wiki/` instead of one fragile `graph.html`
- a repo-local helper exists at `../../../../.skills/stalker-modding/scripts/graphify_workspace.py`

## When To Use This Skill

Use `$graphify` when one of these is true:
- the user asks for a map, graph, ownership view, architecture view, or subsystem overview
- the Lua corpus is too large to inspect file-by-file
- you need cross-file routing across `vanilla scripts`, `GAMMA Scripts`, or `Anomaly-Mod-Configuration-Menu-main`
- you need a shortest path or node explanation before patching a subsystem
- you want to narrow a large search surface before raw reference searches or edits

## Prefer Existing Artifacts First

Before rebuilding anything, inspect the generated maps already present in this workspace:
- `../../../../ai_workspace/map_index.html`
- `../../../../ai_workspace/lua-graphify-out/folder_map.html`
- `../../../../ai_workspace/lua-graphify-out/GRAPH_REPORT.md`
- `../../../../ai_workspace/lua-graphify-out/wiki/index.md`
- `../../../../ai_workspace/vanilla scripts/graphify-out/folder_map.html`
- `../../../../ai_workspace/GAMMA Scripts/graphify-out/graph.html`
- per-folder `../../../../ai_workspace/src/*/graphify-out/graph.html`

Routing rules:
- For Anomaly script behavior, prefer the combined Lua-only graph under `ai_workspace/lua-graphify-out`.
- For vanilla-only grounding, prefer `ai_workspace/vanilla scripts/graphify-out`.
- For GAMMA pack glue, prefer `ai_workspace/GAMMA Scripts/graphify-out`.
- For engine source, prefer the smallest existing `ai_workspace/src/<subsystem>/graphify-out` graph instead of a whole-tree rebuild.

## Rebuild Workflow

Use the repo-local helper when the task is about STALKER Lua or when the combined workspace map needs refresh.

Windows PowerShell:

```powershell
py -3 .\.skills\stalker-modding\scripts\graphify_workspace.py all --root ai_workspace
py -3 .\.skills\stalker-modding\scripts\graphify_workspace.py lua-map --root ai_workspace
py -3 .\.skills\stalker-modding\scripts\graphify_workspace.py index --root ai_workspace
```

WSL/Linux/macOS:

```bash
python3 ./.skills/stalker-modding/scripts/graphify_workspace.py all --root ai_workspace
python3 ./.skills/stalker-modding/scripts/graphify_workspace.py lua-map --root ai_workspace
python3 ./.skills/stalker-modding/scripts/graphify_workspace.py index --root ai_workspace
```

Use native `graphify update <subfolder>` only for smaller non-Lua code trees such as `ai_workspace/src/xrCore` or `ai_workspace/src/xrEngine`.

## Query Workflow

After locating the right graph, use the native query tools against that graph:

```powershell
graphify explain "ui_mcm" --graph "ai_workspace/lua-graphify-out/graph.json"
graphify path "ui_mcm" "axr_main" --graph "ai_workspace/lua-graphify-out/graph.json"
graphify query "What are the main Lua subsystems in this workspace?" --graph "ai_workspace/lua-graphify-out/graph.json" --budget 1200
```

Use `explain` and `path` before broad `query` when you already know the node or subsystem names. They are more reliable on large graphs.

## Rules

- Treat graphify as a routing and summarization layer, not final authority on runtime semantics.
- Verify any graph-derived claim in local code before editing.
- Prefer the smallest graph that can answer the question.
- Do not try to force a single huge `graph.html` for all of `ai_workspace`; use folder maps and per-subsystem graphs instead.
- For STALKER behavior work, stay Lua-first unless the user explicitly wants C++ or docs mapping.
