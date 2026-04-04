# Repo Profile: anomaly-modding-book

Repository:
- `TheParaziT/anomaly-modding-book`

Use this repo as the online authority for:
- onboarding and modding workflow guidance
- file formats
- tutorials
- scripting introductions and curated references
- mapping, animation, texture, SDK, and addon setup guides
- compatibility-first addon patterns such as callbacks, DXML, DLTX, and narrow monkey patches

## Best Questions For This Repo

- how to approach a modding workflow
- where to find reference docs for a format or subsystem
- what files or concepts matter for a tutorial-style task
- which modding tools or workflows are commonly used
- whether a change should be a callback, a DXML patch, a DLTX patch, or only then a monkey patch

## Do Not Use As Primary Truth For

- exact engine runtime semantics when local engine source says otherwise
- the current workspace behavior when local code differs

## Preferred Access Pattern

1. local workspace and local refs when the task is project-specific
2. `anomaly-modding-book` GitMCP for tutorial, format, or workflow lookups
3. DeepWiki only if repo-level mapping is useful

## High-Value Search Themes

- callbacks
- callback staging such as `on_game_start` versus `actor_on_first_update`
- `_g.script`, `lua_help.script`, and `axr_main.script` as codebase orientation files
- monkey patching tradeoffs and limits
- DXML
- DLTX
- time events
- script animations
- MCM
- file formats
- HUD animations
- level compile and SDK workflows
