# Flat View

English \| [日本語](FLAT_VIEW_FEATURE.ja.md)

Flat view swaps the pane's listing for **every file below the current
directory**, in one flat list. Press the key again to go back.

| Action | Key | Menu |
|--------|-----|------|
| `flat_view` | `Shift-B` | View → Flat View |

It is also in the command palette (`Ctrl-T`).

```
Photos/                          2024/trip/a.jpg
  2024/trip/a.jpg       →        2024/trip/b.jpg
  2024/trip/b.jpg                2025/c.jpg
  2025/c.jpg                     notes.txt
  notes.txt
```

## What it is for

Anything you can do with a list works on the whole tree at once:

- **Find what takes the space** — sort by size (`3`).
- **See what changed recently** — sort by date (`4`).
- **Collect files of one kind** — filter by `*.jpg` (`;`), select them all, and
  copy them to the other pane.

You can also view, edit, rename, delete, compare and get details as usual.

## What is in the list

- **Files only.** Directories don't get rows of their own, but every file
  inside them is listed.
- Each row is named by its path below the directory you started from, such as
  `2024/trip/a.jpg`. Sort, filter and incremental search use that path, so
  `2024/*` filters to one year.
- **Hidden files follow the pane.** Anything the pane hides (`.` toggles it) is
  neither listed nor looked into.
- **Symbolic links to directories are not followed**, so a link that points
  back up the tree can't make the list endless. A link to a file is listed.
- The pane header reads `[Flat view] /the/directory`.

## Flattening only part of the tree

If items are selected when you press `Shift-B`, only those are flattened. Each
selected directory contributes everything below it, and each selected file
appears as itself. To flatten the whole directory, clear the selection first
(`End`).

## Large and remote trees

The progress dialog counts the files as they are found, and `Esc` stops the
walk. Stopping leaves the pane as it was rather than showing part of the tree.
Flat view works under `ssh://`, `s3://` and inside archives, the same as
any other location.

## Going back

`Shift-B` again, or `Backspace`, returns to the directory with the cursor on
the item it was on.

## Things to know

- **The list is a snapshot.** Files you delete, move or rename from the list
  drop out of it. Files added to the tree afterwards don't appear until you
  leave the view and open it again.
- **Copying out of the list is flat.** Copying `2024/a.jpg` and `2025/a.jpg` to
  the other pane puts both directly into that directory, so the second one
  meets the first and you get the usual
  [conflict dialog](FILE_OPERATIONS_FEATURE.md).
- Flat view works on directories. On a search-results pane or an imported
  list it says so and does nothing.

## Changing the key

```python
KEY_BINDINGS['flat_view'] = ['Ctrl-B']
```

`Ctrl-B` is not the default because it is tmux's prefix key, so inside tmux it
never reaches XeFM. See [Key Bindings](KEY_BINDINGS_FEATURE.md).

## Related

- [Search options](SEARCH_OPTIONS_FEATURE.md): `Shift-F` with `*` finds files
  by name across a tree, when you want to pick which ones.
- [File lists](FILE_LIST_IMPORT_FEATURE.md): a list of paths from the
  clipboard, a command or a file.
