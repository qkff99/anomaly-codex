# Engine Quirks

Use this file to avoid overconfident assumptions about XRay runtime behavior.

## Practical Quirks

- object availability is timing-sensitive
- online objects and server objects have different lifecycles
- callback surfaces may be extended by modded exes or monkey patches
- UI lifecycle is not the same as gameplay lifecycle
- save/load often breaks assumptions that looked fine in a single session
- engine-exposed helpers may exist without clear tutorial coverage

## Defensive Rules

- verify object validity close to use sites
- treat callback signatures as environment-sensitive until confirmed
- do not infer exact order from one script example
- rebuild transient state after load
- verify engine capability in local source or `xray-monolith` before promising behavior

## Good Habits

- compare with local vanilla when patching
- keep fallbacks explicit
- prefer versioned state over implicit compatibility
- keep debug output targeted and removable

## Escalation Triggers

If any of these appear, stop guessing and verify:
- nil or destroyed object errors
- behavior changes only after save/load
- modded exes specific callbacks or console commands
- body, HUD, or animation behavior differing from vanilla expectations
