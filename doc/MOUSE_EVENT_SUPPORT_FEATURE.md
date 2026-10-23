# Mouse

English \| [日本語](MOUSE_EVENT_SUPPORT_FEATURE.ja.md)

XeFM is built to be fast from the keyboard, and the mouse works alongside it.
You can mark and open files, move them by dragging, scroll and jump around,
all with the mouse. Every mouse action also has a key.

## Where it works

| | Desktop app (macOS, Windows) | Terminal |
|---|---|---|
| Click, double-click, right-click, wheel | yes | yes, in terminals that report the mouse |
| Cmd/Ctrl-click, Shift-click | yes | Ctrl-click usually; Shift-click only where the terminal passes it on (see below) |
| Middle-click, back/forward buttons | yes | where the terminal reports them |
| Dragging files out to other apps | yes | no — the paths are copied to the clipboard instead |
| Dropping files in from other apps | yes | no |

Start the desktop app with `xefm --backend gui`. The terminal is the default.

## Clicking in a file list

XeFM keeps two things apart: the **cursor**, which is on one row, and
**marks**, which can be on any number of rows. Operations act on the marked
files, or on the cursor's file when nothing is marked. The mouse follows the
same model.

| Gesture | What it does |
|---|---|
| Click | Moves the cursor there and makes that pane active. Marks are left alone. |
| Cmd-click (macOS) / Ctrl-click | Moves the cursor and marks or unmarks that row. |
| Shift-click | Marks every row from the last row you clicked to this one, adding to what is marked. |
| Double-click | Opens the row, as Enter does: enters a folder or an archive, opens a file. |
| Middle-click on a folder | Opens that folder in the other pane. |
| Right-click | Opens the context menu for the row. Below the last row, opens the menu for the directory. |
| Click below the last row | Makes the pane active without moving the cursor. |

A plain click never clears your marks, because marks often take a while to
build up. To clear them, use **Select ▸ Unselect All** or the context menu.

On macOS, **Control-click** is the secondary click, as in every Mac app. It
opens the context menu, so use **Command**-click to mark.

**In the terminal**, Ctrl-click works in most terminals. Many terminals keep
Shift-click for their own text selection and don't pass it on. Where Shift-click
doesn't arrive, use Space and the context menu's Select / Deselect instead.

## Scrolling

- **Wheel or trackpad**: scrolls the pane under the pointer, whichever pane is
  active. The cursor doesn't move.
- **Scrollbar**: drag the thumb, or click above or below it to move a page.

## The bars around the list

- **The path above a pane** works as a set of links. Click a folder name in it
  to go to that folder, with the cursor on the folder you came from. This
  works inside archives and on SSH and S3 too, following the same steps up as
  Backspace.
- **The pane footer**: click the sort description to open the sort menu, or the
  filter to change it.
- **The key hints at the bottom of the window**: click one to run it. They list
  your own key bindings, so they always match your keymap.

## Back and forward

Each pane remembers the folders it has shown. Go back and forward through them
like in a browser:

| | Keys | Mouse |
|---|---|---|
| Back | `Alt-←` (and `Cmd-[` in the macOS app) | the back button |
| Forward | `Alt-→` (and `Cmd-]` in the macOS app) | the forward button |

This is different from Backspace, which goes to the parent folder, and from
**H**, which lists recently used folders. The same commands are in the **Go**
menu.

## Dragging files

### Out of XeFM

Press on a row and drag. If the row is marked, every marked file goes with
it; otherwise only that file does. Drop the files on Finder, Explorer, another
app, or the other XeFM pane. You can start a drag in a background XeFM window
without bringing it forward first.

Only local files can be dragged. Files on SSH or S3, or inside an archive,
have no file on disk to hand to another app.

### Into XeFM, and between panes

Drop files on a pane to put them in the pane's folder. Drop them on a folder
row to put them in that folder. What happens follows your system's usual
rules:

| | macOS | Windows |
|---|---|---|
| No key held | Move if the files are on the same drive, copy if not | same |
| Copy | hold **Option** | hold **Ctrl** |
| Move | hold **Command** | hold **Shift** |

While you drag, the cursor shows a copy or a move. A drop goes through the
usual copy or move, with its confirmation and its dialog for files that
already exist. A drop that asks for a link (an alias or shortcut) is refused.

## In the terminal

The terminal reports the mouse only while mouse reporting is on. XeFM turns it
on, but some setups need it allowed too. tmux, for example, needs
`set -g mouse on`. Where the terminal reports nothing, everything still works
from the keyboard.

## Keys for everything

| Mouse | Keys |
|---|---|
| Click a row | arrow keys |
| Cmd/Ctrl-click | Space (mark and move down) |
| Shift-click | Shift-Space, or Space while moving |
| Double-click | Enter |
| Click a folder in the path | Backspace (one level), J / H (favorites, history) |
| Back / forward buttons | Alt-← / Alt-→ |
| Scrollbar | Page Up / Page Down, Home / End |
| Drag between panes | `C` (copy) / `M` (move) |

## See also

- [Context Menus](CONTEXT_MENU_FEATURE.md)
- [Directory Diff Viewer](DIFF_VIEWER_FEATURE.md) — double-click works there too
- [Desktop Mode Guide](DESKTOP_MODE_GUIDE.md)
