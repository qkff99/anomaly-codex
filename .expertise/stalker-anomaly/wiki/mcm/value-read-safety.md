---
id: mcm-value-read-safety
type: ui-safety
title: ui_mcm.get lifecycle safety
versions:
  - Anomaly MCM reference snapshot 81893aab42d0
---

# ui_mcm.get lifecycle safety

`ui_mcm.get(path)` reads an MCM option by its option-tree path and may be used when settings are applied. It must not run from `on_mcm_load()`: the MCM documentation says results can be unpredictable during option-table building, and the runtime asserts against that get because it can corrupt the table or settings file.
