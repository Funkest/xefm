# Deleting to the Trash

English \| [日本語](TRASH_FEATURE.ja.md)

**File → Move to Trash…** (`delete_files`, also on `Delete`) moves files to
your system's **Trash**, called the Recycle Bin on Windows, so a mistaken delete can be undone. Restore them from Finder
(*Put Back*), the Recycle Bin, or your desktop's Trash, the same way as files
deleted anywhere else.

| Action | Menu | What it does |
|---|---|---|
| `delete_files` | **File → Move to Trash…** (**Move to Recycle Bin…** on Windows) | Move the selection (or the item under the cursor) to the Trash |
| `delete_permanently` | **File → Delete Permanently…** | Delete for good, without the Trash |

`Delete` and `Shift-Delete` run these two under every preset; their other keys
depend on your keymap preset — see [Keymap Presets](KEYMAP_PRESETS_FEATURE.md#every-key-side-by-side).
The menu commands, and the keys of every preset but AFX style, act on the item
under the cursor when nothing is marked. AFX style binds its keys, `Delete` and
`Shift-Delete` included, to marked items only: with nothing marked they do
nothing, so mark the item first or use the menu.

Both ask first. The Trash confirmation's default button is *Move to Trash*,
because the move can be undone. The permanent delete's default is *Cancel*.
The **File** menu and the right-click menu have both commands.

## Where there is no Trash

Some places have no Trash:

- files on SSH or S3;
- files inside archives;
- on Windows, USB and network drives, where Windows itself would delete for
  good.

There, `delete_files` deletes for good, and its confirmation says *There is no Trash here,
so these are deleted for good* before anything happens.

## Which Trash

| System | Where deleted files go |
|---|---|
| macOS | The Trash, as from Finder. Each drive keeps its own, and *Put Back* knows where they came from. |
| Windows | The Recycle Bin, on fixed (internal) drives |
| Linux and other Unix desktops | The desktop Trash (`~/.local/share/Trash`, or a `.Trash` folder at the top of another drive), which GNOME Files, Dolphin and `gio trash` all read |

A folder goes to the Trash whole, as one item.

## Settings

```python
CONFIRM_TRASH = True     # ask before moving to the Trash
CONFIRM_DELETE = True    # ask before deleting for good
DELETE_TO_TRASH = True   # False: delete_files deletes for good, like delete_permanently
```
