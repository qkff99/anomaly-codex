# Performance Hot Paths

Use this file whenever the change touches actor updates, binder updates, UI-per-frame paths, or broad registries.

## Treat As Hot By Default

- `actor_on_update`
- binder `update`
- frequently-fired callbacks
- UI updates tied to frame or input
- registry scans over online or server object sets

## Rules

- avoid full scans each tick
- avoid growing tables without cleanup bounds
- cache repeated expensive checks for the current tick or small window
- prefer narrow candidate lists over world-wide searches
- clean incrementally, not in spikes

## Red Flags

- nested loops over object registries
- repeated config or ini reads in updates
- repeated string parsing in frame paths
- allocating large temporary tables every frame
- repeated object lookup by id when a validated cached id would work

## Safer Patterns

- scan at intervals
- early-return when feature inactive
- stage heavy work across frames
- use prefiltered ids or sections
- move discovery out of the hot callback into setup or refresh windows

## Review Checklist

- what is the max work per frame
- what is the trigger frequency
- can this path go inactive early
- can lookups be memoized safely
- can cleanup be bounded by count or age
