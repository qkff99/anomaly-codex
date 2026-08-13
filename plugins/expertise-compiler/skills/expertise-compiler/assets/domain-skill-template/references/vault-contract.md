# Vault contract

The generated skill uses `{{VAULT_PATH}}` as the vault root for `{{DOMAIN_NAME}}`.

## Authority order

1. Registered immutable raw code or documents at an exact commit or snapshot provide evidence.
2. Provenance records bind claims to source spans.
3. Wiki pages explain and connect evidence.
4. Maps, aliases, graph rankings, and lexical indexes accelerate navigation.
5. Context packs select evidence under a budget but never answer the task.

Do not treat derived artifacts or disposable indexes as the sole source of truth.

## Important paths

- `vault.json` identifies the vault and format version.
- `COMPETENCY.md` defines supported tasks, scope, authority, versions, and gaps.
- `sources/registry.jsonl` records source identity, trust, version, and fingerprints.
- `sources/raw/` contains immutable evidence snapshots.
- `wiki/ROUTER.md` provides the first navigation layer.
- `wiki/` contains derived maps and knowledge pages.
- `code/` contains deterministic file, symbol, edge, alias, and repo-map data.
- `state/provenance.jsonl` maps claims to source spans.
- `state/diagnostics.json` records evaluated coverage and failures.

Read vault content without modifying raw evidence. Route compilation, updates, repairs, publication, and verified learning through `expertctl` so schemas, provenance, atomic writes, and rollback remain intact.
