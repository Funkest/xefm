# Keymap Presets

By default, XeFM runs commands from single letters: `C` copies, `M` moves,
`K` deletes. That is fast once you know it. If you want typing a letter to be
harmless, or you are used to the function-key layout of two-pane file
managers, switch to a **preset**.

**View → Keymap** picks one:

| Preset | Bare letters | Commands are on |
|--------|--------------|-----------------|
| **Default** | run commands | letters (`C`, `M`, `K`, `V`, …) |
| **Orthodox** | search for a file | function keys (`F3`, `F5`, `F8`, …) |

The change applies at once. The help dialog (`F1`), the menus and the status
bar show the new keys, and XeFM remembers your choice for later sessions.

## Orthodox

The layout shared by the classic two-pane file managers. Typing a letter or
digit starts [incremental search](XEFM_USER_GUIDE.md) with that character, so
`r` `e` `p` jumps to `report.txt`. No letter runs a command.

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
KEY_PRESET = 'orthodox'   # or 'default'
```

A `KEY_PRESET` in `config.py` overrides the menu, and the menu says so if you
try to change it there. Leave it as `None` to let the menu decide.

## See also

- [Key Bindings](KEY_BINDINGS_FEATURE.md): changing individual keys
- [Command Palette](COMMAND_PALETTE_FEATURE.md): finding any command and its key
