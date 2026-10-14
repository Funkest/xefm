# Search Modes, Filter Chips and Recent Searches — Implementation

[#609](https://github.com/crftwr/xefm/issues/609), from the #579 hand check.
User-facing behavior is in
[`doc/SEARCH_OPTIONS_FEATURE.md`](../SEARCH_OPTIONS_FEATURE.md) and
[`doc/OS_INDEX_SEARCH_FEATURE.md`](../OS_INDEX_SEARCH_FEATURE.md).

The hand check found the OS index search worse than the OS's own:

- its query was written in a syntax few people know (`kind:`, `name:`);
- its results were seen only after Enter;
- its dialog listed past queries where results belong.

Three changes answer that, and each is meant to outlive this feature. They are
the first pieces of the planned advanced search.

## Modes

`ProgressiveSearchDialog` takes `modes` (what `Tab` steps through, in order),
`mode_names` (what the hint calls each) and `can_search(mode, query)`
(whether there is anything to search; by default, a query). The app passes
`("filename", "content")`, plus `"index"` when `_index_scope(pane)` allows
the OS index. `index_search` opens the dialog in that mode. Results stream
like any other mode's. `_iter_index_matches` runs `os_index.search` per
query, which is cheap for Spotlight. A failure is raised as `SearchFailed`,
which the dialog shows on its status line like an invalid pattern rather than
swallowing it as an empty result. The fed results pane's header names the
engine, the filters, and the query when there is one
(`_virtual_header_text`).

## Filter chips

`xefm/search_filters.py` declares three **choice options** (`Kind`,
`Modified`, `Size`) and what each value means:

- `predicate(values)` is `(name, attrs) -> bool` over a listing record
  (`is_dir`, `size`, `mtime`, the `dir_scan` record `tree_walk` already
  yields), so the walks filter **without a second stat**.
  `_iter_filename_matches` and `_iter_content_matches` take it as `keep`.
  Content applies it before reading a byte.
- The kinds are decided by **extension**, the same in every mode. That is
  coarser than Spotlight's content types, and it is the point: a chip must
  not mean one thing in filename search and another in the index.
- The index's results are paths only. Each is `stat`ed (`stat_attrs`) and
  checked with the same predicate. A path the index still lists but the
  disk no longer has is dropped.
- With the field empty, `index_query(engine, values)` turns the chips into
  the engine's own query: a Spotlight predicate (`kMDItemContentTypeTree`,
  `kMDItemFSContentChangeDate`, `kMDItemFSSize`) or `where …` Windows Search
  SQL (`System.Kind`, `System.DateModified` in UTC, `System.Size`). It only
  narrows what the index returns. Every result still goes through
  `predicate`, so the index filing something differently from the extension
  table cannot let a wrong file through.
- `can_search`: the chips search on their own in filename (`*`) and index
  mode, not in content, which needs words to look for.
- They are `persist=False` (`reset_transient` on open), like `Sub`.
- The chips are kept **apart from the query text** and ANDed with it. Tokens
  inside the field would need a token-aware text field in PuiKit, and a TUI
  rendition of it. The field stays plain text, and a raw `kind:pdf` still
  works in the index mode.

### Choice options in `xefm.options`

`Option.choices` is `((value, label), …)`; a choice option's default is its
first value.

- `OptionSet.set` keeps only a known value.
- `toggle(name, step)` steps through the values, wrapping, and `step=-1`
  goes back.
- `chips()` reports "on" as `is_set`: not the first value.
- The options box shows the value's label, sizes its column to the widest
  label, and takes `←` for the previous value.
- In the dialog, a set choice chip shows its value (`Images`). A click opens
  a `popup_menu` of the values, the current one checked, placed under the
  chip through the layer's origin (`_origin`). A click on an on/off chip
  still flips it.
- `toggle_kind` / `toggle_modified` / `toggle_size` exist as unbound
  `search.` actions, like the other options.

The case and subfolder options are gated to `filename` / `content` now: the
index reads its own query and always descends.

## Recent searches

History is input, so it hangs from the input. The dialog takes
`history(mode)` and `on_history_clear(mode)`:

- **opening it:** a `▾` at the query field's right end (`_history_rect`),
  or `Alt-↓`;
- **the menu:** a `popup_menu` under the field of that mode's queries, then
  *Clear Recent Searches*; picking one fills the field (`_use_query`) and
  searches;
- **storage:** the app keeps one state key per mode (`_SEARCH_HISTORY`; the
  index keeps #579's `index_search.history`) and records a query when its
  results are fed with Enter;
- **the result list:** never shows history, and is empty while the field
  is.

`popup_menu` rather than a new PuiKit widget: it is native on macOS and a
widget popup in a terminal, and needs nothing new. It gives up per-entry
removal, which *Clear* covers. A history-capable text field, the same in
every XeFM dialog with a query, would be a PuiKit component.

## Tests

`test/test_search_filters.py`: kinds, the predicate (AND, files-only size,
midnight and New Year), `describe`, `index_query` for both engines, choice
options (default, stepping both ways, unknown values refused, "on", reset),
and in the app:

- the chips alone searching filenames;
- the chips narrowing content, and content needing words;
- `Tab` stepping through every mode;
- a choice chip's value menu;
- the history menu from `Alt-↓`;
- Enter recording the query.

`test/test_os_index.py`: the index as a mode of the dialog, with its history
off the result list, and index results checked against the chips (the chips
becoming the query when the field is empty).
