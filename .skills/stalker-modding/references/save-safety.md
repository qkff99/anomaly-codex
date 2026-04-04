# Save Safety

Use this file before touching persistence, long-lived manager state, binder state, or delayed runtime flows.

## Safe Defaults

- store plain Lua scalars and tables
- version serialized state explicitly
- rebuild transient runtime caches after load
- keep missing data recovery deterministic

## Avoid

- engine userdata
- live game objects or server objects in serialized state
- closures, functions, coroutines, or anything environment-bound
- unbounded historical tables

## Recommended Pattern

1. Keep a clear save schema table.
2. Include a version field.
3. Load defensively and migrate if needed.
4. Reconstruct transient or cached data in a post-load path.

## High-Risk Symptoms

- "works until save/load"
- object ids restored without revalidation
- delayed calls surviving across load assumptions
- manager tables that grow across play sessions

## Review Checklist

- is every saved field serializable
- does load tolerate missing keys and old versions
- are object ids revalidated before use
- are runtime-only tables rebuilt rather than restored blindly
- is the save schema focused and documented

## Manual QA

- fresh game start
- first update after load
- save and immediate load
- save during subsystem-active state
- level transition if relevant
