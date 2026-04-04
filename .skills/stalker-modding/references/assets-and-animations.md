# Assets And Animations

This is a curated lookup guide for V1. Use it to decide where to search, not as a complete procedural reference.

## Best Sources

- local workspace assets and config references
- `anomaly-modding-book` for file formats, skeletons, HUD animation docs, Blender workflows
- `xray-monolith` for engine-side animation fixes or exported behavior affecting first-person assets

## High-Value Topics

- HUD hands animations
- motion marks
- skeleton and bone naming
- OMF, SKL, SKLS, OGF, DDS, THM, PE and related file formats
- icon atlases and texture preparation

## Fast Routing

- first-person weapon or detector hands -> HUD animation refs and `weapons-and-hud.md`
- body model or outfit visuals -> `visible-body-and-legs.md`
- raw format question -> `anomaly-modding-book` file-format references
- engine playback or export behavior -> `xray-monolith` or local engine source

## Common Failure Modes

- mismatched animation names between config and asset
- wrong skeleton or bone expectations
- asset-side edits that need config updates but did not get them
- assuming engine playback bugs are asset bugs

## Recommended Follow-Up References

- `references/weapons-and-hud.md`
- `references/visible-body-and-legs.md`
- `references/repos/anomaly-modding-book.md`
- `references/repos/xray-monolith.md`
