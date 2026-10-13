# Find Similar Files

**Tools → Find Similar Files…** looks through a folder for files you probably
don't need twice:

| Method | Finds | Needs |
|--------|-------|-------|
| **Identical files** | the same content under different names or in different folders | nothing more |
| **Similar videos** | the same video re-encoded or resized, and clips cut from a longer video | [ffmpeg](https://ffmpeg.org) on your `PATH` |

The detection is done by [similar-files](https://github.com/crftwr/similar-files),
which XeFM runs for you. A method that is missing something shows in the menu
what to install.

## Running a scan

1. Go to the folder to scan, or select the folders and files to scan.
2. Choose **Tools → Find Similar Files…** and pick a method.

The scan starts at once and **runs as a program of its own**. A video scan can
take hours. You can keep using XeFM, or quit it: the scan carries on, and the
next time XeFM starts it tells you what finished while it was closed.

The status bar's right end shows how it is going:

```
⟳ Similar videos extract 42% (Ctrl-G)
```

and says when it is done:

```
✓ Similar videos: 12 groups (Ctrl-G)
```

## Looking at the results

Open **View → Background Jobs…** (`Ctrl-G`) and choose the scan. The pane
goes to its results: **one playlist per group**, with the file the others were
compared with on the first line.

- `Enter` on a group shows its files as a list. Copy, move, delete, view and
  compare work there as anywhere else.
- `Backspace` goes back to the groups.
- Select several groups and press `Enter` to see them all as one list.

Nothing is ever deleted for you. Deciding which copy to keep is up to you.

## Stopping a scan

Choose a running scan in the jobs list, then **Stop the scan**. It stops within
a second or so, and the groups it had found are kept.

Stopping, putting the computer to sleep or restarting it doesn't waste the
work done. similar-files remembers what it has already read, so running the
same scan again picks up quickly.

## Things to know

- **Local folders only.** A mounted network share counts as local. Folders on
  `ssh://` or `s3://` can't be scanned from here yet.
- **Results are kept in `~/.xefm/scans/`**, one folder per scan, with the
  scan's log. Nothing is written beside your files. The ten most recent
  finished scans are kept.
- If a scan ends without finishing (its process was killed, for example), the
  jobs list says so, and choosing it shows its log.
- **similar-files must be installed** in the same Python as XeFM:
  `pip install 'similar-files>=0.2'`. The desktop apps don't include it yet,
  so there the menu item says it is missing.

## See also

- [File lists](FILE_LIST_IMPORT_FEATURE.md): how a playlist opens as a list
- [Background Jobs](BACKGROUND_JOBS_FEATURE.md): the jobs list
