# File Clipboard — Implementation

[#577](https://github.com/crftwr/xefm/issues/577), from discussion
[#342](https://github.com/crftwr/xefm/discussions/342). User-facing behavior is
in [`doc/FILE_CLIPBOARD_FEATURE.md`](../FILE_CLIPBOARD_FEATURE.md). The OS side
is PuiKit's `clipboard_files` capability (crftwr/puikit#155).

## Two clipboards, one model

`xefm/file_clipboard.py`'s `FileClipboard` is XeFM's own clipboard: `paths`
(XeFM `Path`s, so S3, SSH and archive entries ride it), `cut`, and `version`,
which changes on every change for anything that caches what it derives. It
is the model on every platform. The OS clipboard is a **bridge** to other
applications, reached through three Panel calls:

| PuiKit | macOS | Windows | Terminal / Linux |
|---|---|---|---|
| `set_clipboard_files(paths, cut=)` | file `NSURL`s | `CF_HDROP` + "Preferred DropEffect" | `False` |
| `get_clipboard_files()` | file URLs → `ClipboardFiles` | `DragQueryFileW` + DropEffect | `None` |
| `clipboard_change_count()` | `changeCount` | `GetClipboardSequenceNumber` | `None` |

On a backend without the capability the calls are no-ops, so XeFM never
branches: in a terminal or on Linux the bridge silently does nothing, and
XeFM's own clipboard is the only one (#342: parity of capability, not of OS
integration). `FileClipboard._bridge` also tolerates a PuiKit that predates
the calls (`getattr`), until the PuiKit floor is raised.

### Which clipboard a paste takes

`contents()` answers that by **change count**. `_mark_seen()` records the OS
clipboard's count at XeFM's every copy, cut and clear, whether or not XeFM
wrote the OS clipboard then (it cannot for an S3 path). Later:

- the count has not moved: XeFM's own clipboard is the newest, so its
  contents are pasted (`origin="xefm"`);
- it has moved and the OS clipboard holds files: another application wrote
  after XeFM, so its files are pasted (`origin="os"`), and the UI says "from
  another app";
- it has moved to text, or to nothing: XeFM's own again.

Recording the count on every copy, not only on a successful OS write, is the
point. Otherwise an S3 copy, which never reaches the OS clipboard, would lose
to files Finder had copied earlier.

`_os_files()` reads the OS clipboard once per change count (`_os_cache`). It
is asked every frame by the status bar and the footers, and the count is the
only cheap question.

### Lifetime

- XeFM copy: survives its paste. XeFM cut: `consume()` clears it after a
  paste that was not cancelled.
- OS files: a copy is pasted again until something else is written. An
  Explorer **Cut** is taken once: `take_os()` marks the count as seen, so the
  next paste no longer sees it.

## The app

| | |
|---|---|
| `clipboard_put(cut=)` | `_selected_or_focused`. The local ones also go to the OS clipboard. With text selected in the log, the copy chord copies that text instead (`copy_log_selection`). |
| `clipboard_paste()` | Refused into a virtual pane or an archive, as a drop is. A cut whose items already sit in the destination is dropped. The rest go through `FileOperationService.copy` / `.move`: the `CONFIRM_*` prompt, the conflict dialog, progress, and background (#567 where merged). Both panes re-list afterwards. |
| `_clipboard_changed()` | Sets `FilePane.clipboard_marks` / `clipboard_cut` and invalidates the status bar. |
| `_paste_preview(pane)` | "paste: N conflicts" for `PaneFooter`, from `file_clipboard.conflicts`: names compared NFC + casefold against the names the pane already lists. No I/O. Cached on the pane, keyed by the listing, the path, the clipboard version and the contents, because the footer redraws every frame. |
| `_clipboard_ramp_hint()` | Once per session after a paste: "C / M copy or move straight to the other pane" (#342's "a ramp, not a destination"). |

**Status bar.** `StatusBar.draw` draws `clipboard.status()` first, in the
accent color, in every state the bar has. That includes incremental search,
where the hint text is replaced but the carried state must stay ("search for
the destination, then paste").

**Rows.** `FilePane._draw_row` gives a marked row's name and extension
`TextAttribute.ITALIC`, and a cut one a 50 % wash toward the pane
background, floored at `HIDDEN_LC` so it stays legible. This is an aid only:
it vanishes once the row is out of view, which is why the status bar is the
primary indicator (#342: Explorer's failure mode).

## Keys

`Y` / `Ctrl-C` copy, `Shift-Y` / `Ctrl-X` cut, `G` / `Ctrl-V` paste, plus
`Command-C/X/V` in the macOS app (`_config.py`'s desktop case, which used to
give `Command-C` to `copy_log_selection`). Letters as well as chords, so the
clipboard is an expert path and not only a beginner one (#342's open
question).

`Ctrl-C` was `copy_log_selection`. `KeyBindings` takes the first action
bound to a key, so the two could not share it. One action now copies "what
is selected": the log's text when it has a selection, files otherwise.
`copy_log_selection` remains, unbound, behind Edit → Copy Log Selection.
Tests that used `Y` as a free key now use `Z`.

An existing `config.py` binds `Ctrl-C` to `copy_log_selection`, which wins.
The feature doc says how to hand it over.

## Not done

A watcher marking stale entries (the copy engine reports a missing source at
paste), Finder's `Cmd-Opt-V` move-paste, the OS clipboard in terminal
sessions on macOS and Windows, and raising the PuiKit floor once #155 is
released.

## Tests

`test/test_file_clipboard.py`. The model half covers XeFM's own clipboard
(copy survives, cut is consumed), local files reaching the OS clipboard, a
newer OS clipboard winning, an older one not winning over a remote copy, an
Explorer cut taken once, text not counting as files, and the conflict
preview. The app half, on the memory backend with real copy and move tasks,
covers copy then paste in the other pane, cut then paste moving and
emptying the clipboard with the tip, a cut pasted in place, the footer
preview, files from "another app" pasting, the system clipboard receiving a
copy, paste refused into a list, and the status bar leading with `[CUT 1]`.
`test_log_clipboard.py` covers the copy chord copying the log's selection.
