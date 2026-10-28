# Delete to the Trash — Implementation

Issue #591, part 2 of discussion #468 (part 1 is background jobs, #567). The
user chose to write it in-house rather than depend on Send2Trash.

## `xefm/trash.py`

- `available(path)` is cheap:
  - local paths only;
  - macOS: Foundation importable;
  - Windows: `GetDriveTypeW(root) == DRIVE_FIXED`, with UNC paths refused;
  - any other POSIX system: yes.
- `send(path)` dispatches on `sys.platform` and raises `OSError` with the
  reason.
- `NAME` is "Trash", or "Recycle Bin" on Windows, for messages and menu
  labels.

Per platform:

- **macOS:** `NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_`.
  This is Finder's call, so Put Back works. PyObjC is a dependency of PuiKit on
  darwin, so it is present in terminal installs too.
  - A File Provider placeholder (`st_flags & SF_DATALESS`, an online-only file
    in cloud storage) may be refused (#765). OneDrive refuses it, with
    `NSCocoaErrorDomain` 3328 or 513 and no underlying error; Finder then
    offers a permanent delete. When the call fails and the item is dataless,
    `send` raises `NoTrashError` (an `OSError`) with the provider-neutral
    `ONLINE_ONLY` reason.
  - Dataless is decided after the attempt, not in `available`: whether a
    dataless item can be trashed is each provider's choice, and only OneDrive
    has been tried.
  - Not done: downloading the item to trash it (`rename(2)` and reading it
    first both work, as does AppleScript `Finder delete`). The Finder UI does
    not do this either, and the reported file was 122 MB.
- **Windows:** `SHFileOperationW(FO_DELETE)` with `FOF_ALLOWUNDO |
  FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING`. One
  path per call, so each failure is attributed to its file.
  - The call is limited to fixed drives because, on removable and network
    drives, `FOF_ALLOWUNDO` silently deletes permanently.
  - `FOF_WANTNUKEWARNING` makes the shell warn if it would do that anyway.
- **freedesktop** (the Trash specification), in `_trash_freedesktop`:
  - The home trash, `$XDG_DATA_HOME/Trash`, is used when it is on the file's
    device.
  - Otherwise the trash is at `_mount_point` (found by walking up while
    `st_dev` stays the same): `$top/.Trash/$uid` when `$top/.Trash` is a
    non-symlink directory with the sticky bit, else `$top/.Trash-$uid`.
    Directories are created 0700.
  - The info file is created with `O_EXCL` before the rename, so two XeFM
    processes cannot claim one name. A name collision becomes `stem.N.ext`.
  - `Path=` is percent-encoded. It is absolute for the home trash and relative
    to `$top` for a top-directory trash.
  - A failed rename removes its info file.
  - The optional `directorysizes` cache is not written.

## The operation

`FileOperationService.trash` adds a `trash` kind to the existing pipeline.

- The confirmation is `CONFIRM_TRASH`, with *Move to Trash* as the default
  button.
- Each target is one plan entry, counted as one item without walking its
  subtree, with no byte bar.
- `_execute_one` calls `trash.send`. A failure is recorded per target with the
  OS reason. A `NoTrashError` target is also added to `result["no_trash"]`.
- The kind takes part in `_mutated_dirs` (watcher suppression) and in
  `_release_archives`, so an archive XeFM holds open is closed before it is
  trashed (#516).

`FileOperationService.delete` gains `note`, an extra line for the confirmation.

## The app

- `delete_files` (K/Delete) calls `_delete(permanent=not DELETE_TO_TRASH)`.
- `delete_permanently` (Shift-K/Shift-Delete) calls `_delete(permanent=True)`.
- `_delete` trashes only when every target is `available`. Otherwise it runs
  the permanent delete, with the note saying there is no trash, when K asked
  for the trash.
- When the trash task returns `no_trash` targets, `_delete` leaves them out of
  the failure box and runs the permanent delete on just those, with a note
  saying why (the confirmation still honours `CONFIRM_DELETE`).
- Menus: File ▸ Move to Trash… and Delete Permanently…, and the same pair in
  the row's context menu.

## Tests

- `test/conftest.py::no_real_trash` replaces `_trash_macos` and
  `_trash_windows` for every test. A test that reaches the user's real Trash
  fails instead of leaving files in it.
- `test/test_trash.py`:
  - the freedesktop implementation for real, under a temporary
    `XDG_DATA_HOME`: info contents, name collisions, dotfiles, directories,
    percent-encoding, cleanup when the rename fails, the top-directory trash
    on another (simulated) device;
  - macOS against a stand-in NSFileManager;
  - availability for remote and archive paths;
  - the app's K / Shift-K / `DELETE_TO_TRASH` choice;
  - the engine's per-target errors and its `no_trash` list;
  - a dataless refusal becoming `NoTrashError`, and K's follow-up delete.

During development one scratch file was trashed for real on macOS, to confirm
the call works from this process.

## Not done (discussion #468 §3)

- Restoring from the trash and undoing the last operation belong to the
  operation journal.
- On Linux, the `directorysizes` cache.

## Hand checks owed

- Windows: the Recycle Bin on a fixed drive, the refusal on USB, network and
  UNC paths, and the nuke warning.
- macOS: a folder that contains online-only files (whether the provider
  refuses it, and what Finder does), and providers other than OneDrive.
- Linux: GNOME Files or Dolphin restoring an item XeFM trashed, and a second
  drive's `.Trash-$uid`.
