# XeFM State Manager System

## Overview

The XeFM State Manager provides persistent application state management using SQLite database. It safely handles multiple XeFM instances accessing the same state database and automatically creates the database at `~/.xefm/state.db`.

## Features

### Core Capabilities
- **Persistent State Storage**: Saves application state across XeFM sessions
- **Multi-Instance Safety**: Handles concurrent access from multiple XeFM processes
- **Automatic Database Creation**: Creates and initializes database automatically
- **Thread-Safe Operations**: Uses proper locking for concurrent access
- **Graceful Error Handling**: Continues operation even if state operations fail
- **Session Management**: Tracks active XeFM instances and cleans up stale sessions

### State Types Managed
- **Pane State**: Directory paths, selection, scroll position, sort settings, filters
- **Window Layout**: Pane width ratios, log pane height
- **Recent Directories**: History of visited directories for quick navigation
- **Query Histories**: Search, filter and list-command queries, each under its own key
- **Path Cursor History**: Separate cursor positions for left and right panes
- **Session Information**: Active XeFM instances with heartbeat tracking

## Architecture

### Database Schema

```sql
-- Application state table
CREATE TABLE app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,           -- JSON serialized data
    updated_at REAL NOT NULL,      -- Unix timestamp
    instance_id TEXT               -- XeFM instance identifier
);

-- Session tracking table
CREATE TABLE sessions (
    instance_id TEXT PRIMARY KEY,
    pid INTEGER NOT NULL,          -- Process ID
    started_at REAL NOT NULL,      -- Session start time
    last_seen REAL NOT NULL,       -- Last heartbeat time
    hostname TEXT                  -- Machine hostname
);
```

### Class Hierarchy

```
StateManager (Base class)
├── Basic state operations (get/set/delete)
├── Database connection management
├── JSON serialization/deserialization
├── Thread-safe operations
└── Error handling

XeFMStateManager (XeFM-specific)
├── Inherits from StateManager
├── Session management
├── XeFM-specific convenience methods
├── Pane state operations
├── Window layout management
└── History management
```

## Usage

### Basic State Operations

```python
from xefm.state_manager import get_state_manager

# Get the global state manager
state_manager = get_state_manager()

# Save simple values
state_manager.set_state("user_preference", "dark_theme")

# Save complex data
pane_data = {
    'path': '/home/user',
    'selected_index': 5,
    'sort_mode': 'size'
}
state_manager.set_state("left_pane", pane_data)

# Load values
theme = state_manager.get_state("user_preference", "light_theme")
pane_info = state_manager.get_state("left_pane")
```

### XeFM-Specific Operations

```python
# Save pane state: pass the pane dict itself; save_pane_state extracts
# path, focused_index (stored as 'selected_index'), scroll_offset, sort_mode,
# sort_reverse, filter_pattern and selected_files
state_manager.save_pane_state('left', current_pane)

# Load pane state
loaded_state = state_manager.load_pane_state('left')
if loaded_state and Path(loaded_state['path']).exists():
    current_pane['path'] = Path(loaded_state['path'])
    current_pane['sort_mode'] = loaded_state['sort_mode']
    # ... restore other settings

# Window layout
state_manager.save_window_layout(0.6, 0.25)  # 60% left pane, 25% log
layout = state_manager.load_window_layout()

# Recent directories
state_manager.add_recent_directory('/home/user/projects')
recent_dirs = state_manager.load_recent_directories()

# Search history (helpers kept on XeFMStateManager; the app itself keeps
# per-mode query histories under its own keys, see Search History Integration)
state_manager.add_search_term('*.py')
search_history = state_manager.load_search_history()

# Pane-specific cursor history
state_manager.save_pane_cursor_position('left', '/home/user/projects', 'main.py')
cursor_filename = state_manager.load_pane_cursor_position('left', '/home/user/projects')
left_positions = state_manager.get_pane_cursor_positions('left')
left_history = state_manager.get_ordered_pane_history('left')  # Chronological order
state_manager.clear_pane_history('left')  # Clear left pane cursor history
```

### Session Management

```python
# Sessions are automatically managed
# Get active sessions
sessions = state_manager.get_active_sessions()
for session in sessions:
    print(f"Instance: {session['instance_id']}")
    print(f"PID: {session['pid']}")
    print(f"Host: {session['hostname']}")

# Update heartbeat (done at startup)
state_manager.update_session_heartbeat()

# Cleanup (done on quit, in XeFMApp._save_application_state)
state_manager.cleanup_session()
```

## Integration with XeFM

### Initialization

The state manager is set up in `XeFMApp.__init__()` (`xefm/app.py`). It is
injectable so tests can pass a temp-db `XeFMStateManager`; otherwise the global
one is used. The `PaneManager` gets the same instance:

```python
self.state_manager = state_manager if state_manager is not None else get_state_manager()
...
self.pm = PaneManager(self.config, self._resolve_dir(left_dir),
                      self._resolve_dir(right_dir),
                      state_manager=self.state_manager,
                      file_list_manager=self.flm)
self._restore_layout_and_paths()
```

### State Loading

`_restore_layout_and_paths()` runs before the splitters and file lists are
built. It is best-effort: any exception is swallowed, since the log view does
not exist yet.

```python
def _restore_layout_and_paths(self):
    self._panes_fraction = max(0.1, min(0.95, 1.0 - self._default_log_height()))
    try:
        self.state_manager.update_session_heartbeat()
        self.state_manager.cleanup_non_existing_directories()

        layout = self.state_manager.load_window_layout()
        if layout:
            ratio = layout.get('left_pane_ratio', self.pm.left_pane_ratio)
            self.pm.left_pane_ratio = max(0.1, min(0.9, ratio))
            # The saved log height only wins if it differs from the
            # log_height_default saved with it, i.e. the user dragged it (#316)
            ...

        self._restore_one_pane('left', self.pm.left_pane, self._left_provided)
        self._restore_one_pane('right', self.pm.right_pane, self._right_provided)
        self._restore_tabs('left', self._left_provided)
        self._restore_tabs('right', self._right_provided)
    except Exception:
        pass
```

`_restore_one_pane()` re-applies the saved directory only when no startup
directory was given on the command line and the directory still exists; sort
mode (if still a known sort key), sort direction and filter are always restored.

### State Saving

`_save_application_state()` is called from `_quit()`:

```python
def _save_application_state(self):
    try:
        self.state_manager.save_window_layout(
            self.pane_splitter.fraction,
            1.0 - self.content_splitter.fraction,
            log_height_default=self._default_log_height(),
        )
        self.state_manager.save_pane_state('left', self.pm.left_pane)
        self.state_manager.save_pane_state('right', self.pm.right_pane)
        self.pm.save_cursor_position(self.pm.left_pane)
        self.pm.save_cursor_position(self.pm.right_pane)
        self._save_tabs()

        # The full visited-directory trail, most recent first (#220)
        self.state_manager.save_recent_directories(
            self._recent_dirs_most_recent_first(), _HISTORY_MAX)

        self.state_manager.cleanup_session()
    except Exception as e:
        self.log_info(f"Could not save application state: {e}")
```

### Search History Integration

Each search mode keeps its own query history under a key of its own
(`XeFMApp._SEARCH_HISTORY`: `search.history.filename`,
`search.history.content`, `index_search.history`), stored with the generic
`get_state` / `set_state`. Accepting the search dialog records the query:

```python
def on_accept(mode, value):
    query = dialog.query_edit.text.strip()
    if query:
        self._record_history(self._SEARCH_HISTORY[mode], query)
    ...
```

`_query_history(key)`, `_record_history(key, entry)` and
`_forget_history(key, entry)` read, prepend (de-duplicated, capped at
`_LIST_COMMAND_HISTORY_MAX`) and remove entries; the filter and list-command
histories use the same pattern under their own keys.

### Cursor History Integration

The PaneManager uses persistent cursor history (`xefm/pane_manager.py`):

```python
# Cursor positions are saved per pane, keyed by directory
def save_cursor_position(self, pane_data):
    if not pane_data['files'] or pane_data['focused_index'] >= len(pane_data['files']):
        return
    current_file = pane_data['files'][pane_data['focused_index']]
    current_dir = str(pane_data['path'])
    if not self.state_manager:
        return
    pane_name = 'left' if pane_data is self.left_pane else 'right'
    max_entries = self.config.MAX_HISTORY_ENTRIES
    self.state_manager.save_pane_cursor_position(pane_name, current_dir, current_file.name, max_entries)

# ... and restored when a directory's listing is in
def restore_cursor_position(self, pane_data, display_height):
    current_dir = str(pane_data['path'])
    if not self.state_manager:
        return False
    pane_name = 'left' if pane_data is self.left_pane else 'right'
    target_filename = self.state_manager.load_pane_cursor_position(pane_name, current_dir)
    if target_filename:
        # ... find target_filename, set focused_index, adjust scroll_offset
```

`XeFMApp` drives these through two wrappers: `_remember_cursor(pane)` is called
*before* a navigation changes `pane['path']` (a no-op for a virtual
search-results pane), and `_restore_remembered_cursor(pane)` is passed as the
listing's `on_ready`, because the saved cursor is matched by filename and can
only be placed once the files are in.

#### Startup Cursor Restoration

Startup lists both panes on worker threads (`_start_initial_listings`) and
restores the cursor as each listing completes:

```python
def _start_initial_listings(self):
    for name in ("left", "right"):
        self._list_pane(name, on_ready=self._restore_remembered_cursor)
```

#### Quit Cursor Saving

`_save_application_state()` (above) calls `self.pm.save_cursor_position()` for
both panes; `save_cursor_position` itself skips an empty pane or an
out-of-range `focused_index`.

#### Separate Pane Cursor History Features

- **Independent Histories**: Left and right panes maintain completely separate cursor histories
- **Chronological Ordering**: Each pane's history maintains the order of directory visits
- **Duplicate Handling**: Revisiting a directory updates the existing entry and moves it to the end
- **Configurable Limits**: Maximum entries controlled by `MAX_HISTORY_ENTRIES` in config
- **LRU Behavior**: Oldest entries are automatically removed when limit is exceeded per pane
- **No Cross-Contamination**: Navigation in one pane never affects the other pane's history
- **Startup Restoration**: Cursor positions are automatically restored when XeFM starts up
- **Quit Saving**: Cursor positions are automatically saved when XeFM quits
- **Backward Compatibility**: Automatically converts old dictionary format to new ordered format

## Multi-Instance Safety

### Concurrency Handling

The state manager uses several mechanisms to handle multiple XeFM instances safely:

1. **WAL Mode**: SQLite Write-Ahead Logging for better concurrency
2. **Connection Timeouts**: 30-second timeout for database operations
3. **Retry Logic**: Exponential backoff for locked database situations
4. **Thread Locking**: RLock for thread-safe operations within a process
5. **Graceful Degradation**: Operations continue even if state saving fails

### Database Configuration

```python
# Enable WAL mode for better concurrency
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=NORMAL')
conn.execute('PRAGMA temp_store=MEMORY')
conn.execute('PRAGMA mmap_size=268435456')  # 256MB
```

### Error Recovery

```python
@contextmanager
def _get_connection(self):
    for attempt in range(self._retry_attempts):
        try:
            conn = sqlite3.connect(str(self.db_path), timeout=self._connection_timeout)
            yield conn
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < self._retry_attempts - 1:
                time.sleep(self._retry_delay * (2 ** attempt))  # Exponential backoff
                continue
            else:
                raise
```

## Performance Considerations

### Optimization Features
- **Short-Lived Connections**: `_get_connection()` opens one connection per operation and closes it
- **Batch Operations**: `get_all_states()` for bulk retrieval
- **Indexed Queries**: Database indexes on frequently queried columns
- **Memory Storage**: Temporary data stored in memory
- **Lazy Loading**: State loaded only when needed

### Performance Characteristics
- **2000 operations**: ~5 seconds (set/get pairs)
- **1000 bulk retrieval**: ~0.01 seconds
- **Concurrent access**: Handles multiple instances without conflicts
- **Memory usage**: Minimal overhead, JSON serialization

## Error Handling

### Graceful Degradation
- **Database Unavailable**: Operations return default values
- **Serialization Errors**: Invalid data is rejected, operation continues
- **Permission Errors**: Warnings logged, application continues

### Error Examples

```python
# Serialization error handling (_serialize_value)
try:
    return json.dumps(value, default=str, ensure_ascii=False)
except (TypeError, ValueError) as e:
    raise ValueError(f"Cannot serialize value: {e}")  # set_state logs it and returns False

# Database error handling (get_state)
try:
    with self._get_connection() as conn:
        # ... database operations
except Exception as e:
    self.logger.warning(f"Could not get state '{key}': {e}")
    return default
```

## Configuration

### Database Location
- **Default**: `~/.xefm/state.db`
- **Custom**: Can be overridden in StateManager constructor
- **Auto-Creation**: Directory created automatically if needed

### Limits and Defaults
- **Recent Directories**: `save_recent_directories` defaults to 50; the app saves up to `_HISTORY_MAX` (100)
- **Query Histories**: 100 entries per key (`_LIST_COMMAND_HISTORY_MAX` in `xefm/app.py`)
- **Cursor History**: 100 entries per pane (configurable via `MAX_HISTORY_ENTRIES`)
- **Session Timeout**: 5 minutes (300 seconds)
- **Connection Timeout**: 30 seconds
- **Retry Attempts**: 3 with exponential backoff

## Testing

### Test Coverage
- **Unit Tests**: Basic state operations, serialization, error handling
- **Integration Tests**: XeFM-specific operations, multi-instance scenarios
- **Concurrency Tests**: Multiple threads accessing same database
- **Performance Tests**: Large datasets, bulk operations
- **Error Tests**: Database corruption, permission errors, invalid data

### Running Tests

```bash
# Run basic state manager tests
python -m pytest test/test_state_manager.py -v

# Run integration tests
python -m pytest test/test_state_integration.py -v

# App-level save/restore (XeFMApp on the headless backend)
python -m pytest test/test_xefm_app_state_persistence.py -v
```

## Future Enhancements

### Planned Features
- **State Versioning**: Track state changes over time
- **Backup/Restore**: Export/import state data
- **Compression**: Compress large state data
- **Encryption**: Encrypt sensitive state data
- **Cloud Sync**: Synchronize state across machines
- **State Analytics**: Usage patterns and statistics

### Migration Support
- **Schema Versioning**: Handle database schema changes
- **Data Migration**: Convert old state formats
- **Backward Compatibility**: Support older XeFM versions

## Troubleshooting

### Common Issues

1. **Database Locked**
   - Multiple instances accessing database simultaneously
   - Solution: Automatic retry with exponential backoff

2. **Permission Denied**
   - Cannot create `~/.xefm/` directory
   - Solution: Check home directory permissions

3. **Serialization Errors**
   - Complex objects that can't be JSON serialized
   - Solution: Graceful error handling, operation continues

4. **Stale Sessions**
   - Old session entries not cleaned up
   - Solution: Automatic cleanup of sessions older than 5 minutes

### Debug Information

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Check active sessions
sessions = state_manager.get_active_sessions()
print(f"Active sessions: {len(sessions)}")

# Check database file
db_path = Path.home() / '.xefm' / 'state.db'
print(f"Database exists: {db_path.exists()}")
print(f"Database size: {db_path.stat().st_size if db_path.exists() else 0} bytes")
```

## Security Considerations

### Data Protection
- **Local Storage**: Data stored locally, not transmitted
- **File Permissions**: Database file uses standard file permissions
- **No Sensitive Data**: Only application state, no passwords or keys
- **JSON Serialization**: Human-readable format, no binary data

### Access Control
- **User-Level**: Each user has their own state database
- **Process-Level**: Multiple XeFM instances share state safely
- **No Network Access**: Purely local file-based storage

## Conclusion

The XeFM State Manager provides robust, persistent state management that enhances the user experience by remembering application state across sessions. Its multi-instance safety features ensure reliable operation even when multiple XeFM processes are running simultaneously.

The system is designed to be transparent to the user - it works automatically in the background, gracefully handling errors and ensuring that XeFM continues to function even if state operations fail.