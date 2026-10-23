# XeFM Configuration System

XeFM includes a comprehensive configuration system that allows users to customize behavior, key bindings, and appearance through a Python configuration file.

## Configuration File Location

**User Config**: `~/.xefm/config.py`
**Template File**: `_config.py` (in XeFM installation directory)

- **Auto-Creation**: If the config file doesn't exist, XeFM automatically creates one from the template on first launch
- **Template-Based**: Default configuration is maintained in a separate `_config.py` template file
- **Python Format**: Configuration is stored as a Python class for flexibility and validation
- **User Directory**: User config located in the user's home directory for per-user customization
- **Clean Separation**: Template and user config are separate for easier maintenance

## Configuration Structure

### Config Class Format

```python
class Config:
    """User configuration for XeFM"""
    
    # Display settings
    SHOW_HIDDEN_FILES = False
    DEFAULT_LEFT_PANE_RATIO = 0.5
    DEFAULT_LOG_HEIGHT_RATIO = 0.25
    
    # Sorting settings
    DEFAULT_SORT_MODE = 'filename'
    DEFAULT_SORT_REVERSE = False
    
    # ... more settings
```

## Available Configuration Options

### Display Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `SHOW_HIDDEN_FILES` | bool | `False` | Show hidden files by default (dot-names, plus the Windows hidden attribute) |
| `DEFAULT_LEFT_PANE_RATIO` | float | `0.5` | Left pane width ratio (0.1-0.9) |
| `DEFAULT_LOG_HEIGHT_RATIO` | float | `0.25` | Log pane height ratio (0.1-0.5) |
| `DATE_FORMAT` | str | `'short'` | `'short'` (YY-MM-DD HH:mm) or `'full'` (YYYY-MM-DD HH:mm:ss) |

### Sorting Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `DEFAULT_SORT_MODE` | str | `'filename'` | Default sort mode: 'filename', 'extension', 'size', 'timestamp' (the old 'name'/'ext'/'date' still resolve) |
| `DEFAULT_SORT_REVERSE` | bool | `False` | Default reverse sort order |

### Color Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `THEMES` | dict | one example theme (`'Phosphor'`) | Extra named themes, `{name: overrides}`, added to the built-in PuiKit themes (see `COLOR_SCHEMES_IMPLEMENTATION.md`) |

There is no setting that picks the theme: XeFM starts on Dark+ and remembers the
theme last chosen (View → Theme / Next Theme) across restarts.

### Behavior Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `CONFIRM_DELETE` | bool | `True` | Show confirmation for delete operations |
| `CONFIRM_TRASH` | bool | `True` | Show confirmation before moving files to the Trash / Recycle Bin |
| `DELETE_TO_TRASH` | bool | `True` | `delete_files` sends local files to the Trash where the drive has one; `False` deletes permanently |
| `CONFIRM_QUIT` | bool | `True` | Show confirmation when quitting |
| `CONFIRM_COPY` | bool | `True` | Show confirmation for copy operations |
| `CONFIRM_MOVE` | bool | `True` | Show confirmation for move operations |
| `CONFIRM_DUPLICATE` | bool | `True` | Show confirmation for duplicate operations |
| `CONFIRM_EXTRACT_ARCHIVE` | bool | `True` | Show confirmation for archive extraction |
| `CONFIRM_ARCHIVE_CREATE` | bool | `True` | Show confirmation for archive creation |
| `TRANSFER_CONCURRENCY` | str/int | `"auto"` | Files in flight per copy/move/extract: `"auto"` (per storage), `"none"` (sequential), or an integer |

### Startup Directories

There is no config setting for the startup directories. Each pane opens on the
directory passed with `--left` / `--right`, else on the directory it had when
XeFM last quit (`XeFMApp._restore_one_pane`, if that directory still exists),
else on the launch directory (`main()` passes `"."`).

### Performance Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `MAX_LOG_MESSAGES` | int | `1000` | Maximum log messages to keep |

These tables cover the general settings. `xefm/_config.py` is the complete,
commented list — fonts, `TEXT_ENCODINGS`, `KEY_PRESET` / `KEY_SEQUENCE_TIMEOUT`,
the customization tables (`ACTIONS`, `EVENT_HOOKS`, `SORT_KEYS`, `FILTERS`, …),
`FAVORITES`, `PROGRAMS`, `FILE_ASSOCIATIONS`, editor/terminal commands, cache
TTLs, file monitoring and Migemo search. The info-dialog sizes
(`INFO_DIALOG_*`) are constants in `xefm/const.py`, not config settings.

## Key Bindings Configuration

### Keymap Presets and `KEY_BINDINGS`

The keymap comes from a **preset** (`afx`, `orthodox`, `native`, `vim`), chosen
at first launch or in Tools → Advanced → Keymap…, or fixed with `KEY_PRESET`.
`KEY_BINDINGS` in `config.py` is laid over that preset action by action: an
entry replaces that action's keys under every preset, and an action not listed
keeps the preset's. The shipped `KEY_BINDINGS` is empty apart from commented
examples. `keymap_presets.apply()` writes the merged table back into
`config.KEY_BINDINGS`, so every reader sees one table (see
`KEYMAP_PRESETS_IMPLEMENTATION.md`). The keys themselves are listed only in
`doc/KEYMAP_PRESETS_FEATURE.md`.

```python
KEY_BINDINGS = {
    'reload_config': ['F12'],                     # simple format
    'quit': [],                                   # an empty list unbinds
    'delete_permanently': {'keys': ['Shift-DELETE'], 'selection': 'required'},
    'text_viewer.page_down': ['SPACE'],           # one viewer's context only
    'go_root': ['g r'],                           # a key sequence
}
```

### Key Binding Features

- **Multiple Keys**: Each action can have multiple key bindings
- **Key Expressions**: Characters, named keys (`ENTER`, `PAGE_UP`, `F10`), punctuation names, modifier chords (`Ctrl-O`, `Command-ENTER`) and sequences (`'g h'`) — see `KEY_BINDINGS_IMPLEMENTATION.md`
- **Selection Requirements**: The extended format restricts an action to `'required'` / `'none'` / `'any'` selection state
- **Context Prefixes**: `text_viewer.`, `isearch.`, … scope an entry to one surface
- **Old Names**: A renamed action's old name still works, and a one-line notice names it (`deprecated_names_notice`)
- **Validation**: An unknown key name logs `Unknown key in expression: …` and that binding never fires

### Pane Adjustment Actions

`adjust_pane_left` / `adjust_pane_right` move the boundary between the panes,
`adjust_log_up` / `adjust_log_down` change the log pane height, and
`reset_pane_boundary` / `reset_log_height` restore the 50/50 split and the
configured log height.

## Architecture and Loading Flow

### Single Source of Truth

All configuration defaults live in the `Config` class in `xefm/_config.py`. There is
**no** second defaults class — the earlier `DefaultConfig` in `xefm/config.py` was
removed, so there are no longer "two configs" to keep in sync. `xefm/_config.py`
serves two roles:

1. **Template** — copied verbatim to `~/.xefm/config.py` on first run.
2. **Default provider** — the source used to fill in any fields a user config is
   missing.

### Automatic Field Copying

When XeFM loads configuration it:

1. Loads the user's `~/.xefm/config.py` (if present).
2. Loads the template `Config` class from `xefm/_config.py`.
3. Copies any missing public fields from the template into the user config.
4. Returns a complete config with every field present.

This means new options appear automatically in existing user configs, corrupted
configs are backfilled with defaults, and users never have to hand-edit their
config to pick up newly added settings.

### Loading Flow

```
1. ConfigManager.load_config() called
   - ensure_user_tools_dir() seeds ~/.xefm/tools/ on first launch
   - prepare_user_extensions() puts ~/.xefm/extensions/ on sys.path and evicts
     previously imported extension modules (USER_EXTENSIONS_IMPLEMENTATION.md)
2. Load template Config class from xefm/_config.py   (_load_template_config)
3. Does ~/.xefm/config.py exist?
   - No  -> create_default_config() copies xefm/_config.py to ~/.xefm/config.py
   - Yes -> import and instantiate the user's Config
            (on error, fall back to an empty config filled from the template)
4. _copy_missing_fields(user_config, template_class) backfills any missing
   public attributes, logging each field added
5. Return the complete config with all fields present
```

### Key Components (`xefm/config.py`)

- **`ConfigManager`** — loads, caches, and provides access to config. Key methods:
  `load_config()`, `get_config()`, `reload_config()`, `create_default_config()`,
  `validate_config()`, `get_key_bindings()`.
- **`_load_template_config()`** — dynamically imports the `Config` class from
  `xefm/_config.py` and returns the class (not an instance) for field inspection;
  returns `None` on failure.
- **`_copy_missing_fields(user_config, template_config_class)`** — copies public
  (non-`_`) attributes present on the template but missing on the user config,
  logging each addition and the total count.
- **`KeyBindings`** — key-binding lookup and parsing
  (`find_action_for_event`, `get_keys_for_action`, `format_key_for_display`).

> `validate_config()` builds a merged `Config` from `xefm/_config.py` internally to
> check ranges/types — it is a local helper, not a separate defaults class.

### Adding a New Option

1. Add the field to the `Config` class in `xefm/_config.py`.
2. That's it — the field is copied into existing user configs on next launch and
   logged (`Added missing config field: <NAME>`). There is no second class to update.

## Configuration Management

### Automatic Loading

1. **Startup Check**: XeFM checks for `~/.xefm/config.py` on launch
2. **Auto-Creation**: Creates the user config from the `xefm/_config.py` template if the file doesn't exist
3. **Template-Based**: Uses the single `xefm/_config.py` template as the source of defaults
4. **Error Handling**: Fills missing fields from the `xefm/_config.py` template if the config is incomplete or invalid
5. **Validation**: Validates configuration values and reports errors

### Configuration API

```python
import xefm.config

# Get current configuration
config = xefm.config.get_config()

# Reload configuration from file
xefm.config.reload_config()

# Check key bindings
is_bound = xefm.config.is_key_bound_to('q', 'quit')
```

## Customization Examples

### Example 1: Customize Key Bindings

Each entry replaces that action's keys from the preset; unlisted actions keep
theirs.

```python
class Config:
    KEY_PRESET = 'afx'
    KEY_BINDINGS = {
        'file_details': ['I', 'F3'],    # Add F3 for details
        'toggle_color_scheme': ['F11'], # Cycle themes from the keyboard
        'reload_config': ['F12'],       # A key for an action that has none
    }
```

### Example 2: Adjust Display Settings

```python
class Config:
    # Show hidden files by default
    SHOW_HIDDEN_FILES = True
    
    # Wider left pane (70/30 split)
    DEFAULT_LEFT_PANE_RATIO = 0.7
    
    # Smaller log pane
    DEFAULT_LOG_HEIGHT_RATIO = 0.15
    
    # Disable quit confirmation
    CONFIRM_QUIT = False
    
    # Disable copy and move confirmations for faster workflow
    CONFIRM_COPY = False
    CONFIRM_MOVE = False
    
    # Keep extract confirmation for safety
    CONFIRM_EXTRACT_ARCHIVE = True
```

### Example 3: Performance Tuning

```python
class Config:
    # Keep more log messages
    MAX_LOG_MESSAGES = 5000
```

### Example 4: Confirmation Settings

```python
class Config:
    # Safety-first approach - confirm all operations
    CONFIRM_DELETE = True
    CONFIRM_QUIT = True
    CONFIRM_COPY = True
    CONFIRM_MOVE = True
    CONFIRM_EXTRACT_ARCHIVE = True
```

```python
class Config:
    # Speed-focused approach - minimal confirmations
    CONFIRM_DELETE = True      # Keep for safety
    CONFIRM_QUIT = False       # Quick exit
    CONFIRM_COPY = False       # Fast copying
    CONFIRM_MOVE = False       # Fast moving
    CONFIRM_EXTRACT_ARCHIVE = False  # Quick extraction
```

## Configuration Validation

### Automatic Validation

- **Range Checks**: Ratios must be within valid ranges
- **Type Validation**: Settings must be correct types
- **Value Validation**: Enum values are checked
- **Error Reporting**: Invalid settings are reported with warnings

### Validation Rules

- `DEFAULT_LEFT_PANE_RATIO`: Must be between 0.1 and 0.9
- `DEFAULT_LOG_HEIGHT_RATIO`: Must be between 0.1 and 0.5
- `DEFAULT_SORT_MODE`: Must name a sort — 'filename', 'extension', 'size', 'timestamp', an old spelling of one, or a key a config registered
- `FONT_SIZE`: An integer between 8 and 72; `UI_FONT_NAME` / `MONO_FONT_NAME`: a non-empty string or `None`
- `MIGEMO_ROMAJI_TABLE`: Must be 'default' or 'azik'; the `FILE_MONITORING_*`, `MIGEMO_*`, `REDUCED_MOTION`, `TEXT_ENCODINGS` and `WIDE_CHARS` fields are type/range-checked too
- `ACTIONS`, `EVENT_HOOKS`, `SORT_KEYS`, `FILTERS`, …: each entry is shape-checked by `xefm.user_api.validate_user_entries`

`validate_config()` returns the problems as a list; `XeFMApp.reload_config()`
logs each one as `Config warning: …` and applies the config anyway.

## Error Handling

### Configuration Errors

1. **File Not Found**: Creates the user config from the `xefm/_config.py` template
2. **Syntax Errors**: Loads an empty config and fills all fields from the `xefm/_config.py` template
3. **Missing Config Class**: Fills all fields from the template
4. **Invalid Values**: Uses template defaults for invalid settings
5. **Permission Errors**: Reports warning and falls back to template defaults

### Fallback Behavior

- **Graceful Degradation**: XeFM always starts even with config errors
- **Template Defaults**: Missing or invalid fields are filled from the `xefm/_config.py` template
- **Error Logging**: Configuration errors are logged to the log pane
- **User Notification**: Clear messages about configuration issues

## Template System

### Configuration Template

XeFM uses a template-based configuration system for better maintainability:

- **Template File**: `_config.py` contains the default configuration template
- **Clean Defaults**: Template is maintained separately from user configuration
- **Easy Updates**: Template can be updated without affecting user configs
- **Consistent Creation**: All new user configs are created from the same template

### Template Benefits

1. **Maintainability**: Default configuration is in a separate, version-controlled file
2. **Consistency**: All users get the same default configuration structure
3. **Documentation**: Template includes comprehensive comments and examples
4. **Upgrades**: Template can be updated independently of user configurations

### Template Structure

The `_config.py` template includes:
- Complete configuration class with all available options
- Detailed comments explaining each setting
- Example values and valid ranges
- Organized sections for different setting categories

## Advanced Features

### Dynamic Configuration

- **Runtime Changes**: Some settings can be changed during runtime
- **Configuration Reload**: Reload config without restarting XeFM
- **Validation Feedback**: Real-time validation of configuration changes

### Future Enhancements

- **GUI Configuration Editor**: Visual configuration editor
- **Multiple Profiles**: Support for different configuration profiles

## Troubleshooting

### Common Issues

1. **Config File Not Loading**:
   - Check file permissions
   - Verify Python syntax
   - Ensure Config class exists

2. **Invalid Key Bindings**:
   - Check key binding format
   - Check the log for `Unknown key in expression: …`
   - Verify action names are correct

3. **Path Issues**:
   - Use absolute paths or ~ for home directory
   - Ensure directories exist
   - Check path permissions

## Configuration File Example

Here's a complete example configuration file:

```python
#!/usr/bin/env python3
\"\"\"
XeFM User Configuration - Custom Setup
\"\"\"

class Config:
    # Display preferences
    SHOW_HIDDEN_FILES = True
    DEFAULT_LEFT_PANE_RATIO = 0.6
    DEFAULT_LOG_HEIGHT_RATIO = 0.2
    
    # Sorting preferences
    DEFAULT_SORT_MODE = 'timestamp'
    DEFAULT_SORT_REVERSE = True
    
    # Behavior
    CONFIRM_DELETE = True
    CONFIRM_QUIT = False
    CONFIRM_COPY = True
    CONFIRM_MOVE = True
    CONFIRM_EXTRACT_ARCHIVE = False
    
    # Keymap: the AFX preset, with a few keys changed
    KEY_PRESET = 'afx'
    KEY_BINDINGS = {
        'file_details': ['I', 'F3'],    # Add F3 for details
        'toggle_color_scheme': ['F11'], # Cycle themes from the keyboard
        'quit': [],                     # Unbind quit (still in the menu)
    }
    
    # Performance
    MAX_LOG_MESSAGES = 2000
```

The configuration system provides extensive customization while maintaining simplicity and reliability through automatic defaults and comprehensive error handling.