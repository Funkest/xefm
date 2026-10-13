# Keymap Presets — Implementation

[#565](https://github.com/crftwr/xefm/issues/565) and
[#597](https://github.com/crftwr/xefm/issues/597), from discussion
[#343](https://github.com/crftwr/xefm/discussions/343). User-facing behavior is
in [`doc/KEYMAP_PRESETS_FEATURE.md`](../KEYMAP_PRESETS_FEATURE.md).

## Shape

`xefm/keymap_presets.py` holds `Preset` (name, label, description,
`bindings`, `free_letters`, `type_ahead`) and the `PRESETS` table: `afx` and
`orthodox`. Discussion #343 asked for one mechanism with several presets on
it, not a special-cased beginner mode, and that is the reason for this shape.

Since [#597](https://github.com/crftwr/xefm/issues/597) the presets are
**peers**. Each one is a complete keymap, the first launch asks which, and
`config.py`'s `KEY_BINDINGS` is laid over whichever is in force. Before
#597, the AFX table *was* the template's `KEY_BINDINGS`, and a preset changed
only the "untouched" actions (equal to the shipped value). That made AFX the
default, and the untouched test could not tell an old shipped value from a
deliberate one.

The AFX table lives in `xefm/keymap_afx.py`, as `bindings()`. The table moved
there verbatim from `_config.py`, comments and the per-platform desktop
overrides included. It is a function because those overrides branch on
`is_desktop_mode()` and `sys.platform`, and every call returns a new dict.
It is also where the viewers', dialogs' and search bars' keys live. Those
surfaces are the same under every preset, so the other presets start from
this table's copy of them.

Both presets are named for their lineage. AFX's is the single-key Japanese
filers: the X68000 file managers, then AFX (あふ), then cfiler. The preset
follows their style, not their exact keys. `FALLBACK = AFX` is the table in
force while nothing has been chosen. `ALIASES = {"default": "afx"}` and
`canonical()` keep the first name working, both in `KEY_PRESET` and in a
saved menu choice. `set_keymap_preset` compares canonical names, so
`KEY_PRESET = 'default'` does not block choosing AFX style from the menu.
A per-platform Explorer/Finder preset is one more entry.

`actions._template_bindings`, the built-in default for an action no table
mentions, reads `keymap_afx.bindings()` too. Every preset's table starts from
it, so only an action absent from all of them reaches that fallback.

## `table(name)` and `apply(config, name)`

`table(name)` builds one preset's whole keymap:

1. Start from `keymap_afx.bindings()`. For AFX, that is the result.
2. `free_letters` removes **typing keys** (`is_typing_key`: a bare letter or
   digit, or `Shift-<letter>`) from every action of the `filer` and `common`
   contexts. A viewer's own actions keep their letters, because nothing is
   typed into a viewer.
3. `bindings` replaces those actions' keys with a plain list. That drops any
   `selection` gate: AFX's `copy_files` is `{'keys': ['C'], 'selection':
   'required'}`, and an orthodox `F5` copies the cursor item when nothing is
   marked, which `_transfer` already does.

`apply` writes the result **into `config.KEY_BINDINGS`**. The keymap is built
from that table in several places: the app's `self.keys`, the shared
`config_manager.get_key_bindings()` that help and the menus resolve through,
and `DirectoryDiffView`'s own `KeyBindings`. Rewriting the one table they all
read is what makes a preset reach every surface without touching any of them.

1. `overrides(config)` is the table `config.py` was loaded with (extension
   key suggestions included). It is stashed on the config as
   `_KEY_BINDINGS_BASE` the first time, so switching presets back and forth
   starts from it each time instead of compounding.
2. Every entry in it replaces the preset's, whatever it equals. An entry
   under an **old action name** (`rename_file`) also removes the preset's
   entry under the current one (`rename`). `KeyBindings` matches current
   names first, so the preset's entry would otherwise win.
3. `config._KEY_TYPE_AHEAD` records the flag.

`replaced(config, name)` lists the `config.py` entries whose value differs
from preset `name`'s. `set_keymap_preset` logs it when non-empty. That is the
whole migration story for a `config.py` holding the old full AFX copy. Under
AFX the copy replaces nothing and stays silent. Under Orthodox the log names
what it overrides. Nothing deletes the entries automatically: telling a
copied default from a chosen key is exactly the guess #597 removed.

The shipped `_config.py` `KEY_BINDINGS` is `{}` with commented examples, each
one meaningful under every preset.

`test_no_two_actions_share_a_key_in_the_file_list` keeps the orthodox table
free of clashes. The ones it had to resolve: `F5` was `redraw` (now unbound),
`+` was `diff_directories` (now `Shift-F2`), `-` was `reset_pane_boundary`
(now unbound), and `Home`/`End` were select all / unselect all (now `Ctrl-A` /
unbound).

## Choosing

### The Orthodox table

`_ORTHODOX.bindings` follows Total Commander's default keys wherever XeFM has
the matching action. The user asked for it to match TC as closely as possible.
The reference was TC's keyboard map, from KEYBOARD.TXT as reproduced by
softpanorama and the DefKey / devcrea lists, which agree on the keys used here.

- A TC key with no XeFM action stays unbound. Examples: Alt-F8 command-line
  history, Ctrl-L occupied space, Ctrl-U swap panels.
- An XeFM action with no TC key is unbound under this preset (`[]`) when it
  would otherwise hold a key TC uses. Examples: `reveal_in_os` (Ctrl-R),
  `cursor_prev_selected` (Ctrl-Up), `redraw` (F5), `reset_pane_boundary` (`-`),
  `index_search` (Ctrl-F). `reset_log_height` (`_`) is unbound too, so
  type-ahead can reach `__init__.py`.
- Some actions are close but not exact, and are mapped anyway:
  - `duplicate_files` for Shift-F5 (TC prompts for the name; XeFM picks one);
  - `compare_selection` for Shift-F2 (TC marks the differences in both panels);
  - `drives` for Alt-F1 / Alt-F2 (TC's are per panel; XeFM's acts on the active
    one);
  - `connect_server` for Ctrl-F / Ctrl-N (TC's FTP connect / new URL);
  - `filter` for Ctrl-S (TC's quick filter);
  - `file_details` for Alt-Enter (properties).
- `reread` is new: it relists both panes, for TC's F2 / Ctrl-R. It has no key in
  AFX style.
- `command_palette` moves to Ctrl-Shift-P, because Ctrl-T is a new tab.

The table also names actions from PRs not merged yet: tabs, quick view, flat
view, back/forward, the file clipboard, `delete_permanently`. `apply` skips an
action the registry does not resolve, so the preset is right on a build with or
without them, and a missing action never holds a key for nothing.

`resolve(config, chosen)` returns `KEY_PRESET` from the config when it names a
preset, else the saved choice (state key `keymap.preset`), else **None**:
nothing has been chosen. Old names are mapped through `canonical`. `get(None)`
and an unknown name give `FALLBACK`; an unknown name is also logged.

### The first launch

With no preset chosen, `_keymap_preset` is None and `FALLBACK` is applied
for the moment. `run()` then calls `_ask_keymap_preset` in place of that
launch's tip of the day, so two dialogs never stack. A new install and an
upgrade from before presets are treated alike. Telling them apart was tried
first: an existing `config.py` meant AFX was kept without asking. That was
dropped because it made AFX a default after all, which #597 removes. The
cost is one question for upgrading users, and it is asked once.

The dialog is a markdown message box with one button per preset and no
Cancel. It is opened with PuiKit's `dismissable=False`, so Esc does nothing.
A preset button calls `set_keymap_preset`, which stores the choice. Quitting
with the dialog open stores nothing, so the next launch asks again.
`__init__` never opens the dialog, because tests construct the app without
`run()`.

`make keymap-reset` deletes the stored choice, for hand-checking the dialog.

`XeFMApp._apply_keymap_preset` runs right after the state manager exists, and
again in `reload_config` after the new config replaces the old one. It
rebuilds `self.keys` and clears `config_manager._key_bindings`.
`set_keymap_preset` stores the choice, applies it, and invalidates the two
surfaces that cache key names: the status bar's hint line, and the menu
(rebuilt) — the same pair `reload_config` already refreshes for #382. It
refuses, with a log line, when `KEY_PRESET` in the config names a different
preset.

The menu is **View → Keymap ▸**, one checked item per preset. A preset is
not an action, so the command palette does not offer the switch.

## Type-ahead

`on_event`: when no action matched and no menu mnemonic did,
`_type_ahead(event)` checks the flag. For a printable, non-space `char` with
no Ctrl/Alt/Cmd it calls `enter_isearch(quick=True)` and then dispatches the
same event to the panel, where the search bar is now the top layer. The key
that opened the search becomes its first character. Shift is allowed, since a
capital is typing.

`quick=True` keeps I-Search's prompt and matching, and changes only how the
search closes, which follows Total Commander's quick search. The user asked
for that much and no more: the display and the matching stay XeFM's.

- **The bar has no select, select-all or accept callbacks.**
  - `on_cancel` is `_isearch_stop`, so Esc keeps the match instead of
    restoring the origin.
  - `on_passthrough` is `_isearch_passthrough`. `ISearchBar.handle_event`
    hands it any KEY that is not typing, not one of the bar's remaining
    actions (prev/next match, cancel), and not Backspace/Delete
    (`_EDIT_KEYS`).
  - `_isearch_passthrough` closes the search and feeds the event to `on_event`,
    so Enter reaches `open_item` and F5 reaches `copy_files` on the match.
- **The status bar** shows `_quick_hints` (prev/next, close, "other keys act on
  the file") instead of the usual I-Search hint line.

The I-Search key (`enter_isearch()` with no argument) is unchanged.

## Not done

The Explorer/Finder preset, and presets as data packages
(#543).

## Tests

`test/test_keymap_presets.py`.

The pure half covers:

- each preset as a whole table;
- the orthodox table landing, with no selection gate;
- letters freed from the file list but not from a viewer;
- `config.py` overriding every preset, even with a value equal to AFX's,
  and under an old action name;
- `replaced`;
- switching back and forth without compounding;
- no key clashes, `is_typing_key`, `resolve`;
- the shipped `KEY_BINDINGS` being empty.

The app half covers:

- switching relabeling the keymap;
- a typed letter opening search with it, and no type-ahead under AFX;
- the choice surviving a restart, and `KEY_PRESET` winning over the menu;
- the first launch: nothing chosen → asked with no Cancel, quit unanswered → asked again;
- the log line on switching with overriding entries.

It isolates itself from the developer's `~/.xefm/config.py` by emptying the
shared config's `_KEY_BINDINGS_BASE`. Tests elsewhere that want "the shipped
keymap" read `keymap_afx.bindings()`, not `_config.Config.KEY_BINDINGS`.
