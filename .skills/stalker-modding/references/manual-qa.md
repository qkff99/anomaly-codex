# Manual QA

Use this file to build a tight manual test set instead of broad unfocused playtesting.

## Baseline Smoke

- run `luac` syntax check on touched `.lua` or `.script` files first
- game start does not crash
- scripts register and attach
- first actor update is clean
- console or log does not immediately show new nil errors

## Save-Related

- save and immediate load
- save while the feature is active
- reload after state transition
- verify no stale state or duplicated registration appears after load

## Weapons And HUD

- equip and unequip
- show and hide
- sprint, aim, fire, reload
- lowered weapon path if supported
- slot switching

## Visible Body And Legs

- crouch and low crouch
- sprint and stop
- ladder
- freelook if supported
- outfit switch if relevant

## UI And MCM

- open and close the UI
- change option values
- apply, reset, default, and discard pending MCM changes
- reload UI or reopen menu
- reopen MCM and verify persisted values and localization labels
- if keybinds were touched, verify bind, unbind, and visible conflict state
- if MCM is optional, verify the feature still behaves safely when `ui_mcm` is absent
- verify localization and missing widget behavior

## Tasks And A-Life

- mission acceptance or activation
- success and fail path if relevant
- level transition if relevant
- online/offline or spawn-sensitive flow if relevant
