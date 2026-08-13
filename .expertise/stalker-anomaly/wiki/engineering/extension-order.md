---
id: extension-order
type: engineering-policy
title: Compatibility-first extension order
versions:
  - workspace policy for Anomaly 1.5.3 + Modded Exes
---

# Compatibility-first extension order

Start with existing callbacks, configuration hooks, or vanilla extension points. Prefer DXML for XML diffs and DLTX for `.ltx` diffs on Modded Exes; use a narrow monkey patch only when needed, and use a full-file override as the last compatibility option.
