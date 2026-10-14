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
  its values in the popup described below, the current one highlighted. A
  click on an on/off chip still flips it.
- `toggle_kind` / `toggle_modified` / `toggle_size` exist as unbound
  `search.` actions, like the other options.

The case and subfolder options are gated to `filename` / `content` now: the
index reads its own query and always descends.

## Recent searches

History is input, so it hangs from the input. The dialog takes
`history(mode)` and `on_history_remove(mode, query)`:

- **opening it:** a `▾` at the query field's right end (`_history_rect`),
  or `Alt-↓`;
- **the list:** that mode's queries in the popup under the field. Picking
  one fills the field (`_use_query`) and searches; the remove key
  (`remove_list_item`, the pickers' own) forgets one;
- **storage:** the app keeps one state key per mode (`_SEARCH_HISTORY`; the
  index keeps #579's `index_search.history`) and records a query when its
  results are fed with Enter;
- **the result list:** never shows history, and is empty while the field
  is.

## The popup

The history and a choice chip's values open in the completion popup that
`InputDialog` uses for Tab candidates (`CandidateListOverlay`), not a menu:

- **The same on every backend.** A `popup_menu` is native on macOS and a
  widget elsewhere, and its widget form opened *under* the dialog in a
  terminal (z 60 against the dialog's 70). It was unseen, unclosable, and
  stacked with every click. puikit#159 fixes that for every caller.
- **It hosts like the completion popup.** It is a layer one above the
  dialog with `interactive=False`, so the keys stay with the dialog:
  - `_popup_key`: `↑`/`↓` move, Enter picks, Esc closes, the remove key
    forgets a query, and any other key closes the popup and goes on as
    usual, so typing types and Tab switches modes.
  - `_popup_click`: clicks over the popup pick a row; a click elsewhere
    closes it and still does its job, unless it is on the chip or `▾` that
    opened it, which then only closes it.
- **One at a time.** `_open_popup` closes the previous one.
- **Placement.** `_place_popup` hangs it from its dialog-local anchor every
  frame through `overlay_geometry`, from the layer's `screen_rect`. It
  draws after the dialog, so there is no flash.

The popup is XeFM's own (`xefm/candidate_list.py`). A widget every text
field shares is PuiKit's by the project's rule, and moving it there is left
for later.

## Tests

`test/test_search_filters.py`: kinds, the predicate (AND, files-only size,
midnight and New Year), `describe`, `index_query` for both engines, choice
options (default, stepping both ways, unknown values refused, "on", reset),
and in the app:

- the chips alone searching filenames;
- the chips narrowing content, and content needing words;
- `Tab` stepping through every mode;
- a choice chip's values in the popup, picked by keys and by click, closed
  by the chip and Esc, one at a time;
- the history popup from `Alt-↓`, the remove key, and typing closing it;
- Enter recording the query.

`test/test_os_index.py`: the index as a mode of the dialog, with its history
off the result list, and index results checked against the chips (the chips
becoming the query when the field is empty).
