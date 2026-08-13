# Expertise Compiler

Expertise Compiler turns local repositories and documents into an inspectable Markdown/JSONL vault and a reusable Agent Skill. Retrieval is lexical and graph-based: there are no embeddings, model API calls, servers, or background processes.

## Quick start

```powershell
pipx install .
expertctl init example-domain --goal-file competency-request.md
expertctl add example-domain ./source-repo ./manual.md https://example.com/article
expertctl scan example-domain
expertctl compile-plan example-domain
```

If the competency is defined but the user has not supplied enough sources, create a pre-build research bundle instead of guessing URLs:

```powershell
expertctl research-plan example-domain
# The active agent searches the Internet and writes expected-output/source-manifest.json.
expertctl apply-research example-domain path/to/source-manifest.json
expertctl scan example-domain
expertctl compile-plan example-domain
```

`expertctl` does not call a search provider or model. The active agent performs the research; `apply-research` validates public HTTPS candidates, records why they were selected, and snapshots them through the same untrusted-source pipeline as `add`. The manifest must map every mandatory competency requirement to `covered`, `partial`, or an explicit `gap`; source `covers` fields reference those requirement IDs. Once a research task exists, `compile-plan` refuses to continue until its latest coverage matrix is applied and internally consistent.

`compile-plan` creates an extraction bundle under `.expertise/example-domain/state/tasks/`. The active coding agent reads `TASK.md`, writes its schema-bound `build.json`, and applies it. Extraction publishes nothing; `apply-build` returns the path of a synthesis bundle. Process and apply that second bundle to publish the Wiki:

```powershell
expertctl apply-build example-domain path/to/extraction-output
# Read next_task from the command result, produce its expected output, then:
expertctl apply-build example-domain path/to/synthesis-output
expertctl doctor example-domain
expertctl install-skill example-domain --agent codex
```

To make a Codex repository consult the compiled Wiki on every task, install the project harness after the vault is healthy:

```powershell
expertctl install-harness example-domain --project .
```

This installs the runtime skill in `.agents/skills/` and an idempotent managed block in the existing `AGENTS.md`. The active Codex agent must obtain an evidence pack before repository decisions; it may research directly or use whichever subagent mechanism the current host supports. The harness never creates a custom agent or fixes a subagent model, reasoning level, or lifecycle. No daemon or background plugin process is installed. Start a new Codex thread after installation.

At runtime the generated skill follows `route → search → traverse → verify → answer`. Useful inspection commands include `status`, `search`, `symbol`, `neighbors`, `path`, `context`, `read-page`, and `read-source`.

Each semantic phase accepts exactly one `build.json`. Every factual paragraph must be mapped through `claims` to immutable raw spans; publication requires at least 95% paragraph coverage and lexical support from the cited evidence. Accepted Wiki, provenance, diagnostics, candidates, recipe ledger, and source content identities are bound by a publication manifest. Pending updates or a manifest mismatch make the vault non-fresh and block retrieval until compilation completes.

## Hermes plugin

Install as a native Hermes plugin so the builder skill loads as `expertise-compiler:expertise-compiler`:

```powershell
expertctl install-hermes-plugin
# or from a source checkout:
expertctl install-hermes-plugin --plugin-root .
```

This copies `.hermes-plugin/` into `$HERMES_HOME/plugins/expertise-compiler/`. Restart Hermes (or run `/reload`) and the plugin auto-registers. The skill is opt-in (explicit load only) — it does not appear in the system prompt's skill index and never activates automatically, preserving the vault invariant of no background processes.

To use it in a Hermes session:

```
hermes --skills expertise-compiler:expertise-compiler
```

For the simpler skill-only install (no plugin wrapper, copies into `~/.hermes/skills/`):

```powershell
expertctl install-builder-skill --agent hermes
```

## Trust boundary

Imported sources are untrusted data. The tool snapshots and scans them but never executes their code, setup scripts, hooks, or embedded instructions. HTTP downloads resolve and connect to a validated public IP for every redirect. Remote Git clones require explicit HTTPS Git URLs on GitHub, GitLab, or Bitbucket; local Git repositories remain supported. Important Wiki claims must resolve to immutable raw source spans before publication. Raw-only PDFs remain ingestible but cannot support verified page citations without a reliable converter/page map.

Python 3.11+ and Git are the only core requirements. Document conversion, richer web extraction, and Tree-sitter parsing are optional extras.
