# Favorites — Implementation

The Go to Favorite picker (`favorites`, **J**) lists two sources, and
`add_favorite` (**B**) adds to the second one. End-user behavior is in
[NAVIGATION_DIALOGS_FEATURE.md](../NAVIGATION_DIALOGS_FEATURE.md#favorites-j);
this covers where the rows come from and why. Background: discussion #475,
which split bookmarks (places, kept by XeFM) from tags (attributes, kept on the
file by the OS).

## Two sources, one list — `xefm/favorites.py`

| Source | Where | Removable from the picker | Order |
|---|---|---|---|
| `FAVORITES` | `~/.xefm/config.py`, via `config.get_config_favorites()` | No | As written, first |
| Added with **B** | state DB, key `favorites` | Yes | As added, after the config rows |

This is the shape `xefm/server_list.py` already has for Connect to Server, and
for the same reason: XeFM does not rewrite a user-authored Python file, so a row
the user wrote stays theirs. `remove_favorite` refuses a config row and returns
`False`, which is exactly what `show_filter_list`'s `on_remove` needs to keep
the row in the list; the app logs where to remove it instead.

Rows are `FavoriteEntry(name, path, is_file, origin)`. The state DB holds a list
of `{"name", "path", "is_file"}` dicts, capped at `_MAX_SAVED`.

**Deduplication** is by `_key(path)`, string work only: a local path goes
through `normpath` + `normcase` (a trailing separator, or case on Windows, does
not make a second favorite); a URI only loses its trailing `/`. Nothing is
resolved — a symlinked favorite stays the path the user chose. Config wins a
collision, so promoting an added favorite into the config leaves one row.

`add_favorite` returns what it did:

- `ADDED` — new row, appended.
- `RENAMED` — the path was already an added favorite; its name (and `is_file`)
  is replaced in place, keeping its position. This is how a rename is spelled:
  **B** on a place that is already a favorite opens the name prompt prefilled
  with its current name, titled *Rename Favorite*.
- `IN_CONFIG` — the config already lists it; nothing is written. A shadow copy
  in the state DB would become a stale duplicate the day the config changes.
  The app checks this up front (`find_favorite`) and skips the prompt.
- `FAILED` — the state DB write failed (already logged).

## Nothing is probed (#430)

The picker must open without touching the filesystem — a few sleeping network
shares used to stack their timeouts into minutes of dead UI. That holds for the
added rows too, which is why **`is_file` is stored rather than asked**:
`XeFMApp.add_favorite` reads it from the pane's `file_info` (the listing's own
attribute record) when the favorite is added, and the jump trusts it.

Selecting a row goes through `_jump_pane_to`, the provisional move every
"directory you cannot see" picker uses: the pane moves, lists on a worker, and
snaps back if the listing fails. A file favorite passes the file's parent plus
`select_name`, which lands the cursor on the file instead of restoring the
remembered cursor. A file that has since been deleted simply leaves the cursor
where the listing put it.

### The old name, `FAVORITE_DIRECTORIES` (#525)

The field was `FAVORITE_DIRECTORIES` until it could name files. Two places keep
an old config working:

- `config._copy_missing_fields` — a config with the old name and no
  `FAVORITES` has its own list adopted as `FAVORITES` *before* the template's
  missing fields are copied in. Otherwise it would also get the template's
  Home / Documents / Downloads / Desktop, which the user may have deleted.
- `config._favorite_rows` — reads `FAVORITES`, then the old list if it is a
  different object (both set → joined, new first; adopted → read once).
  Duplicate paths are dropped later by `favorites.get_favorites`, as usual.

### A config row that names a file (#525)

A `FAVORITES` row has no `is_file`: it is written by hand (or loaded
from the user's own list), and asking the filesystem when the config loads is
exactly the probe #430 removed. So the jump finds out instead. Listing a file
raises `NotADirectoryError`; `FileListManager.compute_listing` returns that as
`not_a_directory` without logging, and `apply_listing` records it as
`listing_not_dir`. `_jump_pane_to` — when it was not already given a
`select_name` — marks the pane `_lands_on_file`, which tells `apply_listing` not
to log "Not a directory"; its `landed` callback then restores the pane and jumps
again to the parent with `select_name`. Any other navigation that lists a file
still gets the error line. History and drives rows go through the same jump, so
they gain the same behavior for free.

## The add flow — `XeFMApp.add_favorite`

1. Build up to two candidates: the pane's directory (not in a virtual pane,
   which has none of its own) and the focused entry (if any).
2. One candidate → straight to the name prompt. Two → a `ChoiceDialog` with the
   directory first, so **B Enter** adds where you are. Labels carry names, not
   full paths: `ChoiceDialog` sizes to its widest label, clamped to the window.
3. `_name_favorite` shows the name prompt (default: the entry's own name, or the
   full path for a root that has none) and calls `add_favorite`.

The row context menu's **Add to Favorites…** (`_add_cursor_favorite`) skips
step 2: a right-click already names its row, so that row is the candidate. Both
paths get `(entry, is_file)` from `_cursor_favorite_target`.

## Tests

`test/test_favorites.py` fakes the state manager and the config rows, like
`test_server_list.py`; `test/test_favorite_directories.py` still covers the
config side's no-I/O contract.
