# Deleting to the Trash

`K` (or `Delete`) moves files to your system's **Trash**, called the Recycle
Bin on Windows, so a mistaken delete can be undone. Restore them from Finder
(*Put Back*), the Recycle Bin, or your desktop's Trash, the same way as files
deleted anywhere else.

| Key | What it does |
|---|---|
| `K`, `Delete` | Move the selection (or the item under the cursor) to the Trash |
| `Shift-K`, `Shift-Delete` | Delete for good, without the Trash |

Both ask first. The Trash confirmation's default button is *Move to Trash*,
because the move can be undone. The permanent delete's default is *Cancel*.
The **File** menu and the right-click menu have both commands.

## Where there is no Trash

Some places have no Trash:

- files on SSH or S3;
- files inside archives;
- on Windows, USB and network drives, where Windows itself would delete for
  good.

There, `K` deletes for good, and its confirmation says *There is no Trash here,
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
DELETE_TO_TRASH = True   # False: K deletes for good, like Shift-K
```
