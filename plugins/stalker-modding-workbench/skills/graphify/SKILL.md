---
name: graphify
description: "Graph any local corpus into a knowledge graph with clustering, HTML/JSON outputs, and an audit trail."
---

# Graphify

This repo-local plugin wrapper exposes the canonical workspace skill at `../../../../.agents/skills/graphify`.

Use this wrapper only as the plugin discovery bridge. For the actual workflow, load and follow:
- `../../../../.agents/skills/graphify/SKILL.md`

Bootstrap note:
- `graphifyy` is installed by the workspace bootstrap so the skill can run its local pipeline.

Expected outputs from the canonical skill include:
- interactive HTML graph views
- GraphRAG-ready JSON
- `GRAPH_REPORT.md` audit/report artifacts
