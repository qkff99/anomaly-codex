# Runtime Model

Use this reference when the task touches execution flow, persistence, update paths, or subsystem boundaries.

## Main Runtime Surfaces

- `gamedata` resource overlay and script auto-load
- script load order and globals
- startup callbacks and session bootstrap
- script callbacks
- object binders
- class registrators and scheme registrators
- UI attach and delayed attach paths
- time events and next-tick style deferrals
- save/load callbacks and serialized state
- engine-exported functions and console commands

## Typical Control Flow

1. Engine initializes the script VM, exported globals, and `_G` auto-load behavior.
2. `_G.script` is processed early and exposes shared helpers such as `RegisterScriptCallback(...)`.
3. When a game session is started or loaded, the configured `start_game_callback` fires.
4. In Anomaly, `_G.start_game_callback()` forwards to `axr_main.on_game_start()`.
5. `axr_main.on_game_start()` scans `$game_scripts$` and calls each module `on_game_start()` handler it finds.
6. Load, binder init, reinit, and spawn-related work continues through `on_game_load`, binders, and other callbacks.
7. First truly actor/world-dependent one-shot logic should usually wait for `actor_on_first_update`.
8. Per-frame or scheduled updates then run through callbacks, binders, and managers.
9. Save and load surfaces serialize script state through callbacks or manager methods.

## High-Risk Areas

- actor update loops
- binder update methods
- UI code that re-attaches or recreates widgets often
- code that mixes server objects and online game objects
- state that spans callbacks, delayed calls, and save/load

## Practical Reading Order

For an unfamiliar subsystem:
1. Find entrypoints with `scripts/find_entrypoints.sh`
2. Map files with `scripts/map_subsystems.py`
3. Trace local callers and callees
4. Only then load repo references if needed

## Common Runtime Boundaries

- `on_game_start` means scripts are loaded, not that the gameplay world is ready
- `db.actor` and online game objects can be nil or stale at unsafe times
- server objects and online objects are not interchangeable
- menu callbacks are separate from in-world gameplay callbacks
- UI scripts can run before all widgets or game state are ready
- callbacks may be added by engine patches, modded exes, or monkey patches
- persistence must survive save/load without engine object references

## Failure Patterns

- doing actor- or world-dependent work directly in `on_game_start`
- treating menu callbacks as if a loaded level or actor must exist
- storing transient engine userdata in save state
- assuming callbacks always fire in vanilla order across modded exes
- full-table scans inside frequent updates
- treating tutorial pseudo-flow as exact runtime order

## Decision Rules

- If the issue smells like ordering, search entrypoints before editing logic
- If the logic needs the actor or live world objects, prefer `actor_on_first_update` or a later gameplay callback over `on_game_start`
- If the logic is menu-only, search `main_menu_*` callbacks rather than gameplay hooks
- If the issue is about where a file belongs, load `mod-structure-and-load-order.md`
- If the issue smells like persistence, load `save-safety.md`
- If the issue is per-frame or responsiveness related, load `performance-hotpaths.md`
