# Mod Structure And Load Order

Use this reference when deciding where STALKER mod files belong, how Anomaly discovers scripts, or which initialization stage is safe for a given task.

## Canonical Resource Layout

- The game resolves resources through the game root, and `gamedata/` overrides packed `db` resources when the same file exists in both places.
- A local mod project should usually mirror that tree under its own root:
  - `projects/<project-name>/gamedata/scripts`
  - `projects/<project-name>/gamedata/configs`
  - `projects/<project-name>/gamedata/textures`
  - `projects/<project-name>/gamedata/sounds`
  - `projects/<project-name>/gamedata/meshes`
- Use `ai_workspace/vanilla scripts/gamedata` as the baseline for file placement and naming.

## Script Discovery

- `.script` files under `gamedata/scripts` are part of the engine script surface.
- The script engine sets up auto-load behavior for `_G`, so script modules can be loaded on demand when referenced by name.
- Anomaly startup also scans `$game_scripts$` and calls `module.on_game_start()` for scripts that expose it.
- Practical rule: a gameplay script placed in `gamedata/scripts` does not need a central registry just to be discoverable.
- Helper libraries can stay dormant until `require(...)` or another script references them.

## What Goes Where

- Put gameplay callback modules, binders, managers, and script-side integration code in `gamedata/scripts`.
- Put gameplay tuning, logic sections, items, smart terrain data, and UI XML in `gamedata/configs`.
- Put MCM XML and related localization under the config/UI localization tree, not in script-only folders.
- Put textures, sounds, meshes, animations, and other content in the matching asset folders instead of inventing new layout conventions.

## Initialization Stages

- Root scope:
  - good for locals, helper functions, constants, and optional `AddScriptCallback(...)`
  - unsafe for `db.actor`, `level`, spawned objects, and gameplay UI assumptions
- `on_game_start`:
  - scripts are loaded
  - use it for `RegisterScriptCallback(...)`, monkey-patch setup, and lightweight module init
  - do not assume the gameplay world is ready
- `main_menu_on_init` and menu callbacks:
  - use only for menu/UI behavior
  - gameplay-world state is not the right assumption here
- `on_game_load`:
  - good for load-time reinit and binder-related restore
  - still not the safest point for first-time world-object work
- `actor_on_first_update`:
  - preferred first one-shot hook for logic that needs the actor, world objects, or in-game services
  - use this instead of `on_game_start` for messages, inventory/world mutations, or actor-dependent initialization
- `actor_on_update`:
  - almost per-frame
  - only use when a more specific callback is not sufficient

## Decision Rules

- Need the script to be found by the game: place it in `gamedata/scripts`.
- Need callbacks to exist before registration: register in `on_game_start`.
- Need `db.actor`, live objects, or world-dependent services: defer to `actor_on_first_update` or a later gameplay callback.
- Need menu-only UI logic: use `main_menu_on_init` or related menu callbacks.
- Need save/load restore: combine the proper save/load surfaces with `on_game_load`, then validate on an actual load cycle.

## Verify Against Local Sources

- `ai_workspace/anomaly-modding-book-main/docs/getting-started/main-folders-and-files.md`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/wetting-hands.md`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/callbacks.md`
- `ai_workspace/vanilla scripts/gamedata/scripts/_g.script`
- `ai_workspace/vanilla scripts/gamedata/scripts/axr_main.script`
- `ai_workspace/src/xrServerEntities/script_engine.cpp`
- `ai_workspace/src/xrGame/alife_simulator.cpp`
