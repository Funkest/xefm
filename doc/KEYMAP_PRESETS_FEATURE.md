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
command. Typing a letter or digit opens [incremental search](XEFM_USER_GUIDE.md)
with that character, so `r` `e` `p` jumps to `report.txt`. It closes the way
those file managers' quick search does:

- `↑` / `↓` jump to the previous / next match, and `Backspace` removes a
  letter.
- `Esc` closes the search and leaves the cursor on the match.
- **Any other key closes the search and does its usual job.** `Enter` opens
  the match, `F5` copies it, `F3` views it, and so on, with no extra key press
  to leave the search first.
- There is no timeout. The search stays open until you press a key that
  closes it.

Matching is the same as for any incremental search. What you type can appear
anywhere in the name, and romaji finds Japanese names. When you open the
search with the I-Search key, it keeps its own keys under every preset: it
lets you mark matches as you go, and stays open until Enter or Esc.

The keys follow Total Commander's defaults, wherever XeFM has the same
command.

| Key | Action |
|-----|--------|
| `F1` | Help |
| `F2` / `Ctrl-R` | Re-read both panes |
| `F3` | View |
| `F4` | Edit |
| `Shift-F4` | New file |
| `F5` | Copy to the other pane |
| `Shift-F5` | Duplicate in place |
| `F6` | Move to the other pane |
| `Shift-F6` / `Ctrl-M` | Rename (batch rename for several) |
| `F7` | New folder |
| `F8` / `Del` | Delete (to the Trash where there is one) |
| `Shift-F8` / `Shift-Del` | Delete for good |
| `F9` / `F10` / `Alt` | Menu |
| `Alt-F4` | Quit |
| `Shift-F10` | Context menu |
| `Alt-Enter` | Details (properties) |
| `Alt-F1` / `Alt-F2` | Drives |
| `Alt-F5` | Create archive |
| `Alt-F6` / `Alt-F9` | Extract |
| `Alt-F7` | Search files |
| `Shift-F2` | Compare with the other pane and select the differences |
| `Ctrl-F3` … `Ctrl-F6` | Sort by name / extension / date / size |
| `Enter` / `Ctrl-PgDn` | Open |
| `Backspace` / `Ctrl-PgUp` | Parent directory |
| `Ctrl-\` | Root |
| `Alt-←` / `Alt-→` / `Alt-↓` | Back / forward / history |
| `Ctrl-D` | Favorites (directory hotlist) |
| `Ctrl-F` / `Ctrl-N` | Connect to a server |
| `Ctrl-S` / `Ctrl-F10` | Filter / show all files |
| `Ctrl-B` | Flat view |
| `Ctrl-Q` | Quick view |
| `Ctrl-T` / `Ctrl-↑` / `Ctrl-W` | New tab / open folder in a new tab / close tab |
| `Ctrl-Tab` / `Ctrl-Shift-Tab` | Next / previous tab |
| `Ctrl-C` / `Ctrl-X` / `Ctrl-V` | Copy / cut / paste files |
| `Ctrl-P` | Copy the path |
| `Insert` / `Space` | Mark and move down |
| `+` / `-` | Select / unselect by pattern |
| `*` | Invert the file selection |
| `Ctrl-A` / `Ctrl--` | Select all / unselect all |
| `Alt-+` | Select files with the same extension |
| `Home` / `End` | First / last item |
| `Ctrl-Shift-P` | Command palette |

A few of these keys belong to features that may not be in your version of
XeFM yet: tabs, quick view, flat view, back and forward, and the file
clipboard. A key whose command doesn't exist does nothing.

`F5`, `F6` and `F8` act on the marked items, or on the item under the cursor
when nothing is marked.

These commands have no key in this preset, because Total Commander has no key
for them:

- the sort dialog, compare directories in the diff viewer
- go to / send to the other pane's directory, jump to path, add to favorites
- copy / move to a typed directory, the subshell, external programs
- copy names, reveal in Finder / Explorer, the OS index search
- incremental search's own key (typing a letter already starts one)

All of them are in the command palette (`Ctrl-Shift-P`), and most are in the
menus too. To put one back on a key, bind it in `KEY_BINDINGS`.

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
