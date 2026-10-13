# Keymap Presets — Implementation

[#565](https://github.com/crftwr/xefm/issues/565), from discussion
[#343](https://github.com/crftwr/xefm/discussions/343). User-facing behavior is
in [`doc/KEYMAP_PRESETS_FEATURE.md`](../KEYMAP_PRESETS_FEATURE.md).

## Shape

`xefm/keymap_presets.py` holds `Preset` (name, label, `bindings`,
`free_letters`, `type_ahead`) and the `PRESETS` table: `afx` (None) and
`orthodox`. Discussion #343 asked for one mechanism with several presets on
it, not a special-cased beginner mode, and that is the reason for this shape.

The shipped preset is named for its lineage, like `orthodox`. That lineage is
the single-key Japanese filers: the X68000 file managers, then AFX (あふ), then
cfiler. The name says what the layout is, not that it is the default.
`DEFAULT = AFX` keeps the code's notion of "the one that ships". The preset
follows the style of those filers, not their exact keys.
`ALIASES = {"default": "afx"}` and `canonical()` keep the first name working,
both in `KEY_PRESET` and in a View-menu choice saved under it.
`set_keymap_preset` compares canonical names, so `KEY_PRESET = 'default'`
does not block choosing AFX style from the menu.
A per-platform Explorer/Finder preset is one more entry.

## `apply(config, name)`

The preset is written **into `config.KEY_BINDINGS`**. The keymap is built from
that table in several places: the app's `self.keys`, the shared
`config_manager.get_key_bindings()` that help and the menus resolve through,
and `DirectoryDiffView`'s own `KeyBindings`. Rewriting the one table they all
read is what makes a preset reach every surface without touching any of them.

1. The table the config was loaded with is stashed on the config as
   `_KEY_BINDINGS_BASE` the first time, so switching presets back and forth
   starts from it each time instead of compounding.
2. **Untouched** means `base[action] == template[action]`, where the template
   is `xefm._config.Config.KEY_BINDINGS`, or the action is missing from the
   user's table. A user's `config.py` holds a full copy of the template's
   table, so equality with the shipped value is the only way to tell a key
   left alone from a key chosen. A rebound action keeps the user's keys,
   letters included.
3. `free_letters` removes **typing keys** (`is_typing_key`: a bare letter or
   digit, or `Shift-<letter>`) from untouched actions of the `filer` and
   `common` contexts. A viewer's own actions keep their letters, because
   nothing is typed into a viewer.
4. `bindings` replaces untouched actions' keys with a plain list. That drops
   any `selection` gate: the template's `copy_files` is `{'keys': ['C'],
   'selection': 'required'}`, and an orthodox `F5` copies the cursor item when
   nothing is marked, which `_transfer` already does.
5. `config._KEY_TYPE_AHEAD` records the flag.

`test_no_two_actions_share_a_key_in_the_file_list` keeps the orthodox table
free of clashes. The ones it had to resolve: `F5` was `redraw` (now unbound),
`+` was `diff_directories` (now `Shift-F2`), `-` was `reset_pane_boundary`
(now unbound), and `Home`/`End` were select all / unselect all (now `Ctrl-A` /
unbound).

## Choosing

`resolve(config, chosen)`: `KEY_PRESET` from the config when set, else the
View menu's choice (state key `keymap.preset`), else `afx`, with old names
mapped through `canonical`. An unknown name falls back to `afx` and is
logged.

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

`quick=True` gives the classic quick search, the way Total Commander's
behaves:

- **Start-of-name matching.** `search_match.compile_query(anchored=True)`
  drops the leading `*` from the first token's glob and anchors its Migemo
  regex with `\A`. Later tokens still match anywhere.
  `QUICK_SEARCH_MATCH = 'anywhere'` turns the anchoring off. The setting is
  read through `_isearch_anchored` when the search opens.
- **The bar is built in quick-search mode.** It has no select, select-all or
  accept callbacks, and its prompt is "Quick search:".
  - `on_cancel` is `_isearch_stop`, so Esc keeps the match instead of
    restoring the origin.
  - `on_passthrough` is `_isearch_passthrough`. `ISearchBar.handle_event`
    hands it any KEY that is not typing, not one of the bar's remaining
    actions (prev/next match, cancel), and not Backspace/Delete
    (`_EDIT_KEYS`).
  - `_isearch_passthrough` closes the search and feeds the event to `on_event`,
    so Enter reaches `open_item` and F5 reaches `copy_files` on the match.
- **The status bar** shows `_quick_hints` (prev/next, close, "other keys act on
  the file") instead of the I-Search hint line.

The I-Search key (`enter_isearch()` with no argument) is unchanged.

## Not done

The Explorer/Finder preset, a first-run prompt, and presets as data packages
(#543).

## Tests

`test/test_keymap_presets.py`. The pure half covers the orthodox table
landing, no selection gate, letters freed from the file list but not from a
viewer, rebound actions kept, switching back and forth without compounding,
no key clashes, `is_typing_key`, and `resolve`. The app half covers switching
relabeling the keymap, a typed letter opening search with it, no type-ahead
under the default keymap, the choice surviving a restart, and `KEY_PRESET`
winning over the menu.
