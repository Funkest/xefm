# File List Layouts — Implementation

Issues #633 (attributes: obtaining per-entry values) and #756 (layouts:
presenting them), designed together in conversation on 2026-10-28. User-facing
page: `doc/FILE_LIST_LAYOUTS_FEATURE.md`.

## The split

Two layers, kept apart so one value can be shown in several places and ways,
and so that showing something is the user's choice, never the provider's:

| Layer | Module | Config table | Owns |
|---|---|---|---|
| Attributes | `xefm/attributes.py` | `ATTRIBUTES` | what a value is, how and when it is computed, caching, invalidation |
| Layouts | `xefm/layouts.py` | `LAYOUTS`, `LAYOUT_RULES` | which columns and markers a row has, formats, the per-folder choice |

`file_pane.py` draws a row from the effective layout; `file_list_manager.py`
sorts by an attribute; `app.py` holds the per-tab choice, the actions and the
menus.

## Decisions, and why

These were settled before any code. Each is a place a later change should not
quietly undo.

- **Names.** `LAYOUTS` / `LAYOUT_RULES`, not `VIEWS` (reads as the viewers) nor
  `FILE_LIST_LAYOUTS` (a file manager's tables need no `FILE_`; compare
  `FILTERS`, `FAVORITES`). `LIST_` was rejected too: "list" is one of the
  layouts Explorer offers, and thumbnails would not be a list.
- **`kind`** is in every layout from the start (`'details'` only today), so
  tree and thumbnail layouts (#638) are an addition, not a reshaping. Attributes
  and formats do not depend on the kind; only `columns`/`markers` do.
- **No `FORMATTERS` table.** A format is a built-in name or a plain function in
  the column spec; width and refresh go on the column. A named table bought
  nothing a Python variable does not. Built-in names stay, because a layout
  contributed as TOML data cannot hold a function. A table can be added later
  without breaking anything.
- **Markers belong to a column**, each with its own `side` (default `after`),
  because what a marker decorates depends on its purpose — tags mark the name,
  an "estimated" flag would mark the size.
- **Enum `values`** carry the value's *label* (its meaning — the sort dialog
  and later File Details use it) and a *color* that is only a default display
  hint; a layout's format overrides the look entirely.
- **Rules are separate from layouts and only `config.py` writes them.** A layout
  with an `auto` predicate would let an extension change how folders look just
  by being installed, and the order between several packages' predicates is
  undefined. Extensions contribute `attributes` and `layouts`, never rules.
- **Two kinds of non-built-in attribute: `auto` and `on_request`.**
  Automatic ones are computed for **every row** of the listing in the
  background as soon as the layout on screen draws them — no visible-row
  scheduling. Anything too slow for that (a recursive folder size) is not an
  automatic attribute; it is computed only when the user asks
  (`calculate_folder_sizes`, `compute_values`), for the entries asked about.
  Visible-row scheduling, prefetch margins and cancellation on scroll were
  designed and then dropped as the cost of trying to show expensive values
  automatically.
- **Sort and filter never wait for a value.** They read what the store already
  has. `EntryInfo.attr()` is cache-only everywhere — UI thread or worker — so
  one rule covers actions, sort keys and filters.
- **An attribute sort is an overlay for one directory.** It never replaces the
  tab's `sort_mode`; it holds across re-reads of that directory (file
  monitoring re-reads often) and is dropped on leaving it, so the persistent
  sort is the fallback. Rows without a value go last in both directions. An
  automatic attribute's row in the sort dialog is greyed until every row has
  its value; an on-request one is always offered.
- **Cache lifetime.** Across a re-read of the same directory a value is kept
  when the entry's `(size, mtime)` is unchanged; a `directory` provider is run
  again on every re-read (its old values stay on screen until replaced); a
  different directory or `reread` starts afresh.
- **Pane-level values** (a Git branch) are out of scope: an attribute is per
  entry. The status bar is a later issue.
- **Git status is not core.** It is the first non-built-in user of the
  `directory` shape, to be written in xefm-extensions.
- **Everything new is Preview** (`config.ATTRIBUTES`, `config.LAYOUTS`,
  `config.LAYOUT_RULES`, `manifest.contributes.attributes` / `layouts`,
  `EntryInfo.attr`, `Cell`).

## Attributes — `xefm/attributes.py`

`Attribute` is frozen data: `name`, `label`, `type` (`TYPES`), one of `entry`
/ `directory`, `values`, `where`, `compute`, plus two internal hooks for
built-ins: `sync(path, record)` and `applies(path)`.

Built-ins (`BUILTIN`):

| Name | Kind | Value |
|---|---|---|
| `name`, `ext`, `size`, `mtime` | sync | off the listing's record (`dir_scan` attrs); never cached |
| `tags` | auto, per entry | `tags.read`, only where `store_for(path).cheap`; fills `tags.SEEN` |
| `total_size` | on request | a file's size (sync half); a folder's `UsageScan` total |

`SORT_MODE_OF` maps the four sync names to the built-in sort modes, which is
why the sort dialog does not list them twice.

### `AttributeStore`

One per pane dict (tab), created lazily by `store_of(pane)` and kept in
`pane["_attr_store"]`, so a hidden tab keeps what it computed. A `WeakSet` of
live stores backs `lookup()` for `EntryInfo.attr`.

- `sync(files, records, directory, wanted)` is called by `FilePane.draw` on
  every frame and returns at once unless `id(files)`, the wanted set or the
  directory changed. Otherwise it bumps the generation, drops stale values
  (`_drop_stale`, see *Cache lifetime*), and queues one job per directory
  group (`directory` providers; entries grouped by parent, so a search-results
  pane works) and one per missing entry.
- One daemon worker per store (`xefm-attrs`) drains the queue and exits after
  five idle seconds, as `TagCache` did. A job from an older generation is
  skipped; `_put` refuses a result from one.
- `on_ready` (module global, set to `XeFMApp._on_attrs_ready`) is called when
  the queue empties or every `_READY_EVERY` values, so a large folder fills in
  without a frame per row. The app turns it into `_attrs_dirty` and a pump
  wake.
- A provider that raises costs its value (`None`) and is logged once per
  attribute per generation.
- `request(name, paths, records, on_done)` runs an on-request computation on a
  thread of its own with a cancel `Event`; a new directory or `clear()` sets
  it. `total_size` runs `UsageScan.run_sync` with that event as its cancel
  flag.
- `ready()` (every applicable row has a value), `snapshot()` (values for a
  sort, taken on the UI thread), `forget()` (after XeFM wrote tags), `clear()`.

## Layouts — `xefm/layouts.py`

`Layout(name, label, kind, columns)`; `Column(attr, format, width, align,
priority, refresh, markers)`; `Marker(attr, format, side, max_width)`.
`BUILTIN_DEFAULT` reproduces the old fixed row: `name` (marker `tags`), `ext`,
`total_size`, `mtime` with priority 1.

`FORMATS` maps each type to its named formats; the first is the default, except
`time`, whose default follows `DATE_FORMAT`. `resolve_format` turns a column's
or marker's `format` into a `Resolved` (function, built-in or not, width,
align, mono, refresh). `render` calls it — a built-in one with a `Row`
(`is_dir`, `ok`, `attr`), a user one with an `EntryInfo` — and normalizes the
result to a list of `Cell`; a user format that raises draws nothing, logged
once.

`effective(pane)`: `pane["layout"]` (chosen by hand), else
`pane["_layout_auto"]` (the rules' answer), else `default`. An unknown name
falls through, so a saved choice whose layout was removed from the config
does not break the pane and comes back if the layout does.

`resolve(path)` runs the rules on the listing worker (`XeFMApp._list_pane`),
and the answer rides the result as `layout_auto`; `_process_result_queue`
installs it, even when the listing itself is dropped as unchanged.

## Drawing — `FilePane`

`draw` gets the effective layout, the records (`_records`, rebuilt once per
`_listing_entries` identity), syncs the store, and `_plan`s the columns:

- `name` is flexible; `ext` measures the widest split extension as before;
  every other column is its format's width plus the room reserved for its
  markers (`max_width + COL_GAP` each), so a marker never moves the values.
- While the name would be under `MIN_NAME_W`, the column with the lowest
  priority (rightmost on a tie) is dropped — the old date rule, generalized.

`_draw_row` keeps the whole row pipeline (fills, cursor, hidden and cut fades,
inactive dimming) and then draws each placed column. On the name column the
markers sit against the name and the name is elided by their actual width on
that row; `_draw_value` aligns a value column's cells inside the column and
draws its markers either side. Cell colors go through `_cell_fg`: a role or
Finder color name, washed by the inactive-pane dim and floored at `LC_LARGE`,
exactly as the tag dots were; `ink=False` as for every column.

A row with no listing record (a pane built by hand in a test, a row the
listing never saw) draws the built-in columns from `file_info`'s
`size_str`/`date_str`.

The default layout's output was compared character by character against the
fixed-column code at widths 80, 40, 30 and 20 with both `DATE_FORMAT`s, and is
identical.

`refresh_interval` is the smallest `refresh` of a drawn column (the `relative`
time format asks for 60 s); `XeFMApp._layout_refresh_tick` repaints on it.

## Sorting

`XeFMApp._sort_overlay(pane)` returns `(name, values, reverse)` while
`pane["sort_overlay"]["path"]` is the pane's path, else clears it. Every
listing path (`_list_pane`, `_resort`, `_list_virtual`) passes it to
`FileListManager`, whose `_sort_by_overlay` re-orders the already sorted list:
directories first, rows with a value by `attributes.sort_key`, then the rest
in the pane's own order. Values that will not compare lose the overlay, not the
listing.

The sort dialog's extra rows come from `_attribute_sort_rows`: one per column
whose attribute is not a sort mode, with `mode = "attr:<name>"`. Choosing a
built-in key or a quick sort clears the overlay; **Reverse Sort** reverses it.
`get_sort_description` adds "(this folder)".

## Config, extensions, API

- `user_api._process_user_entries` loads `ATTRIBUTES`, then `LAYOUTS` (warning
  on an attribute nothing defines, loading the layout anyway), then
  `LAYOUT_RULES` (dropping a rule whose layout is unknown).
- `extensions`: `CONTRIBUTION_TABLES` gains `attributes` and `layouts`;
  `layouts` is a data kind. An attribute's `entry`/`directory` and a layout's
  `format` (in columns and markers) are references — `_refs_in` finds them for
  `xefm ext check`, `_value_for` / `_layout_refs` import them.
- `TABLE_KEYS` has `ATTRIBUTES` and `LAYOUTS`; the API snapshot was
  regenerated.

## State

`pane["layout"]` is saved with the pane state and with each tab
(`_save_tabs` / `_restore_tabs`). `pane["sort_overlay"]` is not saved: it is
about one visit to one directory.

## Tests

`test/test_list_layouts.py` (tables, rules, formats, the store, drawing, the
attribute sort, `EntryInfo.attr`); `test/test_extensions.py`
(`test_attribute_and_layout_contributions`); `test/test_tags.py` (`tags` as an
attribute). The existing pane tests (`test_file_pane_*`,
`test_date_column_width`) run unchanged against the default layout.

## Not done yet

- Hand checks: GUI and TUI on macOS, Windows; a real Git working tree through
  an extension.
- The Git status extension in xefm-extensions.
- Tree and thumbnail kinds (#638).
- Column headers (agreed: not in the first release).
- Pane-level values (branch) in the status bar.
