# Tree Files (.xft)

An `.xft` file holds **groups of references to files**: for example, the
groups of similar videos a scan found. Each group lists files that may live
in many different folders, on this computer or a server. Press `Enter` on a
`.xft` file to browse it like an archive.

```
scan.xft/
  trip.mp4 (2)/            ← a group
    trip.mp4               ← stands for /Users/me/Movies/trip.mp4
    trip-small.mp4         ← stands for /Volumes/NAS/trip-small.mp4
    trip (copy).mp4
  logo.png (1)/
    …
```

You don't write these files yourself. Programs write them: XeFM's
[Find Similar Files](FIND_SIMILAR_FILES_FEATURE.md) does, through
similar-files. Earlier versions named these files `.xefml`; XeFM still opens
those. The format is described in [XFT_FORMAT.md](XFT_FORMAT.md)
for anyone writing such a program.

## Browsing

- `Enter` on the file goes in. `Enter` on a group opens it. `Backspace` goes
  back up, and from the top it returns to the folder, with the cursor on the
  file.
- Each entry shows the size and date **recorded in the file**, so a group of
  files on a slow server lists instantly.
- `V` views an entry, `=` compares two, and copying to the other pane works,
  all reading the real file.
- `Enter` on an entry that stands for a folder goes to that folder.

## Acting on the real files

Entries in the tree are references. They can't be deleted or renamed there,
because the tree is a record of what was found. To work on the real files:

- **`Shift-O`** opens the real location of the entry under the cursor in the
  other pane, with the cursor on the file. The tree stays where it is.
- **Select several entries (or whole groups) and press `Shift-O`**. The other
  pane shows all their real files as one list, wherever they live. Delete,
  move or compare them there. This is the quick way to clean up duplicates
  spread over many folders.
- `O` from the other pane goes to the real location of the entry highlighted
  in the tree.
- Whatever leaves XeFM gets the **real file**: opening an entry in its
  application (`Cmd-Enter` on macOS, `Ctrl-O`), revealing it in Finder or
  Explorer, editing it (`E`), and copying its path.

## Trees that are still being written

A long scan rewrites its tree file every few minutes, so you can start
looking before it finishes. While it is still running:

- the pane header says **"scanning 42% — groups may change"**;
- the pane updates by itself when the file is rewritten;
- a group may gain or lose files, or change its name. XeFM keeps you in the
  same group when it can, and returns to the top of the tree (saying so in
  the log) when the group is gone;
- `Shift-O` on a selection asks before opening the files, because the groups
  you selected may still change.

Groups of identical files are final as soon as they appear. Only similar-file
groups can change.

## See also

- [Find Similar Files](FIND_SIMILAR_FILES_FEATURE.md)
- [File lists](FILE_LIST_IMPORT_FEATURE.md): flat lists of paths (`.m3u8`,
  `.lst`)
