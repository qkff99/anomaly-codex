---
id: runtime-actor-first-update
type: runtime-callback
title: actor_on_first_update callback
versions:
  - Anomaly 1.5.3 + Modded Exes
---

# actor_on_first_update callback

The vanilla callback registry includes both `actor_on_first_update` and `actor_on_update`. In this workbench, prefer `actor_on_first_update` for one-shot work that needs `db.actor`, spawned objects, or in-world services; reserve the repeating `actor_on_update` path for bounded hot-path work.
