# Quick View — Implementation

[#569](https://github.com/crftwr/xefm/issues/569), from discussion
[#473](https://github.com/crftwr/xefm/discussions/473), part 1. User-facing
behavior is in [`doc/QUICK_VIEW_FEATURE.md`](../QUICK_VIEW_FEATURE.md).

## Taking the other pane's place

`XeFMApp.quick_view` swaps the inactive side's child of `pane_splitter`
(`.first` or `.second`, both plain attributes the Splitter reads every frame)
for `LayoutView(VSplit(Item(QuickView)))`, and keeps the column it replaced.
`_close_quick_view` puts that column back. Nothing about the hidden pane is
touched: its dict, view, header and footer stay as they were, so it comes back
exactly as it was left. A copy or move still targets it.

Closing happens in `_sync_active`: whenever the active side becomes the
preview's side (`switch_pane`, `focus_left` / `focus_right`, `nav_left` /
`nav_right`), quick view closes. A preview that became the active pane would
leave the user working in a pane they cannot see. A click on the preview
activates nothing, because `QuickView` is not a `FilePane`.

`_quick_view_follow` runs after every key and mouse event the file list
handles, and hands the cursor entry and its `file_info` record to
`QuickView.follow`.

## `QuickView`

`xefm/quick_view.py`. It is not focusable, so it never takes the keyboard. It
handles only the mouse wheel.

**Why not embed the viewers.** `TextViewer` and `ImageViewer` are full-window
modal widgets with their own chrome, keymaps and lifetimes. The preview needs
their *pieces*, and those are module-level already:

| Content | From |
|---|---|
| Decoding | `text_encoding.decode_text`, `looks_binary_bytes` |
| Highlighting | `text_viewer._highlight` with `_syntax_palette(panel)`, resolved on the UI thread and handed to the worker |
| Tabs | `text_viewer._expand_tabs` |
| Pictures | `image_decoders` (native suffix → the path; a decoder → a `RasterImage`), drawn with `draw_image(fit="contain")` |
| Folder totals | `disk_usage.UsageScan`, the walk the details dialog uses |

**Loading.** `follow` resets the state, bumps `_gen`, and sets a due time
`DEBOUNCE_S` (0.15 s) away. Its animation tick starts the load once the
cursor has rested that long. A file loads on a worker, which posts
`(gen, kind, lines, note, image)` into `_result`. The tick installs it only if
`gen` still matches, so a result for an item the cursor has left is dropped.
A folder starts a `UsageScan`. `follow` cancels the previous scan, and the
tick repaints every 0.2 s while it runs. The tick keeps running only while a
load is pending or a scan is running.

**Caps.** `TEXT_CAP` (256 KB) of a local text file is read, and its last line
dropped if the cap cut it. `HEX_BYTES` (512) are shown for a binary. On a
remote location (`"://"` in the path), a file is read only up to `REMOTE_CAP`
(256 KB), and a folder is not walked. Those show `details` with a one-line
reason. A picture is decoded here only up to `IMAGE_DECODE_CAP`, and only when
the panel draws images (`panel.images`).

**Drawing.** Row 0 is the name (accent), row 1 is size and date from the
pane's own `file_info` (no extra `stat`), then the body. Text rows are drawn
segment by segment in `MONO`, advancing by `display_width`, as the text viewer
does, and are cut at the pane's width rather than wrapped.

## Not done

Rich renderers (Markdown, JSON, CSV), audio / video (#473 part 2), press-to-
load for large remote files, and keyboard scrolling of the preview.

## Tests

`test/test_quick_view.py`. The pure half covers the hex dump, `is_remote`, and
a large remote file never being opened. The app half, on the memory backend
with real ticks and workers, covers toggling taking the other pane and giving
the same column back, a text file's start, a binary's hex dump, a folder's
totals, only the rested-on item loading, and switching panes closing quick
view.
