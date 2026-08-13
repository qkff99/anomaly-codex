# Artifact contracts

Read this reference when producing bundle output, reviewing a vault, or reconstructing a generated skill. Treat the packaged JSON Schemas and command output as authoritative for exact field types; use these contracts for meaning.

## Canonical layers

| Layer | Format | Contract |
| --- | --- | --- |
| Evidence | immutable raw files and snapshots | Final proof at a registered commit or content hash |
| Knowledge | Markdown | Human-readable derived pages with provenance |
| Machine state | JSON and JSONL | Registry, graph, aliases, provenance, tasks, diagnostics, and logs |
| Acceleration | gzip JSON or optional SQLite FTS5 | Rebuildable cache, never the only source of truth |

## Source record

Keep a stable `id`, `kind`, original `uri` or local origin, trust state, authority, retrieval time, raw path, and content hash. For Git, also keep repository URL, branch or tag, and exact commit. For web documents, keep the original URL and snapshot metadata. Default imported content to `trusted: false`.

## Source-discovery manifest

Follow the research bundle's `output-schema.json`. Record `phase`, locked `task_id`, executed `queries`, mandatory `coverage`, candidate `sources`, and unresolved `gaps`. Each coverage row has a stable `id`, requirement text, one or more references to the top-level queries, a diagnostic question, and `covered`, `partial`, or `gap` status. Every top-level query must belong to at least one row. Covered rows require a source; partial rows require a source and remaining gap; gap rows require no source and an explicit reason. Each source needs a public HTTPS `url`, selection `reason`, declared `authority` class, and nonempty `covers` containing coverage IDs; `version` and `license` are optional strings. The top-level `gaps` list must exactly match partial/gap reasons in coverage order. These fields describe the agent's selection and never upgrade the imported source from `trusted: false`.

## Candidate record

Keep `candidate_id`, canonical-name proposal, aliases, type, claims, symbols, source spans, versions, and related candidate IDs. Candidate output is intermediate and must not appear as published fact before global resolution.

## Wiki page

Keep stable page identity and routing metadata such as `id`, `title`, `type`, `summary`, aliases, tags, applicable repositories or versions, status, claim classes, source spans, related page IDs, and last verification time. Classify content as fact, inference, hypothesis, or verified recipe. Attach source spans to factual paragraphs rather than citing only at page level.

## Context pack

Return an explainable selection containing the route, pages, symbols, source spans, graph neighbors, version warnings, knowledge gaps, and suggested next reads. Respect the requested token budget. Do not place a generated answer in the pack.

## Verified recipe

Require a goal, applicability, changed files or symbols when relevant, ordered procedure, verification results, and evidence. Permit promotion only when `verification` and `evidence` are nonempty and correspond to a build, tests, target observation, direct source, reproduced fix, or explicit user confirmation. Direct-source evidence is materialized in provenance. If that source changes, keep the recipe pending until the same identity is reverified against current evidence or explicitly marked `historical`; append revisions with a `supersedes_sha256` chain.

## Task-bundle output

Follow the bundle's `output-schema.json` and emit exactly one `build.json`. Use stable identifiers from the inputs, preserve source-span coordinates, represent unresolved conflicts explicitly, and avoid unknown fields when the schema disallows them. Synthesis and repair pages need paragraph-numbered `claims`; the compiler binds each accepted paragraph hash to its canonical raw span and requires at least 95% coverage. A synthesis must preserve all accepted user diagnostics unless `retired_diagnostics` explicitly names a probe and records a specific reason.
