# Log Triage

Use this file when the task starts from a crash log, runtime error, syntax error, or a very large Anomaly/XRay log dump.

## Default Workflow

1. Prefer `scripts/log_triage.py summarize <log-or-dir>` before reading a giant raw log into context.
2. If the user uses MO2 and the log points at scripts, configs, or assets, prefer asking for the MO2 `mods/` path first. If the user does not use MO2, prefer unpacked `gamedata/`.
3. Remember external paths only when the user explicitly approves it.
4. Use a remembered `logs_dir` only when repeated "latest log" automation is actually useful for that user.
5. Use `scripts/log_triage.py extract ...` only when the compact summary is not enough.

## What The Parser Looks For

- Lua/runtime markers:
  - `SCRIPT RUNTIME ERROR`
  - `SCRIPT SYNTAX ERROR`
  - `SCRIPT ERROR (while running file)`
  - `SCRIPT ERROR (memory allocation)`
  - `! [SCRIPT ERROR]:`
  - `! [LUA]`, `* [LUA]`, `~ [LUA]`
  - `stack traceback:`
- Engine fatal markers:
  - `FATAL ERROR`
  - `Expression    :`
  - `Function      :`
  - `File          :`
  - `Line          :`
  - `Description   :`
  - `stack trace:`

## Expected Output

- kind of failure
- short headline
- primary script or source file
- line number when available
- top stack frames
- resolved local inspect points when engine stack frames match `ai_workspace/src`
- resolved local inspect points when Lua paths match `projects/*/gamedata`, workspace `gamedata`, vanilla refs, or remembered external mod roots
- suggested next search targets

## Practical Rules

- Treat log parsing as a context-reduction step, not a substitute for code tracing.
- After triage, search the reported script, callback, or helper name in local refs with `find_references.py`.
- For Lua/runtime triage, a remembered MO2 `mods/` path is usually more valuable than a remembered `logs_dir`, because it lets the skill resolve the reported script or asset back to the installed addon.
- For engine fatal blocks, do not assume the first engine frame is the gameplay root cause; often the actionable clue is the `Expression`, `File`, or nearby Lua traceback.
- Prefer the resolved non-wrapper inspect points over `xrDebugNew.cpp` wrapper frames such as `xrDebug::backend`, `xrDebug::gather_info`, `invalid_parameter_handler`, or `UnhandledFilter`.
