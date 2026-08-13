---
id: lua-api-orientation
type: api-reference
title: Lua API orientation map
versions:
  - exported local Lua API snapshot 4fd6a10f4be3
---

# Lua API orientation map

The exported Lua surface exposes the global entry points `game_graph()` and `alife()`. Its `alife_simulator` declaration includes object lookup, actor lookup, spawn, release, restrictions, and information-portion operations; use it as an API locator, then verify runtime semantics in vanilla scripts or engine source.
