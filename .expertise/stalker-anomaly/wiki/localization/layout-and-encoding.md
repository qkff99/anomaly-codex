---
id: localization-encoding
type: localization-contract
title: Localization layout and legacy encoding
versions:
  - workspace policy for Anomaly 1.5.3 + Modded Exes
---

# Localization layout and legacy encoding

String-table localization belongs in `gamedata/configs/text/<language>/*.xml`, with the active language selected by `gamedata/configs/localization.ltx`. Legacy Russian XML is commonly `windows-1251`; inspect and round-trip its encoding through the localization helper instead of silently rewriting it as UTF-8.
