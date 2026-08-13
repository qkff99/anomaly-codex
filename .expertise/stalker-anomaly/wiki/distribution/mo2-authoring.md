---
id: mo2-authoring-layout
type: distribution-workflow
title: MO2 authoring and packaging layout
versions:
  - workspace policy for Anomaly 1.5.3 + Modded Exes
---

# MO2 authoring and packaging layout

Author a local project under `projects/<project-name>/gamedata/...` before packaging it as a loose overlay or FOMOD. Mod Organizer 2 virtualizes the live game view: use `mods/` as an install target, keep `profiles/` as profile state, and do not treat `overwrite/` as the source of truth.
