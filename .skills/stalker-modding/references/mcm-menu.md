# Anomaly MCM Menu

Use this file when a task touches Anomaly Mod Configuration Menu integration, option trees, MCM localization, keybind widgets, or MCM-specific UI behavior.

## Local Authority

- Primary local authority: `ai_workspace/Anomaly-Mod-Configuration-Menu-main`
- Start with:
  - `README.md`
  - `gamedata/scripts/ui_mcm.script`
  - `gamedata/scripts/ui_main_menu.script`
  - `gamedata/scripts/dph_mcm_save_storage.script`
  - `gamedata/configs/ui/ui_mcm_16.xml`
  - `gamedata/configs/text/<lang>/ui_st_mcm.xml`

## Integration Model

- A mod adds MCM support by shipping a script in `gamedata/scripts` whose filename ends with `mcm.script`.
- MCM scans `*mcm.script`, ignores `ui_mcm.script`, and calls `on_mcm_load()` on discovered modules.
- `on_mcm_load()` must return a valid options tree.
- It may also return a second string value for a collection name; that collection becomes the root for settings paths and localization naming, so it must be globally unique enough to avoid collisions.
- MCM also passes the current global options table into `on_mcm_load(options)`, but normal addon code should treat that as advanced behavior and prefer simply returning its own tree.

## Option Tree Rules

- The top-level `id` should be unique across the whole load order, not just inside the addon.
- Trees use nested `gr` tables and build settings paths from nested ids, joined by `/`.
- Typical option path: `root/group/option`.
- Supported option types include:
  - `check`, `list`, `input`, `radio_h`, `radio_v`, `track`, `key_bind`
- Support and formatting types include:
  - `line`, `image`, `slide`, `title`, `desc`
- Every real option needs `id`, `type`, and `val`.
- `key_bind` must use `val = 2`.

## Reading And Writing Settings

- MCM stores values under section `mcm` in `axr_options.ltx` unless the option uses command or custom functor behavior.
- Default path reader: `ui_mcm.get(path)`.
- `ui_mcm.get(path)` is cached and falls back to the option `def` value.
- Do not call `ui_mcm.get(...)` inside `on_mcm_load()`. MCM is still gathering the table there and `ui_mcm.get()` asserts on that path for safety.
- In MCM 1.7.0+, `ui_mcm.get()` returns `nil` for orphaned or unknown paths instead of reading garbage from `axr_options`.
- For simple settings, prefer `def` plus `ui_mcm.get(path)` over unnecessary functors.
- If MCM is optional, wrap reads with a fallback pattern such as `if ui_mcm then ... else ... end`.

## Apply And Callback Flow

- When the player clicks Apply, MCM writes pending values, executes option functors, and then sends callbacks.
- Standard Anomaly callback:
  - `on_option_change`, with `true` when the change came from MCM
- MCM-specific callbacks:
  - `mcm_option_change`
  - `mcm_option_reset`
  - `mcm_option_restore_default`
  - `mcm_option_discard`
- Prefer re-reading cached settings on apply via `on_option_change` or `mcm_option_change` instead of polling `ui_mcm.get()` in hot paths.

## Localization Rules

- In practice, use `gamedata/configs/text/<language>/*.xml` for MCM strings.
- Menu label for the root or collection:
  - `ui_mcm_menu_<root>`
- Default option label path:
  - `ui_mcm_<path_with_slashes_replaced_by_underscores>`
- Default tooltip path:
  - `ui_mcm_<path_with_slashes_replaced_by_underscores>_desc`
- List and radio captions typically use:
  - `ui_mcm_lst_<token>`
- `hint` overrides the default option label and tooltip naming, but it should be given without the `ui_mcm_` prefix and without `_desc`.
- If a string is missing, MCM shows the raw id.
- The local MCM repo uses mixed encodings:
  - `gamedata/configs/text/eng/ui_st_mcm.xml` is UTF-8
  - `gamedata/configs/text/rus/ui_st_mcm.xml` is `windows-1251` / `cp1251`
- Before editing Russian MCM XML, use `xml_localization_tool.py prepare-edit`, then `finish-edit` before finalizing.

## Keybind-Specific Rules

- MCM keybind values are DIK key codes.
- Keybinds are gathered into meta lists inside MCM, so names and tooltips must be descriptive outside the context of the addon's own menu branch.
- `curr` and `functor` are not supported for `key_bind`.
- Pre-1.6.0 MCM does not support `key_bind`; if backward compatibility matters, treat missing values carefully.
- MCM exposes helper utilities:
  - `ui_mcm.get_mod_key(val)`
  - `ui_mcm.double_tap(id, key, [multi_tap])`
  - `ui_mcm.key_hold(id, key, [repeat])`
  - `ui_mcm.simple_press(id, key, functor, ...)`
- Keyboard display names come from `gamedata/configs/mcm_key_localization.ltx`.
- If reported keys do not match the actual keyboard layout, that LTX may need adjustment.

## Save-Specific Storage

- Global storage is the default and is correct for most addons.
- For save-specific storage, use `ui_mcm.store_in_save(path)` or `dph_mcm_save_storage.register_module(path)`.
- `path` may be the full option path or a partial subtree path.
- It is safe to call `ui_mcm.store_in_save(path)` even if the helper script is absent; MCM falls back to an error print instead of a hard failure.
- If per-save behavior matters, register it in `on_game_start()` or another safe runtime stage, not through `ui_mcm.get()` inside `on_mcm_load()`.

## Advanced UI Hooks

- `ui_hook_functor` and `on_selection_functor` are advanced-only surfaces.
- `ui_hook_functor` runs during UI element registration and receives anchor, handlers, attrs, and flags.
- `on_selection_functor` runs on unsaved value changes and is suitable for live preview or UI reaction logic.
- These hooks are powerful but brittle. Use them only when the stock widget layout cannot express the behavior.
- Do not assume a monkey patch against MCM UI internals will survive version updates. The local changelog explicitly notes compatibility-breaking internal UI changes.

## Conflict Surface

- MCM itself integrates into the main menu by shipping:
  - `gamedata/scripts/ui_main_menu.script`
  - `gamedata/configs/ui/ui_mm_main.xml`
  - `gamedata/configs/ui/ui_mcm.xml`
  - textures and localization for the menu
- Mods that only want to expose settings should normally avoid editing `ui_main_menu.script` or `ui_mm_main.xml` directly.
- If a task touches MCM reskins or menu integration, treat MCM UI XML and textures as a compatibility-sensitive surface.
- The local changelog notes that MCM 1.7.2 changed the MCM UI and may break reskins.

## Practical Workflow

1. Keep the addon functional without MCM unless the feature truly requires MCM.
2. Add or update `*_mcm.script` with `on_mcm_load()`.
3. Keep root ids, collection names, and list tokens unique.
4. Add matching localization keys in `configs/text/<lang>/*.xml`.
5. Use `ui_mcm.get(path)` in runtime code, but never during `on_mcm_load()`.
6. Re-read settings on `on_option_change` or `mcm_option_change` instead of per-frame polling.
7. Use save-specific storage only when the feature truly needs per-save divergence.
8. If touching Russian MCM XML, round-trip through the XML encoding helper.
9. If the task is only “add settings UI”, avoid patching MCM internals, main menu internals, or MCM UI hooks.

## Verify Against Local Sources

- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/README.md`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/gamedata/scripts/ui_mcm.script`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/gamedata/scripts/ui_main_menu.script`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/gamedata/scripts/dph_mcm_save_storage.script`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/gamedata/scripts/modxml_mcm_rus.script`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/gamedata/configs/ui/ui_mcm_16.xml`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/gamedata/configs/text/eng/ui_st_mcm.xml`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/gamedata/configs/text/rus/ui_st_mcm.xml`
- `ai_workspace/Anomaly-Mod-Configuration-Menu-main/changelog`
