# Source Priority

Use the smallest sufficient source tier. Higher tiers are not always better; they are often noisier or less trustworthy for the current workspace.

## Tier Order

1. Local workspace
2. Local vanilla references
3. Local Lua API export
4. Local engine source
5. Indexed repo context such as DeepWiki
6. Live repo references such as GitMCP
7. External web

## Tier Rules

### 1. Local Workspace

Use first for:
- bugfixes, refactors, config tweaks, reviews, and conflict analysis
- naming, conventions, active module boundaries, and real behavior

Do not skip this tier when the task is about the current codebase.

### 2. Local Vanilla References

Use for:
- baseline behavior
- narrow diffs versus Anomaly defaults
- confirming whether a patch is actually needed

Treat vanilla as the preferred fallback when the workspace is a patch layer.

### 3. Local Lua API Export

Use for:
- checking whether a symbol is actually exported
- confirming rough argument surface before guessing

Do not treat exported presence as proof of exact runtime semantics.

### 4. Local Engine Source

Use for:
- engine capability lookup
- C++ side behavior, console commands, exposed functions, safety assumptions
- cases where Lua or config docs are incomplete

Prefer this over tutorial material when behavior matters.

### 5. Indexed Repo Context

Use for:
- subsystem mapping
- file discovery
- tracing unfamiliar architecture

Treat as a map, not final truth.

### 6. Live Repo References

Use for:
- `xray-monolith` engine and Modded Exes behavior
- `anomaly-modding-book` tutorials, file formats, and onboarding material
- `modorganizer2` MO2 directory layout, VFS behavior, and distribution assumptions

Verify actionable claims locally whenever possible.

For `xray-monolith` specifically:
- prefer code search for file discovery and callback surfaces
- prefer repo documentation fetch for changelog and feature summaries
- prefer raw GitHub file URLs for generic file fetches instead of `github.com/.../blob/...`

### 7. External Web

Use only when:
- the needed information is absent from local refs, indexed repos, and live repo refs
- the user explicitly wants broader ecosystem context

Mark confidence as lower and distinguish fact from inference.

## Fast Decisions

- Workspace bug or review -> local workspace first
- "How does vanilla do this?" -> local vanilla
- "Is this function exported?" -> local Lua API export
- "Can the engine do this?" -> local engine source, then `xray-monolith`
- "How do I set this up?" -> `anomaly-modding-book`
- "How should this be packaged for MO2?" -> `modorganizer2`, then local packaging refs
- "What files implement this subsystem?" -> DeepWiki, then local verification

## Investigation Record

For a code-path or architecture answer, keep the record narrow and auditable:

- Start with the requested symbol, file, callback, or config hook; trace it to the applicable entry point and record reachability conditions plus the source of controlling data.
- Group findings by runtime subsystem (`engine runtime`, `Lua bindings`, `ALife`, `UI/MCM`, `configs`, `save/load`) rather than by C++ versus Lua alone.
- Separate structural edges (include, import, call) from semantic edges (registration, object construction, state mutation, save/load, callback dispatch).
- Mark claims as `verified fact`, `inference`, or `unknown`. Dynamic registrations, string lookups, factories, virtual dispatch, macros, Lua auto-discovery, callback tables, and configuration hooks remain `unknown` until their execution path is verified.
- An absent direct text call is not proof that an export, callback, virtual method, factory product, or script module is unused.
- For C++ navigation, LSP, or static analysis, lower confidence when the actual compile database/toolchain is unavailable; never present unparseable translation-unit diagnostics as findings.

## Failure Modes

- Tutorial repo contradicts engine source: trust local engine source
- Indexed answer names a path missing locally: treat it as a hint and verify
- No local refs exist: degrade to repo-first mode and say confidence is reduced
