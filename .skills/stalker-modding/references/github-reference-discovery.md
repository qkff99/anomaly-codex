# GitHub Reference Discovery

Use this file when local refs are insufficient and the task needs external Anomaly addon or modpack references from GitHub.

## Commands

- `scripts/discover_github_refs.py search --query "<text>"`
  - search GitHub repositories relevant to the query
- `scripts/discover_github_refs.py persist --repo owner/repo --id <slug> --role <role>`
  - promote a curated repo into persistent MCP and overlay state
- `scripts/discover_github_refs.py list`
  - show persisted curated repos

## Persistence Rules

Only persist curated high-signal repos.

Persisting a repo updates:
- `.vscode/mcp.json`
- `plugins/stalker-modding-workbench/.mcp.json`
- `.codex-stalker/workspace.json`
- `references/repos/<slug>.md`

## Seeded Reference

- `Grokitach/Stalker_GAMMA`
  - role: `modpack-index`
  - use it for addon discovery, modpack composition, install lists, and pack-specific glue
  - do not treat it as the final authority on engine semantics

## Practical Rules

- Prefer local vanilla, engine, and workspace refs first.
- Use GitHub discovery when the task needs example implementations, addon lists, or ecosystem reconnaissance.
- Promote only the repos that are likely to be reused across tasks.
