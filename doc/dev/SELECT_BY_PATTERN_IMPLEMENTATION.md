# Select by Pattern — Implementation

Issue #544. Three file-list actions: `select_by_pattern`, `unselect_by_pattern`
and `select_same_extension`. User-facing behavior is in
[SELECT_BY_PATTERN_FEATURE.md](../SELECT_BY_PATTERN_FEATURE.md).

## Where things live

| Piece | Location |
|-------|----------|
| Action metadata + palette help pages | `xefm/actions.py` (`_a(...)` rows, `_DETAILS`) |
| Default bindings (`'`, `"`, none) | `xefm/_config.py`, File Selection block |
| Dispatch | `XeFMApp._filer_handlers` in `xefm/app.py` |
| Prompt | `XeFMApp.select_by_pattern(select)` |
| Matching + selection | `FileListManager.select_by_pattern`, `select_same_extension`, `_apply_bulk_selection` |
| Extension rule | `file_list_manager.file_extension` |
| Menu | Select menu in `XeFMApp._build_menu` |
| Help rows | Selection section of the help table in `xefm/app.py` (`select_same_extension` tagged "(Select menu)") |
| Tests | `test/test_select_by_pattern.py` |

## Matching is the filter's

`FileListManager.select_by_pattern` compiles the pattern with
`filters.matcher(pattern)` — the same entry point `_apply_filter_pattern` uses —
and calls it with each file's attribute record. That one call is what makes the
issue's requirement ("same name comparison as the filter, NFC, pane-relative")
hold without a second implementation:

- A typed pattern is split by `filters.split_globs` (spaces / `;` / quotes) and
  matched against `cmp_name` lowercased and composed.
- `cmp_name` is filled by `_assemble_listing` relative to the virtual pane's root,
  so on a search-results pane the glob sees `sub/a.txt`, not `a.txt`.
- A name registered in `FILTERS` resolves to its globs or its predicate.

The attribute record comes from `pane['_listing_entries']` (the pre-filter
snapshot, which has `size`/`mtime`/`ok`) so a predicate filter gets real values
through `EntryInfo.from_attrs`. A pane with no snapshot falls back to
`file_info`, which carries `is_dir` and `cmp_name` — enough for any glob.

A predicate that raises fails the whole action and changes nothing (logged as an
error). This is the opposite direction from the filter, which fails *open* and
shows everything; for a selection, "selected nothing" is the safe outcome.

Directories are skipped, matching `toggle_select_files`: the filter keeps
directories visible regardless of the pattern, so it has no answer for them.

## The prompt

`XeFMApp.select_by_pattern` reuses `show_history_input` with the Filter picker's
items minus the "clear filter" row: `filters.rows()` then `_filter_history()`.
Accepted patterns go through `_record_filter_pattern` (which already skips
defined-filter names), and the remove key uses `_forget_filter_pattern`. The two
prompts share one history on purpose — the pattern language is the same.

## Same extension

`file_extension(name)`: from the last dot, NFC, lowercased; `""` when the only
dot is a leading one or there is none. It deliberately ignores
`MAX_EXTENSION_LENGTH`, which governs the extension column and the extension
sort — a display constraint, not a grouping one. The focused item being a
directory is a refusal (`(False, msg)`), not a no-op success.

## Messages

`_apply_bulk_selection` reports how many files actually *changed* (newly added
or actually removed), not how many matched, and returns `(False, "No files …")`
when nothing matched. The app logs it through `_log_result`.

## Keys

`select_by_pattern` is `'` and `unselect_by_pattern` is `"` — cfiler's keys
for the same commands, beside the filter's `;` / `:`. Both are bound as glyphs,
not `QUOTE` / `Shift-QUOTE`, so they match the character whatever layout
produced it (JIS puts them on `Shift-7` / `Shift-2`), and a POSIX terminal
delivers them like any printable. The actions read these defaults from the
`_config.py` template (`default_keys` omitted).

PuiKit has no keypad key names, so Total Commander's `Num+` / `Num−` would
collapse to `+` / `-`, which are `diff_directories` (`Shift-EQUAL`) and
`reset_pane_boundary`.

`select_same_extension` ships unbound (`default_keys=()`, `[]` in
`_config.py`); its help row names the Select menu, which satisfies
`test_help_backend`'s rule that every unbound row names a route.
