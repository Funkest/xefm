# Keymap Presets

By default, XeFM runs commands from single letters: `C` copies, `M` moves,
`K` deletes. That is fast once you know it. If you want typing a letter to be
harmless, or you are used to the function-key layout of two-pane file
managers, switch to a **preset**.

**View → Keymap** picks one:

| Preset | Bare letters | Commands are on |
|--------|--------------|-----------------|
| **AFX style** (the default) | run commands | letters (`C`, `M`, `K`, `V`, …) |
| **Orthodox** | search for a file | function keys (`F3`, `F5`, `F8`, …) |

The change applies at once. The help dialog (`F1`), the menus and the status
bar show the new keys, and XeFM remembers your choice for later sessions.

## AFX style

XeFM's own layout, and the one it starts with. One letter runs one command,
which is the style of the Japanese single-key filers: the X68000 file managers,
then AFX (あふ) on Windows, then cfiler. XeFM follows that style rather than
copying any one of them key for key, so details differ from AFX. Deleting, for
example, is `K`.

## Orthodox

The layout shared by the classic two-pane file managers. No letter runs a
command. Typing a letter or digit opens **quick search** with that character,
as in those file managers:

- The search box replaces the pane's footer, and shows what you typed and how
  many files match.
- Matching works like this:
  - The name must **start with** what you typed, so `r` `e` `p` jumps to
    `report.txt`.
  - Words after a space can match anywhere in the name, so `rep 24` finds
    `report-2024.pdf`.
  - A letter that would match nothing is not added.
- `↑` / `↓` jump to the previous / next match. `Backspace` removes a letter.
- `Esc` closes the search and leaves the cursor on the match.
- **Any other key closes the search and does its usual job.** `Enter` opens
  the match, `F5` copies it, `F3` views it, and so on, with no extra key press
  to leave the search first.
- There is no timeout. The search stays open until you press a key that
  closes it.

To match anywhere in the name instead of from its start, set
`QUICK_SEARCH_MATCH = 'anywhere'` in `config.py`. The I-Search key keeps its
own behavior under every preset. It matches anywhere, lets you mark matches as
you go, and stays open until Enter or Esc.

| Key | Action |
|-----|--------|
| `F1` | Help |
| `F2` | External programs |
| `F3` | View |
| `F4` | Edit |
| `F5` | Copy to the other pane |
| `Shift-F5` | Copy to a typed directory |
| `F6` | Move to the other pane |
| `Shift-F6` | Rename |
| `Shift-F4` | New file |
| `F7` | New folder |
| `F8` / `Del` | Delete |
| `F9` / `Alt` | Menu |
| `F10` | Quit |
| `Alt-F1` | Drives |
| `Alt-F5` / `Alt-F9` | Create archive / extract |
| `Alt-F7` | Search files |
| `Alt-Shift-F7` | Search file contents |
| `Alt-↓` | History |
| `Ctrl-D` | Favorites |
| `Insert` / `Space` | Mark and move down |
| `+` / `-` | Select / unselect by pattern |
| `Ctrl-A` | Select all |
| `Home` / `End` | First / last item |
| `Ctrl-F3` … `Ctrl-F6` | Sort by name / extension / date / size |
| `Shift-F2` | Compare directories |

`F5`, `F6` and `F8` act on the marked items, or on the item under the cursor
when nothing is marked.

These commands have no key in this preset:

- the sort dialog, file details, compare and select
- go to / send to the other pane's directory
- jump to path, connect to server, add to favorites
- move to a typed directory, the subshell
- toggle-select all files / all items, unselect all
- incremental search's own key (typing a letter already starts one)
- redraw, reset the pane split

All of them are in the command palette (`Ctrl-T`), and most are in the menus
too. To put one back on a key, bind it in `KEY_BINDINGS`.

Function keys and modified function keys have terminal sequences, so the
layout works in a terminal as well as in the desktop app. A terminal may still
keep some of them. On macOS, Terminal.app sends `Alt-<key>` only with **Use
Option as Meta key** turned on, and a laptop keyboard may need `fn` for the
function keys. If one does nothing, rebind it.

## Your own key bindings come first

A preset replaces only the keys you have **not** changed. If your
`config.py` rebinds `copy_files`, that binding stays the same under every
preset, letters included. To change a key in a preset, rebind it in
`KEY_BINDINGS` as usual.

## Choosing it in config.py

```python
KEY_PRESET = 'orthodox'   # or 'afx'
```

`'default'`, the name this preset had first, still works and means `'afx'`.

A `KEY_PRESET` in `config.py` overrides the menu, and the menu says so if you
try to change it there. Leave it as `None` to let the menu decide.

## See also

- [Key Bindings](KEY_BINDINGS_FEATURE.md): changing individual keys
- [Command Palette](COMMAND_PALETTE_FEATURE.md): finding any command and its key
