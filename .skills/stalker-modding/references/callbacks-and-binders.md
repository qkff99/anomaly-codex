# Callbacks And Binders

Use this file for subsystem mapping, event tracing, actor or weapon lifecycle work, and review of runtime coupling.

## What To Look For

- `RegisterScriptCallback`
- `UnregisterScriptCallback`
- binder `init` functions that call `bind_object`
- classes derived from `object_binder`
- class registrators
- UI delayed attach hooks
- monkey patches that wrap callback dispatch

## Search Strategy

Local search first:
- `scripts/find_entrypoints.sh`
- `rg "RegisterScriptCallback|bind_object|object_binder|class_registrator|delayed_attach"`

Remote search when local context is incomplete:
- `xray-monolith` for added callbacks or modded exes behavior
- DeepWiki for path discovery

## Binder Rules

- treat binder state as runtime state first, persistence state second
- keep update work bounded
- separate config load from runtime mutation
- prefer explicit reset methods over scattered flag resets

## Callback Rules

- callback order may differ across patches or wrappers
- callback arguments can be broader in modded exes than in vanilla
- check local call sites before assuming a callback is vanilla-only

## Callback Staging

- Root scope:
  - declare locals, helpers, constants, and optional `AddScriptCallback(...)`
  - do not touch `db.actor`, `level`, spawned objects, or world-bound UI here
- `on_game_start`:
  - best place to call `RegisterScriptCallback(...)`
  - safe for lightweight module init and patch wiring
  - not a safe place to assume the actor, level, or gameplay world already exists
- `main_menu_on_init` and related menu hooks:
  - use for menu UI and menu-adjacent behavior only
  - do not wire gameplay-world logic here unless it is explicitly menu-safe
- `on_game_load`:
  - useful for load-time restore and binder-adjacent state reinit
  - do not assume every world object is already spawned
- `actor_on_first_update`:
  - preferred first hook for one-shot in-world initialization
  - use this for logic that needs `db.actor`, actor inventory, messages, world objects, or other live gameplay services
- `actor_on_update`:
  - almost per-frame
  - keep the body minimal and budgeted

## Review Checklist

- does this callback run on a hot path
- can any object argument be nil or stale
- is there save/load state tied to callback-driven logic
- does this change introduce duplicate registration or missed unregister
- does it conflict with visible-body, HUD, or UI attach flows

## Common Conflict Zones

- actor weapon callbacks vs custom HUD or weapon scripts
- body or legs rendering vs active item transforms
- UI delayed attach vs MCM or script-created widgets
- time events vs save/load and reload timing
