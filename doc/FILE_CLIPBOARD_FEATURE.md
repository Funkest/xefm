# File Clipboard

Copy or cut files now, then paste them **wherever you go next**: a third
folder, the other pane after you have moved it somewhere, or (on macOS and
Windows) Finder or Explorer.

| Action | Keys | Menu |
|--------|------|------|
| `clipboard_copy` | `Y`, `Ctrl-C` (`Cmd-C` on macOS) | Edit → Copy |
| `clipboard_cut` | `Shift-Y`, `Ctrl-X` (`Cmd-X`) | Edit → Cut |
| `clipboard_paste` | `G`, `Ctrl-V` (`Cmd-V`) | Edit → Paste |
| `clipboard_clear` | — | Edit → Clear Clipboard |

## Clipboard or C / M?

Both copy and move files, but they answer different questions:

| | `C` / `M` | Clipboard |
|---|---|---|
| Where to | the **other pane**, which you can see now | the folder **you are in when you paste** |
| Steps | one | two: copy or cut, then paste |
| Reaches | the two panes | any folder, and other applications |

`C` and `M` stay the quick way between the two panes. The clipboard is for
everything else: collecting files from several folders, or putting them
somewhere neither pane shows yet.

## Copying, cutting, pasting

- **Copy** or **Cut** takes the selected files, or the one under the cursor.
  Nothing on disk changes yet.
- **Paste** copies them, or moves them after a cut, into the folder of the
  active pane. It asks before overwriting, with the same dialog as `C` and
  `M`.
- A **copy** stays on the clipboard after pasting, so you can paste it again
  elsewhere. A **cut** is used up by its paste.
- Pasting a cut into the folder it came from does nothing.
- You can't paste into a search-results pane or into an archive. Go to a
  folder first.

The clipboard holds any file XeFM can reach, including files on SSH and S3
and files inside archives.

## Seeing what you carry

- **The status bar** starts with what the clipboard holds: `[COPY 3]`,
  `[CUT 1]`, or `[2 from another app]`. It stays there while you search, so
  "find the destination, then paste" works. **Click it** to see the files it
  holds, then choose **Paste Here** or **Clear**. **Edit → Show Clipboard…**
  opens the same list.
- **Each pane's footer** says how many names a paste there would run into:
  `paste: 2 conflicts`.
- **The files themselves** show their names in *italics* wherever they are
  listed. Cut files are also faded.

## With Finder and Explorer (macOS and Windows desktop apps)

- **Copying** local files in XeFM also puts them on the system clipboard, so
  `Cmd-V` in Finder or `Ctrl-V` in Explorer pastes them. A cut in XeFM is a
  cut for Explorer too. Finder has no cut for files, so it always copies.
- **Copying files in Finder or Explorer** and then pasting in XeFM pastes
  those files. Once you are back in XeFM, the status bar says
  `[n from another app]`. An Explorer **Cut** moves the files when you paste them in
  XeFM.

Files on SSH, S3 or inside archives can't go on the system clipboard. They
stay on XeFM's own clipboard only.

**It is one clipboard.** Whatever you copied last is what it holds, as
everywhere else on your computer. If you copy text after copying files in
XeFM, in another app or from XeFM's own log, the files are no longer on the
clipboard: the status bar clears, and their names are no longer in italics.

## In a terminal, and on Linux

XeFM's own clipboard works the same everywhere, in the desktop apps and in
every terminal. It does not connect to the system clipboard in a terminal or
on Linux. A terminal session may be running on another machine, where "the
system clipboard" would be the wrong one.

## The copy key and the log

When text is highlighted in the log pane, the copy key copies that text
instead of files, as it always has. **Edit → Copy Log Selection** does that
too. Copying text replaces the files on the clipboard, also in a terminal and
on Linux.

## Keys from an older config.py

A `config.py` written before this feature binds `Ctrl-C` to
`copy_log_selection`, and that binding comes first. `Y`, `Shift-Y` and `G`
still work. To give `Ctrl-C` to the clipboard, change the line to:

```python
'copy_log_selection': [],
```

The new copy key still copies log text when the log has a selection.
