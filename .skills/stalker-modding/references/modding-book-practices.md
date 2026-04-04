# Modding Book Practices

Use this file when the task needs workflow defaults, Lua modding patterns, or compatibility-first guidance derived from the local anomaly-modding-book.

## Core Defaults

- Start from vanilla behavior and local references before inventing a custom pattern.
- Prefer small, focused scripts over large cross-cutting rewrites.
- Use global search on the vanilla codebase to find how a subsystem already works before extending it.
- Treat anomaly-modding-book as a workflow and file-format guide first, not as the final authority on engine semantics.

## Lua Coding Patterns

- Keep module-scope state narrow and intentional.
- Prefer `local` variables for module-private state and helpers.
- Avoid creating accidental globals.
- Do not collide with engine globals or names exported by `lua_help.script`.
- Use `RegisterScriptCallback(...)` rather than wiring directly into callback tables.
- Add your own callbacks with `AddScriptCallback(...)` only when existing ones are not enough.
- Prefix custom callback names so they do not collide with other addons.

## Runtime Patterns

- `on_game_start` is for callback registration and lightweight startup work.
- `actor_on_first_update` is the first normal one-shot hook for actor/world-dependent logic.
- `actor_on_update` is expensive and should be treated as an exception path, not the default design.
- If persistence matters, design `save_state` and `load_state` deliberately instead of hoping runtime state will survive.

## Compatibility Patterns

- Prefer existing callbacks over monkey patching.
- Prefer monkey patching over direct script replacement only when a callback route does not exist.
- If monkey patching is required:
  - save the original function first
  - patch narrowly
  - document the conflict surface
  - remember that load order matters
- Watch for `local` functions and variables when considering a patch strategy.

## Modding Style The Book Encourages

- Event-driven logic over polling
- Differential changes over file replacement
- Reuse of vanilla helpers over full subsystem rewrites
- Search and trace first, patch second
- Compatibility-first thinking for distributable addons

## High-Value Topics From The Book

- callbacks and callback staging
- monkey patching as a fallback, not a default
- codebase orientation through `_g.script`, `lua_help.script`, and `axr_main.script`
- localization XML structure and encoding
- DXML for XML diffs
- DLTX for `.ltx` diffs

## Verify Against Local Sources

- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/README.md`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/wetting-hands.md`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/codebase-introduction.md`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/callbacks.md`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/monkey-patching.md`
