# Lua API Map

Use this file as a routing map, not as a replacement for exported API verification.

## Core Namespaces

- `db`: actor and storage access, high-value but nil-fragile
- `level`: current level operations, map, object lookup, camera helpers, input-adjacent helpers
- `alife()`: server-side and offline world surfaces
- `game`: UI-adjacent and gameplay helpers
- `device()`: camera and rendering-facing data
- `relation_registry`, `simboard`, manager globals: optional or mod-dependent surfaces

## Object Families

- `CScriptGameObject` style online objects
- server objects from A-Life or registries
- UI windows and statics
- vectors, matrices, physics shell, player HUD helpers

## Safe Usage Rules

- check object existence before method calls
- do not assume online and server surfaces share methods
- validate config values with `type` or `tonumber`
- prefer local aliases only in hot modules

## Verification Order

1. Search local code for current usage
2. Check local API export
3. Check local engine source or `xray-monolith` for behavior details

## Common Questions

- "Is this function exported?" -> local Lua API export
- "What args does this callback or method use?" -> local code first, then engine refs
- "Why is this object nil?" -> inspect lifecycle, callback timing, and online/offline boundary
