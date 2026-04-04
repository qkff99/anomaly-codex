# DXML And DLTX

Use this file when deciding whether a mod should patch XML or LTX differentially instead of replacing whole files.

## Why These Matter

- DXML and DLTX exist to reduce addon conflicts.
- Both are Modded Exes features, not generic vanilla assumptions.
- Their value is mostly compatibility: patch only what changed instead of shipping a full replacement file.

## DXML

- DXML intercepts XML before engine or scripts consume it, exposes a Lua-side XML object, then returns the modified XML.
- Use DXML when the real job is:
  - inserting XML nodes
  - modifying XML text
  - changing or removing XML attributes
  - augmenting existing XML layouts or gameplay XML without replacing the file
- Typical DXML flow:
  - create `modxml_<name>.script`
  - register `on_xml_read`
  - check `xml_file_name`
  - query or modify `xml_obj`
- DXML supports:
  - `insertFromXMLString`
  - `insertFromXMLFile`
  - `query(...)` with CSS-like selectors
  - `getText` / `setText`
  - `setElementAttr` / `removeElementAttr`
- DXML-specific habits:
  - check whether the target node already exists before inserting
  - patch the smallest possible XML surface
  - do not assume every XML file is equally supported
- Important limitation from the book:
  - generic `character_desc_general.xml` handling goes through dedicated callbacks like `on_specific_character_init` and `on_specific_character_dialog_list`

## DLTX

- DLTX is differential loading for `.ltx` configs.
- Use DLTX when the real job is:
  - overriding one or a few fields in an existing section
  - deleting fields or sections
  - adding or removing items from CSV-style lists
  - augmenting inheritance without replacing a whole config file
- Prefer DLTX over full-file LTX overrides when Modded Exes are available.
- Standard workflow:
  - find the root LTX file
  - create `mod_<root>_<unique_suffix>.ltx`
  - express only the diff
- High-value syntax:
  - `![section]` section override
  - `!![section]` section deletion
  - `@[section]` create or override section
  - `!field` delete field
  - `>field = ...` add CSV items
  - `<field = ...` remove CSV items
- DLTX habits:
  - do not restate unchanged parents or unchanged CSV contents
  - keep the patch minimal and readable
  - use a unique suffix so addon filenames do not collide

## Decision Rules

- Need to change XML structure without replacing the file: prefer DXML.
- Need to change `.ltx` values without replacing the file: prefer DLTX.
- Need plain Lua runtime behavior and an existing callback can do it: prefer callbacks over both.
- Need to intercept Lua function flow because no clean extension point exists: consider monkey patching after DXML/DLTX have been ruled out.
- If the target environment might not have Modded Exes, explicitly call out that DXML or DLTX is an environment requirement.

## Compatibility Guidance

- DXML and DLTX reduce conflict risk, but they do not make incompatible edits magically compatible.
- Narrow patches still need conflict review if two addons change the same node, same field, or same runtime flow.
- Differential patching is the default compatibility-first choice for distributable addons on Modded Exes.

## Verify Against Local Sources

- `ai_workspace/anomaly-modding-book-main/docs/tutorials/addons/dxml.md`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/addons/dltx.mdx`
- `ai_workspace/anomaly-modding-book-main/docs/tutorials/scripting/monkey-patching.md`
