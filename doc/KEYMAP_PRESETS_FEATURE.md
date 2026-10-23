# Keymap Presets

XeFM has four complete keymaps, called **presets**. None is the default:
the first time XeFM starts, it asks which one you want.

| Preset | Bare letters | Commands are on |
|--------|--------------|-----------------|
| **AFX style** | run commands | letters (`C`, `M`, `K`, `V`, …) |
| **Orthodox** | search for a file | function keys (`F3`, `F5`, `F8`, …) |
| **OS native** | search for a file | Finder's or Explorer's keys (`Cmd`/`Ctrl`-`C`, `F2`, `Delete`, …) |
| **Vim style** | run commands | Vim-style keys (`hjkl`, `gg`, `yy`, `dd`, `/`, …) |

**Tools → Advanced → Keymap** switches at any time. The change applies at once: the help
dialog (`F1`), the menus and the status bar show the new keys, and XeFM
remembers your choice for later sessions.

## The first launch

When no preset has been chosen yet, XeFM starts with a **Keymap** dialog
with one button per preset. That includes the first start after updating from
a version without presets. The dialog has no Cancel, and `Esc` does not close
it: choose one to go on. You can switch later from Tools → Advanced → Keymap.

If you are updating and want the keys you have been using, choose **AFX
style**. Your `config.py` may hold a full copy of the old keymap. See
[A config.py from an earlier XeFM](#a-configpy-from-an-earlier-xefm) before
choosing another preset.

## AFX style

One letter runs one command, which is the style of the Japanese single-key
filers: the X68000 file managers, then AFX (あふ) on Windows, then cfiler.
XeFM follows that style rather than copying any one of them key for key, so
details differ from AFX. Deleting, for example, is `K`.

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

## OS native

The keys Finder uses on macOS and Explorer uses on Windows. Use it if you
come to XeFM from those rather than from another file manager. As in
Orthodox, no letter runs a command: typing a letter searches, which is how
both Finder and Explorer select a file by name.

| Action | macOS app | Windows app | Terminal (any OS) |
|---|---|---|---|
| Copy / cut / paste files | `Cmd-C` / `Cmd-X` / `Cmd-V` | `Ctrl-C` / `Ctrl-X` / `Ctrl-V` | `Ctrl-C` / `Ctrl-X` / `Ctrl-V` |
| Open | `Enter`, `Cmd-↓` | `Enter` | `Enter` |
| Parent folder | `Cmd-↑`, `Backspace` | `Backspace`, `Alt-↑` | `Backspace`, `Alt-↑` |
| Back / forward | `Cmd-[` / `Cmd-]` | `Alt-←` / `Alt-→` | `Alt-←` / `Alt-→` |
| Rename | `F2` | `F2` | `F2` |
| Delete (to the Trash) | `Cmd-Backspace`, `Delete` | `Delete` | `Delete` |
| Delete for good | `Cmd-Opt-Backspace` | `Shift-Delete` | `Shift-Delete` |
| New folder | `Cmd-Shift-N` | `Ctrl-Shift-N` | `F7` |
| Select all | `Cmd-A` | `Ctrl-A` | `Ctrl-A` |
| Mark the item | `Ctrl-Space` | `Space` | `Space` |
| Quick view | `Space` | `Alt-P` | `Alt-P` |
| File details | `Cmd-I` | `Alt-Enter` | `Alt-I` |
| Find files | `Cmd-F` | `Ctrl-F` | `Ctrl-F` |
| Go to path | `Cmd-Shift-G` | `Ctrl-L`, `Alt-D` | `Ctrl-L`, `Alt-D` |
| Copy the path | `Cmd-Opt-C` | `Ctrl-Shift-C` | `Ctrl-P` |
| Show hidden files | `Cmd-Shift-.` | `.` | `.` |
| New tab / close tab | `Cmd-T` / `Cmd-W` | `Ctrl-T` / `Ctrl-W` | `Ctrl-T` / `Ctrl-W` |
| Command palette | `Cmd-Shift-P` | `Ctrl-Shift-P` | `Ctrl-K` |
| Quit from anywhere, asking only while a task runs | `Cmd-Q` | `Alt-F4` | — |
| Quit, always asking | `Ctrl-Q` | `Ctrl-Q` | `Ctrl-Q` |

The desktop columns also accept the terminal column's keys.

Finder and Explorer have nothing for the two-pane operations, so they use
the function keys every two-pane file manager uses: `F3` view, `F4` edit,
`F5` copy and `F6` move to the other pane, `F8` delete. On macOS, `Enter`
opens, as in every other preset, rather than renaming as in Finder.

**In a terminal.** The preset you choose applies to both the desktop app and
the terminal. A terminal cannot send `Command`, and cannot tell
`Ctrl-Shift-N` from `Ctrl-N`, so there the preset uses the stand-ins in the
last column. Everything else is the same.

## Vim style

Vim-style keys, as Vim-like file managers use them: `hjkl` to move, two-key
commands such as `gg`, `yy` and `dd`, and `/` to search. Letters
run commands, as in AFX style, and typing a letter never searches.

| Keys | Action |
|---|---|
| `j` / `k` | Down / up |
| `h` / `l` | Parent folder / open (enter a folder, view a file) |
| `gg` / `G` | First / last item |
| `Ctrl-F` / `Ctrl-B` | Page down / up |
| `Ctrl-D` / `Ctrl-U` | Half a screen down / up |
| `Tab`, `Space` | Switch pane |
| `Ctrl-O` | Back to the previous folder |
| `t` | Mark or unmark the item, without moving |
| `v` | Mark from the nearest marked item to the cursor |
| `Esc` | Clear the marks |
| `yy` | Copy the marked items (or the item) to the file clipboard |
| `x` | Cut them |
| `p` | Paste here |
| `dd` / `DD` | Delete to the Trash / delete for good |
| `cw` | Rename |
| `/`, then `n` / `N` | Search; next / previous match of the last search |
| `za` | Show or hide hidden files |
| `=` / `zr` | Filter / clear the filter |
| `e` / `w` | View the file / quick view in the other pane |
| `gx` | Open with the OS application |
| `gp` | Go to a path |
| `'` | Favorites |
| `s` / `S` | Shell / sort |
| `Ctrl-G` | File details |
| `Ctrl-L` | Reread both panes |
| `:` | Command palette |
| `ZZ` / `ZQ` | Quit (XeFM asks first) |
| `F3`–`F8` | View, edit, copy and move to the other pane, new folder, delete |

`F3`–`F8` follow the two-pane file managers' function keys. The text viewer moves the same way: `j` / `k` / `h` / `l`,
`gg` / `G`, `Ctrl-F` / `Ctrl-B` (and `Ctrl-D` / `Ctrl-U`, `Space`) by the page,
`/` to search, and `q` or `ZZ` to close it.

The two-key commands are [key sequences](KEY_BINDINGS_FEATURE.md#key-sequences).
While one is half typed, the status bar shows the first key (`g …`); `Esc`
drops it. None of the first keys runs anything on its own, so nothing waits
for `KEY_SEQUENCE_TIMEOUT`.

Where it differs from Vim and Vim-like file managers:

- `v` does not start a visual mode. It marks the range from the nearest
  marked item to the cursor, so mark the start with `t`, move, and press `v`.
- `dd` moves to the system Trash, and `p` pastes what `yy` copied or `x`
  cut. There is no `P` that moves what was yanked: cut with `x`, then `p`.
- `q` alone does nothing in the file list; `ZZ` quits. In the text viewer it
  closes the viewer.
- `/` is XeFM's incremental search, not a regular expression, and it does not
  mark its matches.

## Your own key bindings come on top

`KEY_BINDINGS` in `config.py` holds **your changes** to the preset. Every
entry replaces that action's keys, whichever preset is in force. An action
you don't list keeps the preset's keys. That is why the `KEY_BINDINGS` XeFM
writes into a new `config.py` holds only commented-out examples.

A key you bind is also taken off the action the preset had given it, so you
don't have to find that action and empty it as well. `'toggle_color_scheme':
['Shift-T']` is enough on its own; AFX's `Shift-T` (open in a new tab) stops
answering, and the help and the menus stop listing it there.

A key you bind for the file list only stays on a shared action elsewhere.
`'view_file': ['Q']` opens the file with `Q` in the file list, and `Q`
still closes a viewer. A key you bind with a selection requirement leaves
the opposite one alone: `{'keys': ['C'], 'selection': 'none'}` keeps `C`
copying marked files.

```python
KEY_BINDINGS = {
    'reload_config': ['F12'],   # F12 reloads the config, under every preset
    'quit': [],                 # nothing quits by key
}
```

### A config.py from an earlier XeFM

Before the presets, `config.py` held a copy of the whole AFX-style table.
Under AFX style that copy changes nothing. Under another preset, every entry
in it replaces the preset's keys, so `C` still copies instead of searching.
When you switch presets, the log says how many actions your `config.py`
replaces, and names the first few.

To use another preset, delete the entries you did not mean to change. If you
never changed a key, delete them all and leave `KEY_BINDINGS = {}`.

## Choosing it in config.py

```python
KEY_PRESET = 'orthodox'   # or 'afx', 'native', or 'vim'
```

`'default'`, the name this preset had first, still works and means `'afx'`.

A `KEY_PRESET` in `config.py` overrides the menu, and the menu says so if you
try to change it there. It also skips the first-launch question. Leave it as
`None` to let the dialog and the menu decide.

## See also

- [Key Bindings](KEY_BINDINGS_FEATURE.md): changing individual keys
- [Command Palette](COMMAND_PALETTE_FEATURE.md): finding any command and its key
