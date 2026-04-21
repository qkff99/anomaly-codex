# Anomaly DevTools - Profiler & Logger

A standalone developer toolkit for S.T.A.L.K.E.R. Anomaly that provides performance profiling and structured logging for **any mod**.

## Features

- **Zero-Code Profiling**: Profile any Lua module without modifying its code
- **Module Browser**: UI to discover and select modules to profile
- **Profiling Presets**: Save and load module selections for quick switching
- **Live Statistics**: Real-time function timing (calls, avg/min/max/total ms)
- **Structured Logging**: Severity levels, categories, filtering, file output
- **Category Browser**: Visual category management with colors and quick toggles
- **Self-Contained UI**: ImGui panel with profiler stats and log viewer

---

## Installation

Copy the following files to your `gamedata/scripts/` folder:

| File | Purpose |
|------|---------|
| `devtools_profiler.script` | Core profiling engine |
| `devtools_config.script` | Configuration and presets storage |
| `devtools_logging.script` | Structured logging system |
| `devtools_imgui.script` | ImGui user interface |
| `mod_script_devtools_early.ltx` | DLTX config for early script loading |

Start the game - DevTools registers automatically.

---

## Quick Start

### Using the UI (No Code Required)

1. Open the DevTools window (via your mod's menu or API)
2. Go to the **Profiler** tab
3. Expand **Module Browser**
4. Check the modules you want to profile
5. Click **Start Profiling**
6. Watch the stats table populate with timing data

### Saving Presets

1. Select the modules you want to profile
2. In the **Presets** section, type a name
3. Click **Save**
4. Later, click a preset name to restore that selection

---

## Programmatic Usage

### Profiling a Module

```lua
-- In your mod's on_game_start:
function on_game_start()
    if devtools_profiler then
        devtools_profiler.register_module("my_mod")
    end
end
```

That's it! Your module is now registered. Use the UI to enable/disable profiling.

### Custom Timing

For timing specific code sections that aren't function boundaries:

```lua
devtools_profiler.start_timer("my_operation")
-- ... your code ...
devtools_profiler.end_timer("my_operation")
```

### Logging

```lua
function on_game_start()
    -- Register a category with a color (RGBA 0-255)
    if devtools_logging then
        devtools_logging.register_category("MY_MOD", {100, 200, 255, 255})
    end
end

-- Log messages anywhere:
devtools_logging.info("MY_MOD", "Something happened", {key = "value"})
devtools_logging.warn("MY_MOD", "Warning message")
devtools_logging.error_log("MY_MOD", "Error occurred")
devtools_logging.debug_log("MY_MOD", "Debug info")
```

---

## API Reference

### devtools_profiler.script

#### Module Discovery & Registration
```lua
devtools_profiler.discover_modules()           -- Returns list of all Lua modules in _G
devtools_profiler.register_module(name)        -- Register module for profiling
devtools_profiler.unregister_module(name)      -- Unregister module
devtools_profiler.get_registered_modules()     -- Get list of registered modules
devtools_profiler.is_module_registered(name)   -- Check if registered
```

#### Profiling Control
```lua
devtools_profiler.enable()                     -- Start profiling registered modules
devtools_profiler.disable()                   -- Stop profiling immediately, restore functions
devtools_profiler.is_enabled()                 -- Check if profiling active
```

**Note:** `disable()` immediately stops all timing collection (including manual `start_timer`/`end_timer` calls) by setting the global `ENABLED` flag to `false`. This ensures that statistics stop updating the moment profiling is disabled, even if function wrappers are still active.

#### Manual Timing
```lua
devtools_profiler.start_timer(name)            -- Start timing an operation
devtools_profiler.end_timer(name)              -- End timing, returns duration_ms
```

**Note:** Manual timing calls respect the global profiling state. If profiling is disabled via `disable()`, `start_timer` and `end_timer` will return immediately without recording statistics. This ensures consistent behavior across all profiling methods.

#### Statistics
```lua
devtools_profiler.get_stats(name)              -- Get stats for a function
devtools_profiler.get_all_stats()              -- Get all function stats
devtools_profiler.get_tracked_functions()      -- Get list of tracked function names
devtools_profiler.reset_stats(name)            -- Reset stats for a function
devtools_profiler.reset_all()                  -- Reset all stats
```

#### CSV Export
```lua
devtools_profiler.export_to_csv(filepath)       -- Export all stats to CSV (filepath optional)
devtools_profiler.get_csv_export_path()        -- Get default CSV export path
```

#### Flamegraph Export
```lua
devtools_profiler.enable_flamegraph()          -- Enable flamegraph data collection
devtools_profiler.disable_flamegraph()         -- Disable flamegraph data collection
devtools_profiler.is_flamegraph_enabled()      -- Check if flamegraph collection is enabled
devtools_profiler.reset_flamegraph()           -- Clear captured flamegraph data
devtools_profiler.export_flamegraph(filepath)  -- Export collapsed stacks format (filepath optional)
devtools_profiler.get_flamegraph_export_path() -- Get default flamegraph export path
```

**Note:** Flamegraph exports use the standard "collapsed stacks" format:
`root;module.func;child.func <space> time_us`. This works with external tools like
FlameGraph.pl, inferno, or speedscope.

#### Wrapped Module Info
```lua
devtools_profiler.get_wrapped_modules()        -- Currently wrapped modules
devtools_profiler.get_wrapped_function_count() -- Number of wrapped functions
devtools_profiler.is_module_wrapped(name)      -- Check if module is wrapped
```

#### Presets
```lua
devtools_profiler.save_preset(name)            -- Save current selection as preset
devtools_profiler.load_preset(name)            -- Load preset and register modules
devtools_profiler.delete_preset(name)          -- Delete a preset
devtools_profiler.get_preset_names()           -- Get all preset names
devtools_profiler.preset_exists(name)          -- Check if preset exists
```

### devtools_logging.script

#### Category Management
```lua
devtools_logging.register_category(name, color)    -- Register with RGBA color
devtools_logging.unregister_category(name)         -- Remove category
devtools_logging.get_categories()                  -- List all categories
devtools_logging.get_category_color(name)          -- Get category color
```

#### Logging Functions
```lua
devtools_logging.log(severity, category, message, data)
devtools_logging.debug_log(category, message, data)
devtools_logging.info(category, message, data)
devtools_logging.warn(category, message, data)
devtools_logging.error_log(category, message, data)
```

#### Severity Levels
```lua
devtools_logging.DEBUG = 1
devtools_logging.INFO = 2
devtools_logging.WARN = 3
devtools_logging.ERROR = 4
```

#### Buffer Access
```lua
devtools_logging.get_entries()                     -- Get all log entries
devtools_logging.get_filtered_entries(search)      -- Get filtered entries
devtools_logging.clear()                           -- Clear log buffer
devtools_logging.get_stats()                       -- Get buffer stats
```

#### Configuration
```lua
devtools_logging.set_enabled(bool)                 -- Enable/disable logging
devtools_logging.set_paused(bool)                  -- Pause/resume capture
devtools_logging.set_echo_to_console(bool)         -- Echo to game console
devtools_logging.set_write_to_file(bool)           -- Write to file
devtools_logging.set_file_path(path)               -- Set log file path
devtools_logging.set_category_enabled(cat, bool)   -- Filter categories
devtools_logging.set_min_severity(level)           -- Filter by severity
```

### devtools_imgui.script

```lua
devtools_imgui.toggle_window()                     -- Toggle visibility
devtools_imgui.show()                              -- Show window
devtools_imgui.hide()                              -- Hide window
devtools_imgui.is_visible()                        -- Check visibility
```

---

## UI Features

### Profiler Tab

#### Module Browser
- **Search**: Filter modules by name
- **Select All / Deselect All**: Quick bulk selection
- **Column Display**: Modules shown in responsive columns
- **Color Coding**:
  - Green: Registered for profiling
  - Gray: Available but not selected

**⚠️ WARNING**: Selecting too many modules at once can cause stackoverflows. Use moderation when selecting modules.

#### Presets
- Save current module selection with a name
- Click preset name to load it
- Click "x" to delete a preset

#### Statistics Table
| Column | Description |
|--------|-------------|
| **Function** | Full function name (module.function) |
| **Calls** | Total number of times called |
| **Avg (ms)** | Average execution time per call |
| **Min (ms)** | Fastest execution time observed |
| **Max (ms)** | Slowest execution time observed |
| **Total (ms)** | Cumulative time spent in this function |

**Color Coding:**
- Green (< 1ms): Fast, no concern
- Yellow (1-5ms): Moderate, acceptable
- Orange (5-20ms): Slow, investigate if called frequently
- Red (> 20ms): Very slow, likely a bottleneck

**Sorting:** Click column headers to sort (ascending/descending)

**Export:** Click "Export CSV" button to save all statistics to a CSV file for analysis in Excel or other tools. The file is saved to `appdata/devtools_profiler_export.csv` by default.

### Logger Tab

#### Category Browser
- **Search**: Filter categories by name
- **All On / All Off**: Quick bulk toggle
- **Color Coding**: Categories shown in their registered colors
- **Enable/Disable**: Click checkbox to toggle individual categories

#### Log Viewer
- **Severity Filter**: DEBUG/INFO/WARN/ERROR buttons
- **Search**: Filter log messages by text
- **Auto-scroll**: Optionally follow new messages
- **Pagination**: Navigate through log history

---

## Example: Full Integration

```lua
-- my_awesome_mod.script

function on_game_start()
    -- Register with devtools profiler (if available)
    if devtools_profiler then
        devtools_profiler.register_module("my_awesome_mod")
    end
    
    -- Register logging category with color
    if devtools_logging then
        devtools_logging.register_category("AWESOME", {255, 100, 200, 255})
        devtools_logging.info("AWESOME", "My Awesome Mod initialized!")
    end
end

function do_something_complex(items)
    if devtools_logging then
        devtools_logging.debug_log("AWESOME", "Starting complex operation", {
            item_count = #items
        })
    end
    
    -- Your code here...
    local result = process_items(items)
    
    if devtools_logging then
        devtools_logging.info("AWESOME", "Operation completed", {
            processed = result.count,
            errors = result.errors
        })
    end
    
    return result
end

RegisterScriptCallback("on_game_start", on_game_start)
```

---

## Technical Details

### Timer Precision

The profiler uses **profile_timer** (X-Ray's native C++ timer) exclusively for microsecond-precision timing. This is the only timing method in the X-Ray engine with sufficient resolution for profiling - both `os.clock` and `time_global` lack the precision needed for sub-millisecond measurements.

**Note:** If `profile_timer` is unavailable (rare), timing will be disabled and a warning logged.

### Master Switch Behavior

The profiler uses a global `ENABLED` flag as a master switch that controls all timing collection:
- When `enable()` is called, `ENABLED` is set to `true`, allowing timing to be recorded
- When `disable()` is called, `ENABLED` is immediately set to `false` at the start of the function, ensuring all timing stops instantly
- Both automatic function wrapping and manual `start_timer`/`end_timer` calls respect this flag
- This design ensures that clicking "Stop Profiling" immediately halts all statistics updates, even if function wrappers are still active in memory

### Module Exclusions

DevTools modules (`devtools_*`) and system modules (Lua standard library, `os`, `io`, `debug`, etc.) are always excluded from profiling to prevent infinite recursion and stack overflow.

### Stack Overflow Protection

The profiler includes multiple safeguards to prevent stack overflow:

1. **Module Blacklist**: DevTools modules and Lua standard library are never wrapped
2. **Function Blacklist**: System functions (`printf`, `time_global`, etc.) are excluded
3. **Call Depth Limit**: Maximum 100 nested profiled calls (configurable via `MAX_CALL_DEPTH`)
4. **Nested Call Support**: Each function call gets its own timer, supporting recursive and nested calls correctly

### Ring Buffer

Logs use a ring buffer (default 1000 entries) to prevent memory issues. Oldest entries are overwritten when full.

### Configuration Storage

Presets are stored in `appdata/devtools_presets.txt`.

---

## Advanced: Capturing Game Initialization

DevTools uses DLTX to force early script loading, which allows it to capture the complete game initialization sequence including `_g.start_game_callback` and `axr_main.on_game_start`.

**How it works:**
- The file `gamedata/configs/mod_script_devtools_early.ltx` uses DLTX to add DevTools scripts to the early load list
- This causes the profiler to load BEFORE `start_game_callback` is called
- At root level, the profiler checks for the `_AUTOLOAD_` preset and wraps modules immediately
- When `start_game_callback` runs, `_g` and `axr_main` are already wrapped!

**To capture full initialization:**
1. Select the modules you want to profile (including `_g` and `axr_main`)
2. Enable "Collect Data" for flamegraph if desired
3. Enable "Profile on Load" to save the `_AUTOLOAD_` preset
4. **Restart the game completely** (not just reload a save)
5. The profiler will wrap modules before `start_game_callback` runs

**What gets captured:**
- `_g.start_game_callback` and everything inside it
- `axr_main.on_game_start` and all module `on_game_start` callbacks
- All runtime callbacks (`actor_on_update`, `npc_on_update`, etc.)

**Note:** This requires DLTX support (included in Anomaly 1.5.1+). The early loading happens automatically - no manual patches needed!

---

## Tips

1. **Profile Performance Issues**: If your mod causes stutters, register it and enable profiling to see which functions are slow.

2. **Use Categories**: Create categories for different subsystems (AI, UI, Combat, etc.) to filter logs effectively.

3. **Log Data Objects**: The `data` parameter accepts tables - use it for structured data that helps debugging.

4. **File Output**: Enable "Write to file" for persistent logs that survive game crashes.

5. **Module Discovery**: The Module Browser scans all of `_G` - you can profile ANY mod, even ones you didn't write.

6. **Save Presets**: Create presets for different debugging scenarios (e.g., "AI_Debug", "Combat_Debug").

7. **Performance Impact**: Profiling adds ~1-5% overhead. Disable it during normal gameplay.

8. **CSV Export**: Use the "Export CSV" button to save profiling data for detailed analysis in Excel, Google Sheets, or other tools. Great for comparing performance across different game sessions.

9. **Flamegraph Export**: Enable flamegraph collection, run a profiling session, then export a `.folded` file for external tools like FlameGraph.pl, inferno, or speedscope.

---

