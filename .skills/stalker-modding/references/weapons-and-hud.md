# Weapons And HUD

Use this file for weapon behavior, HUD animation timing, debug HUD workflows, active item transforms, and zoom or fire state logic.

## Common Surfaces

- weapon scripts and item scripts
- HUD sections in configs
- animation names, marks, and state transitions
- zoom and fire callbacks
- debug HUD scripts or console tools
- active item offsets and custom camera or body interactions

## Common Risks

- active item and body model fighting over transforms
- mismatched animation states on show/hide, aim, sprint, reload
- wrong callback assumptions for zoom or fire behavior
- config drift between weapon section, HUD section, and localization or UI text

## Reading Order

1. active workspace weapon script
2. local vanilla weapon or HUD equivalent
3. local Lua API export for relevant methods
4. `xray-monolith` for added callbacks, HUD helpers, and engine-side fixes

## Checklist

- identify the authoritative weapon section and HUD section
- trace zoom, fire, reload, and hide/show entrypoints
- confirm whether debug HUD tools already exist
- test with weapon lowered, sprint, aim, and slot switches
- consider conflicts with visible body or legs systems

## Helpful External References

- `anomaly-modding-book` config references for HUD animation structures
- `xray-monolith` for added callbacks, debug helpers, and modded exes changes
