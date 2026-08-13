---
id: mcm-module-contract
type: ui-contract
title: MCM module on_mcm_load contract
versions:
  - Anomaly MCM reference snapshot 81893aab42d0
---

# MCM module on_mcm_load contract

An MCM-enabled mod supplies a `gamedata/scripts/*mcm.script` module whose `on_mcm_load()` defines and returns a valid options tree. The MCM loader discovers modules with that callback and calls `on_mcm_load(options)` while constructing the menu data.
