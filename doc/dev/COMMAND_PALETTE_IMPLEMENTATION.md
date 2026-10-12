# Command Palette — Implementation

The design and its trade-offs are in discussion
[#550](https://github.com/crftwr/xefm/discussions/550) (requests #530, #531).
This page records how it is built and which of that post's open questions were
answered how.

## Pieces

| Where | What |
|---|---|
| `xefm/actions.py` | `command_palette` (FILER, `Ctrl-T` via the `_config.py` template); `describe_list_item` (FILTER_LIST, `F1`); `Action.details` |
| `xefm/filter_list_dialog.py` | opt-in `to_right`, `to_detail`, `to_help` hooks; `_ColumnRow`; `describe_selected()` |
| `xefm/app.py` | `show_command_palette`, `_palette_actions`, `_palette_keys`, `_palette_help`; Tools menu item; help row |
| `xefm/user_api.py` | a user action's docstring — or its `'description'` entry, which replaces it whole — split PEP 257-style (`_split_description`): summary → `description`, body → `details` |
| `test/test_command_palette.py` | picker hooks and the palette against a live app |

## The picker extensions

All three are general-purpose and **off unless passed**; a call site that uses
none of them builds exactly the dialog it did before (plain text rows, no
`row_factory`, same hint).

- **`to_right(value)`** switches the `ListView` to widget rows: items become
  `(label, right)` pairs and `_ColumnRow` draws the label (elided with the
  picker's `ellipsis` / `elide_where`) and the right column (muted, whole,
  1 unit from the edge). The column is dropped when it would take more than half
  the row, so a narrow box keeps the names. The selection fill comes from
  `ListView._draw_widget_rows` passing the selection colour as the child's `bg`
  hint, so the row paints only text. Matching still runs against `to_label`
  alone — the column is displayed, not searched.
- **`to_detail(value)`** reserves one line (the hint style's line height) above
  `hint_content_bottom`, with a 0.4-unit gap on vector backends and none on a
  grid, and draws the highlighted row's text there, elided. It is deliberately
  **not** in the hint band: `KEY_BINDINGS_IMPLEMENTATION.md` keeps the band for
  keys only.
- **`to_help(value)`** enables `describe_list_item`. `handle_event` claims it by
  **action** (`is_action_for_event(..., context=FILTER_LIST)`), ahead of the
  query field, the same way `remove_list_item` is claimed — so a rebind works,
  and F1 never falls through to the inherited COMMON `help`. The page opens with
  `show_markdown` at the picker's own layer z + 10 (`_layer_z`), and its close
  pops only itself, which is what leaves the query, filtered rows and cursor
  untouched. The hint band gains `F1 help` only when `to_help` is given.

## The palette's rows

`_palette_actions()` walks `registry.actions(FILER)` — the context's own table,
then inherited COMMON, then user actions registered into FILER — and keeps an
action when:

- it is a user action, or the app's `_filer_handlers()` has a handler for it;
- it is not refused by the running frontend (`_BACKEND_GATED`, the same gate the
  help dialog applies — `menu` when an OS menu bar owns it);
- it is not `command_palette` itself.

Viewer contexts are out on purpose: their handlers belong to the open viewer,
and `XeFMApp._run_action` cannot run them from the file list.

Enter runs the action through `_menu(name)` → `dispatch` → `_run_action`, the
same path a menu item takes, so user-first resolution, the `_invoking` guard and
`run_guarded` all apply. The selection requirement is **not** enforced: that is
a property of a key binding (it picks between `move_files` and
`create_directory` on `M`), and choosing an action by name is unambiguous. The
handlers already act on the focused item or report why they cannot.

## Help text

`Action.description` and `Action.details` are a docstring's two halves — the
summary line and the body. A user action gets both from its docstring, or from
an `ACTIONS` entry's `'description'`, which is read the same way and replaces
the docstring whole (mixing a half from each would leave no way to tell which
text is on screen). There is deliberately no second key for the body: one rule,
the one every Python function already follows, and a one-line `'description'`
from a config written before the palette reads exactly as it did.

Built-in long help lives in one table, `_DETAILS` in `xefm/actions.py`, which
`_a()` reads for the `filer` and `common` contexts only — `copy_files` in
`dir_diff` is the same name doing something else, and must not get the file
list's page. An action whose one-line description says everything (cursor
movement, pane and log nudges, plain select/unselect) has no entry; its page is
the description and the facts. `test_every_help_entry_names_a_real_action`
catches a misspelt key, which would otherwise leave an action silently without
its page. Key names in the prose are the defaults and say so; the page's
**Keys** line is the live binding.

The page is the description, the help, then the facts (keys, selection
requirement, source, former names) as labelled lines joined by hard breaks —
not a list, which hung a lone bullet off the common one-fact case — and not the
action name, which is already the title.

`show_markdown` sizes its box from an estimate of the *wrapped* rows
(`_wrapped_rows`, table rows counted as one) rather than the source line count,
so a page of prose opens at its full height instead of already scrolling. This
applies to every Markdown dialog; the box is still capped at 80% of the window.

`_palette_keys` resolves in the FILER context only and returns an empty string
for an unbound action — an empty column reads as "no key" where a dash on many
rows would be noise. `_palette_help` builds the F1 page from the description,
`Action.details`, the keys, the resolved selection requirement, the source and the
aliases.

## Answers to the discussion's open questions

1. **Search descriptions?** Not now — names only, so no `to_match_text` hook
   yet. `FilterListDialog` has no ranking, and description hits would bury name
   hits. The hook is cheap to add if that changes.
2. **Detail row or F1 first?** Both shipped; the row costs one line.
3. **Scope.** FILER + COMMON + the user's `ACTIONS`. `PROGRAMS` stay in their
   own picker (`X`).
4. **Actions that cannot run now.** Shown, not hidden or dimmed (see above).
5. **Palette key.** `Ctrl-T` (the Tools menu, where the palette also lives).
   `Ctrl-Shift-P` is out: Windows Terminal takes it, and a POSIX terminal
   cannot tell it from `Ctrl-P` (`copy_paths`). `Shift-P` is out because a
   Shift+letter in XeFM is a variant of its letter (C / Shift-C, M / Shift-M),
   and P's variants belong to archives. `Ctrl-K`, the web's palette chord, is
   out because a missed Ctrl lands on `K`, `delete_files`. A missed Ctrl on
   `Ctrl-T` lands on `T`, unbound. `Ctrl-T` is also the search dialog's
   example for `search.toggle_case`, which is a different surface. VS Code's
   integrated terminal passes `Ctrl-T` through (hand-checked 2026-10-13).
6. **Key resolution.** Moot for F1: the picker checks `describe_list_item` by
   action name in the FILTER_LIST context and never resolves the key to `help`.

## #531

Not addressed here beyond the action → key column: finding *free* keys is a
per-context question with terminal-specific exceptions, and the discussion's
plan is to confirm that is what #531 wants before designing for it.
