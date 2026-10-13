# Searching the OS Index

Your operating system already keeps an index of your files, their names, their
contents, and much more about them: **Spotlight** on macOS, **Windows
Search** on Windows. XeFM can search that index and show what it finds as a
list you can sort, filter, copy, move and delete in.

| Action | Key | Menu |
|--------|-----|------|
| `index_search` | `Ctrl-F` | View → Search Spotlight… (macOS) / Search Windows Search… (Windows) |

It searches **the active pane's folder and everything below it**. To search
your whole home folder, run it from there.

This is for macOS and Windows. On Linux, use
[Open List from Command](FILE_LIST_IMPORT_FEATURE.md) with your indexer's own
tool (`plocate`, `baloosearch`, `recollq`).

## Writing a query

The query is written the way that OS's own search reads it.

**On macOS (Spotlight)**, as in Spotlight's search field:

| Query | Finds |
|-------|-------|
| `budget 2026` | files whose name or contents have both words |
| `name:report` | files with "report" in their name |
| `kind:pdf` | PDF documents (also `kind:image`, `kind:movie`, `kind:folder`, …) |
| `kMDItemPixelWidth > 4000` | images wider than 4000 pixels |
| `kMDItemDurationSeconds > 600` | audio and video longer than ten minutes |
| `kMDItemWhereFroms == "*example.com*"` | files downloaded from a site |
| `kMDItemLastUsedDate > $time.today(-7)` | files you opened in the last week |

**On Windows (Windows Search)**:

| Query | Finds |
|-------|-------|
| `budget 2026` | files whose name or contents contain both words |
| `where System.Size > 100000000` | a raw Windows Search SQL condition — here, files over 100 MB |
| `where System.Kind = 'picture'` | pictures |

Queries you have run before are offered again, most recent first. Type to
narrow the list, `↓` to pick one, `Shift-Delete` to forget one.

## The results

The matches open in the active pane as a list, titled with the query. Every
list feature works there: sort by date or size, filter, select, copy, move,
view, and `Shift-O` to reveal a file where it really lives. `Backspace`
returns to the folder.

While the index is being asked, a progress dialog counts the matches, and
`Esc` stops the search.

## Finder saved searches

A Finder **Smart Folder** is a `.savedSearch` file, usually in
`~/Library/Saved Searches`. Press `Enter` on one in XeFM and it runs its
query in the folders it was saved with, showing the matches as a list named
after it. Searches you built in Finder become one-key lists here.

## Things to know

- **The index decides what can be found.** Spotlight skips folders listed
  under System Settings → Spotlight → Search Privacy. Windows Search by
  default covers your user folders and libraries, not whole drives, and the
  service can be turned off. A file outside the index won't be found. For
  that, use **Search Files** (`Shift-F`), which walks the folder itself.
- **Local folders only.** A mounted network share is searched only if the
  OS indexes it. `ssh://` and `s3://` folders are refused.
- **Windows** needs `comtypes` (installed with XeFM). If it is missing, the
  action says how to install it.
