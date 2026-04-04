# Validation Prompts

Use these prompts to smoke-test whether the skill routes sources correctly and keeps claims grounded.

## Prompt Suite

1. Review this Anomaly Lua bugfix and tell me whether the change is save-safe.
2. Map the callbacks and binders involved in this HUD weapon behavior before proposing a fix.
3. Compare this custom script against vanilla and explain the smallest safe patch.
4. Explain whether Modded Exes adds a callback or helper for this feature, and cite the source tier used.
5. Diagnose a visible body or legs conflict with a custom weapon script.
6. Tell me how to set up an MCM option for this feature and what files need to stay aligned.
7. Explain how to approach this file-format or animation task and where to look first.
8. Analyze a mixed workspace with several mod prototypes and tell me which module looks active.

## Acceptance Signals

- source selection is explicit and sensible
- local code outranks generic references
- engine facts are not justified only by tutorial docs
- save and hot-path risks are called out when relevant
- missing local context is acknowledged instead of guessed away
