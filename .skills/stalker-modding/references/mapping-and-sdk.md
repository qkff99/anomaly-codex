# Mapping And SDK

This is a curated lookup guide for V1. Use it when the task touches levels, SDK workflows, compiled assets, or map-side file formats.

## Best Sources

- local project files and tool outputs
- `anomaly-modding-book` mapping tutorials and file-format references
- local engine source for capability or format-adjacent behavior

## Common Topic Areas

- level compile and decompile workflow
- AI map and graph-related formats
- terrain, HOM, SOM, CFORM and level binaries
- material and sound environment setup
- SDK project files and exported asset expectations

## Fast Routing

- "How do I build or decompile a level?" -> `anomaly-modding-book`
- "What is this level file format?" -> file-format refs in `anomaly-modding-book`
- "Does the engine support this behavior?" -> local engine source or `xray-monolith`

## Common Failure Modes

- treating generated binaries as hand-edited sources
- changing map-side assets without corresponding config or material updates
- assuming Anomaly-specific packaging rules are universal across all XRay branches
