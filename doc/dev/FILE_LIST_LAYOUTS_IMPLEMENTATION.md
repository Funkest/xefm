# File List Layouts — Implementation

Issues #633 (attributes: obtaining per-entry values), #756 (presenting them)
and #789 (explaining them), designed in conversation on 2026-10-28 to
2026-10-30 — the decisions are recorded on #756. User-facing page:
`doc/FILE_LIST_LAYOUTS_FEATURE.md`.

## The parts

| Part | Module | Config | Owns |
|---|---|---|---|
| Attributes | `xefm/attributes.py` | `ATTRIBUTES` | what a value is, how and when it is computed, caching, invalidation |
| Layouts | `xefm/layouts.py` | `LAYOUTS`, `DEFAULT_LAYOUT` | presentation: which usual columns, their order and formats — taste and width |
| Extras | `xefm/layouts.py` | `EXTRAS` | content: what a folder adds (tags, Git status) as markers and columns, with a default `when` |

A pane draws `layouts.compose(layout_of(pane), active_extras(pane))`.
`file_pane.py` draws it; `file_list_manager.py` sorts by an attribute;
`app.py` holds the per-tab choices, the actions, the menus and the legend.

## Decisions, and why

Each is a place a later change should not quietly undo.

- **Presentation and content are separate and combine.** A first version had
  one `LAYOUTS` choice per tab, picked by first-match `LAYOUT_RULES`. That
  mixed what is chosen by taste and screen width (short dates, joined names)
  with what depends on the folder and the task (Git status), so every
  combination needed its own layout, and Git and another extra could not show
  together. `LAYOUT_RULES` is gone; a config still using it gets a warning.
- **Names.** `LAYOUTS` (not `VIEWS`, which reads as the viewers; no `FILE_`
  prefix, which a file manager's tables do not need — compare `FILTERS`) and
  `EXTRAS`.
- **`kind`** is in every layout from the start (`'details'` only today), so
  tree and thumbnail layouts (#638) are an addition.
- **No `FORMATTERS` table.** A format is a built-in name or a plain function on
  the column or marker. Built-in names stay because TOML cannot hold a
  function.
- **An extension may propose how its extra is shown; the user decides.** An
  extra carries `when` and its placement; installing the package is enough to
  see it where it applies. The user overrides per tab (Auto / On / Off, like
  sort and filter, persisted with the tab and copied to a new one) and in
  `config.py` key by key under the same name (`{'git': {'when': 'never'}}`),
  as theme overrides work.
- **Tags are a built-in extra**, so built-in and extension decorations take
  one path and `LAYOUTS` holds presentation alone.
- **Placement.** A marker is `on` a column (`name` by default, and when the
  named column is absent), `before` or `after` its text. A column goes `after`
  a column, `replace`s one (to save room; it inherits the priority unless it
  gives its own; the replaced built-in still sorts), or goes at the end —
  also when the named column is absent or already replaced.
- **Tight rows when extras are sparse — the deciding case.** Nothing is
  reserved for what a value *might* need. Per listing, measured with the real
  font: a marker slot is as wide as its widest use on any row, and absent when
  unused; an extra's column is as wide as its widest value, and absent when it
  has none. The accepted cost: the columns shift once when an automatic
  attribute's values land on entering a folder (one shift, since `read`
  answers a folder at once; none on a re-read).
- **Position identifies an extra where position is fixed.** On a value column
  and in the name's `before` gutter, each extra used in the listing has its own
  slot, in definition order, on every row — names start in one column. After
  the name, marks follow the name and are told apart by glyph and color only.
  Extensions are advised to put a sparse state `before` the name.
- **`max_width` is gone**: it counted cells, i.e. assumed a monospaced font (a
  proportional `●` measured just over one cell and was elided away). Widths are
  measured; what remains is `limit`, a count of a format's cells (the tag dots:
  three).
- **Collisions are reported**, not prevented: at load, each extra's markers
  are rendered for every declared `enum` value (tag dots for every tag color)
  and a glyph two extras draw in the same color gets a config warning.
- **The legend is a Help section**, not a command (#789): Help is where a user
  goes when something on screen is unclear. **Markers in this pane** comes
  first when the active tab shows any, lists only its active extras, and is a
  short list, not a table — Help's Tab/Shift-Tab start from the links on the
  first screen, and a long legend pushed them off it. Help is Markdown, so a
  mark's color is named in words.
- **One provider function, `read(directory, entries)`.** Named for what it
  does, not the unit it batches by; the folder is an explicit argument rather
  than an implicit promise about `entries`. XeFM picks the batch: a whole
  folder for an automatic attribute, one entry per call for an on-request one.
- **Two kinds of non-built-in attribute: `auto` and `on_request`.** Automatic
  ones are computed for every row of the listing in the background as soon as
  something on screen draws them. Anything too slow for that (a recursive
  folder size) is computed only when asked (`calculate_folder_sizes`,
  `compute_values`).
- **Sort and filter never wait for a value.** `EntryInfo.attr()` is cache-only
  everywhere.
- **An attribute sort is an overlay for one directory**: it never replaces the
  tab's `sort_mode`, holds across re-reads, and is dropped on leaving. Rows
  without a value go last both ways. An automatic attribute's row is greyed
  until every row has its value. The rows offered are the layout's columns and
  every attribute of the tab's active extras.
- **Cache lifetime.** A re-read runs every automatic attribute's `read` again
  for the whole folder, since a Git status changes without the file changing;
  old values stay on screen until replaced. An on-request value is kept while
  its entry's `(size, mtime)` is unchanged. Another directory or `reread`
  starts afresh.
- **Out of scope for now:** pane-level values (a Git branch), describing the
  cursor row's marks in the status bar, column headers.
- **Everything new is Preview** (`config.ATTRIBUTES`, `LAYOUTS`,
  `DEFAULT_LAYOUT`, `EXTRAS`, the three manifest kinds, `EntryInfo.attr`,
  `Cell`).

## Attributes — `xefm/attributes.py`

`Attribute` is frozen data: `name`, `label`, `type` (`TYPES`), `read`,
`values`, `where`, `compute`, plus two internal hooks for built-ins:
`sync(path, record)` and `applies(path)`.

| Name | Kind | Value |
|---|---|---|
| `name`, `ext`, `size`, `mtime` | sync | off the listing's record (`dir_scan` attrs); never cached |
| `tags` | auto | `tags.read` per entry, only where `store_for(path).cheap`; fills `tags.SEEN` |
| `total_size` | on request | a file's size (sync half); a folder's `UsageScan` total |

`SORT_MODE_OF` maps the four sync names to the built-in sort modes.

### `AttributeStore`

One per pane dict (tab), created lazily by `store_of(pane)` and kept in
`pane["_attr_store"]`. A `WeakSet` of live stores backs `lookup()` for
`EntryInfo.attr`.

- `sync(files, records, directory, wanted)` runs on every draw and returns at
  once unless the listing, the wanted set or the directory changed. Otherwise
  it bumps the generation, drops stale values (`_drop_stale`), and queues one
  `read` per attribute per folder (rows grouped by parent, so a search-results
  pane works).
- One daemon worker per store (`xefm-attrs`), exiting after five idle seconds.
  A job of an older generation is skipped; `_put` refuses its results.
- `version` is bumped whenever a value comes or goes; the pane re-measures on
  it.
- `on_ready` (set to `XeFMApp._on_attrs_ready`) is called when the queue
  empties or every `_READY_EVERY` values.
- A `read` that raises, or returns the wrong number of values, costs that
  call's values (`None`), logged once per attribute per generation.
- `request(name, paths, records, on_done)` runs an on-request computation one
  entry per call on its own thread with a cancel `Event`, set by a new
  directory or `clear()`. `total_size` runs `UsageScan.run_sync` with it.

## Layouts and extras — `xefm/layouts.py`

`Layout(name, label, kind, columns)`; `Column(attr, format, width, align,
priority, refresh, markers, extra)`; `Marker(attr, format, side, limit, slot)`.
`Extra(name, label, when, markers, columns)` with `ExtraMarker(marker, on)`
and `ExtraColumn(column, after, replace)`. `BUILTIN_DEFAULT` reproduces the old
fixed row (`name`, `ext`, `total_size`, `mtime` priority 1);
`BUILTIN_EXTRA_SPECS` holds `tags` as the spec `EXTRAS` takes, so a config
entry of the same name merges over it.

- `FORMATS`, `resolve_format`, `render`: as before — a built-in format gets a
  `Row`, a user one an `EntryInfo`, and the result is normalized to `Cell`s.
- `extras_for(path)` evaluates every extra's `when` on the listing worker
  (`XeFMApp._list_pane`); the result rides the listing as `extras_auto` and
  `_process_result_queue` installs it as `pane["_extras_auto"]`, even when the
  listing itself is dropped as unchanged.
- `active_extras(pane)`: definition order; On, or Auto and in `_extras_auto`.
- `compose(layout, extras)` places columns (replace / after / end) and attaches
  markers (`on`, else the name), each tagged with its extra as `slot` / `extra`.
  Results are cached per `(layout, extra names)`.
- `glyphs(extra)` renders each declared value through the marker's format —
  the legend, and with `by_color` the collision check (`collisions`).

## Drawing — `FilePane`

- `_measure` walks the listing once per `(files, store.version, layout)`: for
  each column, each side, each slot, the widest group any row draws; for each
  extra's column, its widest value. The name's `after` markers are skipped.
- `_plan` places columns: a value column's width is its format's (or its
  measured width, for an extra's column without `width`), plus the used
  `before` and `after` slots. The name's used `before` slots are a gutter.
  An extra's column with no value is left out. Then the priority rule drops
  columns while the name is under `MIN_NAME_W`.
- `_draw_row` draws the name with its gutter (`_draw_slots`: each slot at its
  place, blank where this row has none), the name elided by that row's `after`
  markers, then each value column (`_draw_value`: value aligned inside, slots
  either side). `_slot_groups` gathers a row's markers by slot, applying
  `limit`. Cell colors go through `_cell_fg`, as the tag dots always did.
- A row with no listing record draws the built-in columns from `file_info`.

The default layout's text output was compared character by character with the
fixed-column code at widths 80/40/30/20 and both `DATE_FORMAT`s.

## Sorting

`XeFMApp._sort_overlay(pane)` returns `(name, values, reverse)` while
`pane["sort_overlay"]["path"]` is the pane's path, else clears it; every listing
path passes it to `FileListManager._sort_by_overlay`. The dialog's extra rows
come from `_attribute_sort_rows` (`mode = "attr:<name>"`).

## App

- `choose_layout` / View → Layout ▸; `choose_extras` / View → Show ▸ (one
  submenu per extra, Auto / On / Off, then Calculate Folder Sizes and Compute
  Values — moved there to keep View within 23 rows on an 80×24 terminal).
- `pane["layout"]` and `pane["extras"]` (`{name: 'on'|'off'}`) are saved with
  the pane and each tab; `_saved_extras` keeps a state for an extra the config
  no longer has. `sort_overlay` is not saved.
- `_help_markers_section` builds the legend.

## Config, extensions, API

- `user_api._process_user_entries` loads `ATTRIBUTES`, `LAYOUTS`,
  `DEFAULT_LAYOUT` (warning and `default` when unknown), then `EXTRAS` (merged
  over a built-in of the same name; a warning for attributes nothing defines),
  then reports collisions.
- `extensions`: kinds `attributes`, `layouts`, `extras`; `layouts` and `extras`
  are data. `read`, `when` and every `format` are references when they hold a
  colon — `_refs_in` finds them, `_value_for` / `_layout_refs` import them. An
  `EXTRAS` entry also in `config.py` is merged with config's keys winning,
  instead of config.py replacing it whole.

## Tests

`test/test_list_layouts.py` (tables, extras, compose, formats, the store,
drawing — the gutter, sparse extras taking no room, slots and `limit` — the
attribute sort, the app's per-tab state and the Help legend);
`test/test_extensions.py` (contributions, and an extra overridden key by
key); `test/test_tags.py`.

## Not done yet

- Hand checks: GUI and TUI on macOS and Windows; a real Git working tree.
- The Git status extension in xefm-extensions.
- File Details showing attribute values (#789 B).
- Tree and thumbnail kinds (#638).
