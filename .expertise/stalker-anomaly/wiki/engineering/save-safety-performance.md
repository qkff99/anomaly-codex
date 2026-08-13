---
id: runtime-safety-performance
type: engineering-policy
title: Save safety and hot-path limits
versions:
  - workspace policy for Anomaly 1.5.3 + Modded Exes
---

# Save safety and hot-path limits

Persistent state must remain serializable, engine-facing code must tolerate partial failure, and hot-path work must be bounded. Avoid unbounded scans in `actor_on_update` and do not store non-serializable engine objects in save state; use deterministic fallbacks when an optional system is absent.
