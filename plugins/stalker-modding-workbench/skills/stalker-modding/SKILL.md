---
name: stalker-modding
description: "Use when working on S.T.A.L.K.E.R./XRay modding tasks, especially Anomaly 1.5.3 + Modded Exes: Lua scripts, configs, UI XML, XML localization, crash-log triage, existing addon maintenance, HUD and weapons, callbacks, binders, save/load safety, engine capability lookup, mixed mod workbenches, and reference research."
---

# STALKER Modding

This is a repo-local plugin. It provides operational guardrails; the active workbench provides the large reference trees and helper scripts.

## Bind To The Active Workbench

Find the task's workbench root first: it is the directory containing `AGENTS.md`, `.skills/stalker-modding/`, `.codex-stalker/workspace.json`, and `ai_workspace/`. Do not resolve workspace references relative to this installed plugin cache.

From that root, load the canonical `.skills/stalker-modding/SKILL.md`, the workspace overlay, and only the relevant `help/stalker/*.md` and `.skills/stalker-modding/references/*.md` files. Use the workbench's `.skills/stalker-modding/scripts/` helpers, local `ai_workspace` references, and `ai_workspace/user references` rather than copying external trees. Use the local MCM repository for `ui_mcm` behavior and the GAMMA overlay for pack-specific compatibility.

Before substantial task work, follow `$stalker-anomaly-expert` against the workbench's checked-in `.expertise/stalker-anomaly` vault. Default extension order is callbacks/config hooks, DXML, DLTX, narrow original-preserving monkey patches, then full-file overrides. Start vanilla script tracing at `_g.script`, `lua_help.script`, and `axr_main.script`.

For C++/Lua/config investigations, trace the smallest source-of-truth path through the relevant entry point, reachability conditions, and data origin. Group findings by runtime subsystem; distinguish structural links from semantic behavior; label conclusions `verified fact`, `inference`, or `unknown`. Do not call a callback, export, virtual method, factory product, registered Lua module, string lookup, or config hook unused just because direct text search finds no caller; leave it `UNKNOWN` until its runtime path is verified.

For logs, use the workbench's `log_triage.py` first, inspect the owning project frame rather than assuming the top stack frame is the cause, and test one to three falsifiable hypotheses against the narrowest relevant source path. Use LSP or targeted C++ static analysis only when the existing toolchain and compilation database make its result trustworthy. Never install, bootstrap, download, or reconfigure Python, `rg`, `luac`, LSP servers, compilers, or build systems automatically; report the missing prerequisite and reduced validation unless the user explicitly asks to provision it.

For project work, author under the workbench's `projects/<project-name>`, ask whether an existing mod should be imported or edited in place, and use its project, packaging, localization, Lua, quality-scan, and regression helpers only when they fit the task. Treat MO2 `overwrite/` as transient output and use `stalker-gamma` only for addon discovery and modpack composition, not engine semantics.

The plugin-local `.mcp.json` wires:
- `deepwiki`
- `xray-monolith`
- `anomaly-modding-book`
- `modorganizer2`
- `stalker-gamma`
