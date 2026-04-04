# Localization And Encodings

Use this file when a task touches string tables, UI text keys, translated item names, language switching, or legacy XML encodings.

## Vanilla Localization Layout

- Active language lives in `gamedata/configs/localization.ltx` under `[string_table] language = ...`.
- String-table XML files live in `gamedata/configs/text/<language>/*.xml`.
- Vanilla Russian files under `configs/text/rus` are commonly declared as `encoding="windows-1251"`.
- A typical localization file looks like:
  - root tag: `string_table`
  - entries: `<string id="some_key"><text>Localized text</text></string>`

## How The Engine Reads It

- `CStringTable::Init()` reads the active language from `localization.ltx`.
- It loads `text/<lang>/*.xml` through `CUIXml`.
- `CStringTable::Load()` reads each `<string id="...">` entry and stores the `<text>` value in the runtime string table.
- UI XML and gameplay code resolve keys through `CStringTable().translate(...)`.
- `ReloadLanguage()` rebuilds the table and refreshes active UI surfaces.

## Where Localization Keys Are Used

- UI XML:
  - `<text>st_some_key</text>` is translated by `CUIXmlInit::InitText(...)`
- LTX/config fields:
  - `inv_name`
  - `inv_name_short`
  - `text`
  - `hint`
- Scripts and C++:
  - direct `CStringTable().translate("st_some_key")`
- Runtime refresh:
  - `on_localization_change` is the script callback to refresh cached translated text

## Encoding Rules

- Do not assume `.xml` means UTF-8 in STALKER work.
- For Russian vanilla localization XML, assume `windows-1251` unless inspection shows otherwise.
- The XML declaration matters: TinyXML treats `UTF-8` declarations as UTF-8 and other declarations as legacy encoding.
- Saving a cp1251 file as UTF-8 without fixing the declaration, or editing it as raw UTF-8 while leaving `windows-1251`, is a mojibake trap.
- Conversely, saving a `windows-1251` file with characters not representable in cp1251 will fail or corrupt the text.

## Safe Editing Workflow

Use the helper instead of editing legacy-encoded XML blind.

- Inspect:
  - `python3 ./.skills/stalker-modding/scripts/xml_localization_tool.py inspect path/to/file.xml`
- Convert to UTF-8 for editing:
  - `python3 ./.skills/stalker-modding/scripts/xml_localization_tool.py prepare-edit path/to/file.xml`
- Edit the file normally.
- Restore original encoding:
  - `python3 ./.skills/stalker-modding/scripts/xml_localization_tool.py finish-edit path/to/file.xml`

PowerShell equivalents:
- `py -3 .\.skills\stalker-modding\scripts\xml_localization_tool.py inspect path\to\file.xml`
- `py -3 .\.skills\stalker-modding\scripts\xml_localization_tool.py prepare-edit path\to\file.xml`
- `py -3 .\.skills\stalker-modding\scripts\xml_localization_tool.py finish-edit path\to\file.xml`

## Decision Rules

- Need to add or change a translation string: edit the matching file under `configs/text/<language>/`.
- Need a new UI caption: add a string-table id and reference that id from UI XML.
- Need to localize an item, quest, or hint: trace the config key first, then update the right `st_*.xml` or `ui_st_*.xml`.
- Need to search by Cyrillic content: prefer encoding-aware helpers over raw byte-oriented grep.
- Need to change language-sensitive cached UI text: look for `on_localization_change`.

## Verify Against Local Sources

- `ai_workspace/vanilla scripts/gamedata/configs/localization.ltx`
- `ai_workspace/vanilla scripts/gamedata/configs/text/rus/*.xml`
- `ai_workspace/src/xrGame/string_table.cpp`
- `ai_workspace/src/xrGame/ui/UIXmlInit.cpp`
- `ai_workspace/src/xrXMLParser/xrXMLParser.cpp`
- `ai_workspace/src/xrXMLParser/tinyxmlparser.cpp`
