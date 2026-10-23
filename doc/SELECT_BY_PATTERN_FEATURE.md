# Select by Pattern

English \| [日本語](SELECT_BY_PATTERN_FEATURE.ja.md)

Three ways to select many files at once without filtering the pane first.

| Action | Menu | What it does |
|--------|------|--------------|
| `select_by_pattern` | Select → Select by Pattern… | Asks for a pattern and adds every matching file to the selection |
| `unselect_by_pattern` | Select → Unselect by Pattern… | Asks for a pattern and removes every matching file from the selection |
| `select_same_extension` | Select → Select Same Extension | Adds every file with the same extension as the one under the cursor |

Keys depend on your keymap preset — see [Keymap Presets](KEYMAP_PRESETS_FEATURE.md#every-key-side-by-side).
All three are also in the command palette (**Tools → Command Palette…**).
Most presets give `select_same_extension` no key; see [Keys](#keys).

## Patterns

A pattern is written exactly as for **Filter** (**View → Filter…**):

- A wildcard pattern: `*.jpg`, `report_202?.*`, `[ab]*`.
- Several at once, separated by spaces (or `;`): `*.jpg *.png *.gif`. A file
  matching any one of them counts.
- A pattern with a space in it, in quotes: `"my file*"`.
- The name of a filter defined in `FILTERS` in `config.py` — `images`, say, or
  `big` for a filter that picks files by size. See
  [Customization](CUSTOMIZATION_FEATURE.md).

Case does not matter: `*.jpg` also picks `IMG_0001.JPG`. A pattern that would
show some files under **Filter** selects those same files here — including on a
search-results pane, where a file's name is its path below the search root, so
`sub/*` selects the hits under `sub`.

The prompt lists your defined filters and the patterns you used before. That
history is shared with **Filter**: a pattern typed in either is offered in both.

## What gets selected

- Only files. Directories are never selected or unselected by a pattern, even
  one like `*` that their names match — use `toggle_select_items` for those.
- **Select** only adds and **Unselect** only removes. Everything else keeps the
  selection it had, so several patterns in a row add up: select `*.jpg`, then
  `*.png`, then unselect `thumb_*`.
- The log says how many files changed, or that nothing matched.

## Select same extension

Put the cursor on a file and run `select_same_extension`: every file in the pane
with the same extension is selected, whatever its case — on `photo.JPG` it picks
every `.jpg` and `.JPG`. On a file with no extension (`README`, `.bashrc`) it
selects the other files without one. On a directory it does nothing.

## Keys

Each preset puts these actions on its own keys; the
[Keymap Presets](KEYMAP_PRESETS_FEATURE.md#every-key-side-by-side) page lists
them. A key that is a character, such as `'` or `"`, works the same in the
desktop app and in any terminal, whatever the keyboard layout: press whichever
key types it (on a Japanese keyboard, `Shift-7` for `'` and `Shift-2` for `"`).

To change the keys, or give `select_same_extension` one, set them in
`config.py`:

```python
KEY_BINDINGS = {
    'select_by_pattern': ["'"],
    'unselect_by_pattern': ['"'],
    'select_same_extension': ['Y'],
}
```

See [Key Bindings](KEY_BINDINGS_FEATURE.md) for the key names.
