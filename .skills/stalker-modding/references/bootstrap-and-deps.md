# Tool Availability And Explicit Provisioning

Use this reference when a task needs a local helper, compiler, language server, or analyser that may be absent.

## Default Policy

Discover prerequisites before depending on them. Do not install, bootstrap, download, or reconfigure local tooling merely to orient in a repository or to make a check runnable.

Common optional tools:
- `python` for helper scripts
- `luac` 5.1 for Lua syntax and prototype-local-limit checks
- `rg` for fast search
- a matching C++ toolchain and compilation database for trustworthy cross-file diagnostics

## When A Tool Is Missing

1. State the missing prerequisite and which check could not run.
2. Use existing source inspection or another already available, lower-risk check where possible.
3. Mark the resulting confidence or validation gap in the outcome.
4. Offer the relevant bootstrap helper only if the user explicitly requests provisioning.

`bootstrap_env.sh` and `bootstrap_env.ps1` remain available as explicit opt-in helpers. If the user approves use of them, prefer Lua 5.1 for Anomaly and report any version mismatch before relying on the result.
