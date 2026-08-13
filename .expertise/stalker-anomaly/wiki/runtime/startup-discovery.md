---
id: runtime-startup-discovery
type: runtime-lifecycle
title: on_game_start script discovery
versions:
  - Anomaly 1.5.3 + Modded Exes
---

# on_game_start script discovery

`axr_main.on_game_start()` calls `getFS():file_list_open_ex` for `*.script` under `$game_scripts$`, collects each `_G[file_name].on_game_start`, and calls each collected module after the scan. A normal startup module can therefore live in `gamedata/scripts/*.script`; treat this as early startup and defer world-dependent work until a later suitable callback.
