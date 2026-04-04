# UI XML And MCM

Use this file for UI scripts, XML layouts, menu integration, localization coupling, and MCM or options hooks.

For actual Anomaly MCM integration details, load `references/mcm-menu.md` as the primary reference and use this file as the shorter UI alignment checklist.

## Common Surfaces

- XML layout files
- UI scripts and delayed attach paths
- localization strings
- `configs/text/<lang>/*.xml` string-table files
- MCM registration and option keys
- dynamic UI elements created in script
- Anomaly MCM local authority repo: `ai_workspace/Anomaly-Mod-Configuration-Menu-main`

## Rules

- keep XML, script, and localization changes aligned
- keep localization ids stable across UI XML, LTX, scripts, and `configs/text/<lang>` string tables
- treat Russian localization XML as potentially `windows-1251`; use the XML localization helper before editing legacy-encoded files
- treat MCM as optional unless the project explicitly requires it
- for MCM, prefer adding a dedicated `*mcm.script` module and localization keys over editing `ui_main_menu.script` or `ui_mm_main.xml`
- do not assume UI widgets exist before attach or delayed attach completes
- avoid mandatory hard dependency on optional UI systems

## Review Checklist

- are XML ids and script lookups aligned
- are localization keys added or updated
- were legacy XML encodings preserved after editing
- does MCM registration match config keys and defaults
- can the feature run without MCM
- does delayed attach or repeated attach duplicate widgets or handlers

## Search Strategy

- local UI scripts and XML first
- then local vanilla equivalents
- for MCM-specific behavior, API, keybinds, or naming rules, load `references/mcm-menu.md` and inspect `ai_workspace/Anomaly-Mod-Configuration-Menu-main`
- for localization XML, load `references/localization-and-encodings.md`
- then `anomaly-modding-book` for MCM or XML workflow guidance
