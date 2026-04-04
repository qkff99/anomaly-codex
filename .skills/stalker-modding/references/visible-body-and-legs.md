# Visible Body And Legs

Use this file for first-person body, legs rendering, outfit visual switching, freelook, crouch, ladder, and attachment conflicts.

## Common Conflict Surfaces

- active item transforms vs body model transforms
- outfit visual swaps and HD model branches
- low crouch, ladder, freelook, sprint, or camera mode transitions
- attachment shadows, torch or bolt offsets, and shadowmap-specific behavior

## What To Verify

- which script owns legs or body spawning and updates
- which sections identify dummy body objects or visuals
- whether engine patches from modded exes are expected
- whether active items are repositioned by both the weapon system and body system

## Search Hints

- `legs`
- `visible_body`
- `outfit`
- `freelook`
- `low_crouch`
- `ladder`

## Checklist

- inspect runtime state transitions
- inspect section or visual-name heuristics
- test with sprint, crouch, ladder, aim, death, save/load
- look for hot loops and object lookups in update

## When To Use Engine Refs

Use `xray-monolith` when the workspace depends on modded exes legs behavior, first-person body rendering changes, HUD bone changes, or debug helpers that do not exist in vanilla.
