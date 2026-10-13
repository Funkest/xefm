# Quick View

Press `Shift-V` (**View → Quick View**) and the **other pane becomes a
preview** of the item under the cursor. Move the cursor and the preview
follows. Press `Shift-V` again to close it.

| Item under the cursor | The preview shows |
|-----------------------|-------------------|
| Text file | the start of the file (up to 256 KB), syntax-highlighted as in the text viewer |
| Picture | the picture, fitted to the pane |
| Other binary file | a hex dump of the first 512 bytes |
| Folder | how many files and folders it holds and their total size, counted while you watch |

Above the content, a header line names the item, with its size and date.

## Working with it

- **The keyboard stays on the file list.** Move, select, copy and delete as
  usual. The preview only watches.
- **Scroll the preview with the mouse wheel.**
- **The other pane is kept.** Its folder, cursor and selection come back
  exactly as they were when quick view closes.
- **Switching panes closes quick view** (`Tab`). The preview is not a pane you
  can work in.
- Copy and move still go to the other pane's folder, even while it is hidden
  behind the preview.

## Speed

The preview waits until the cursor stops for a moment, so moving quickly down
a long listing doesn't read every file it passes.

On a **remote** location (`ssh://`, `s3://`, inside an archive), only files up
to 256 KB are read. Larger files show their size and date. Remote folders are
not counted, because counting would walk the whole tree over the network.

In a terminal that can't draw pictures, a picture shows only its details.

## See also

- [Text Viewer](TEXT_VIEWER_FEATURE.md) and
  [Image Viewer](IMAGE_VIEWER_FEATURE.md): the full viewers (`V`)
- [File Details](FILE_DETAILS_FEATURE.md): size on disk and more (`I`)
