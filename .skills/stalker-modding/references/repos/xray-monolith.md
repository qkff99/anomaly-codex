# Repo Profile: xray-monolith

Repository:
- `themrdemonized/xray-monolith`

Use this repo as the online authority for:
- Modded Exes behavior
- engine capability lookup
- additional callbacks and exported helpers
- engine-side fixes touching HUD, legs, save safety, debug helpers, and performance patches

## Best Questions For This Repo

- Which files implement or expose a callback, command, or helper
- Whether a Modded Exes feature exists and where it is described
- What engine patch likely affects a runtime symptom
- Which engine-side changes are relevant to visible body, HUD, or update safety

## Do Not Use As Primary Truth For

- the current workspace behavior when local code differs
- tutorial guidance
- broad modding onboarding

## Preferred Access Pattern

1. local code or engine source if present
2. `xray-monolith` code search for targeted file discovery
3. `fetch_xray_monolith_documentation` for README, changelog, and feature summaries
4. generic fetch with `raw.githubusercontent.com/...` when a specific file such as `DXML.md` or `lua_help_ex.script` must be read
5. DeepWiki for repo map if necessary

## Tool Caveats

- Prefer raw GitHub URLs over `github.com/.../blob/...` when using generic fetch; blob URLs return GitHub page chrome instead of clean file content.
- Treat `search_xray_monolith_docs` as opportunistic, not authoritative. It can return README fallback text or time out on narrow queries.
- If doc search is weak, switch to code search plus raw file fetch instead of retrying the same query repeatedly.

## High-Value Search Themes

- callbacks
- `lua_help_ex`
- legs
- HUD
- time events
- save or load safety
- debug renderer or debug HUD
