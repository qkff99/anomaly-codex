# Tasks, Story, And A-Life

Use this file for task systems, story ids, spawn sections, squad and smart terrain work, and online/offline object boundaries.

## High-Risk Areas

- story id changes
- task functor or manager edits
- spawn section mismatches
- smart terrain and squad descriptor coupling
- online versus offline assumptions

## Rules

- keep ids stable unless the migration path is explicit
- prefer additive patches over rewriting broad descriptor sets
- confirm whether logic is task-layer, story-layer, or A-Life-layer before editing
- separate server object reasoning from online object reasoning

## Checklist

- locate authoritative config files
- locate script manager or functor entrypoints
- confirm whether change affects save compatibility
- test save/load and level transitions
- test task completion, fail path, and recovery path if applicable

## When To Load More

- load `save-safety.md` if ids or state persist
- load `runtime-model.md` if callbacks or managers are involved
- use `xray-monolith` for engine-level helper capability, not quest design rules
