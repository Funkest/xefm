# Branch View — Implementation

[#559](https://github.com/crftwr/xefm/issues/559), from discussion
[#547](https://github.com/crftwr/xefm/discussions/547). User-facing behavior is
in [`doc/BRANCH_VIEW_FEATURE.md`](../BRANCH_VIEW_FEATURE.md).

Branch view is a third kind of virtual pane, next to a search feed and an
imported list. The pane model, its listing worker and the operations on it are
described in
[SEARCH_RESULTS_PANE_IMPLEMENTATION.md](SEARCH_RESULTS_PANE_IMPLEMENTATION.md)
and [FILE_LIST_IMPORT_IMPLEMENTATION.md](FILE_LIST_IMPORT_IMPLEMENTATION.md).
This document covers what is specific to it: the walk, and how it enters the
pane.

## Pieces

| Piece | Where |
|---|---|
| The action, and its toggle back | `XeFMApp.branch_view` (action `branch_view`, `Shift-B`, Go → Branch View) |
| The walk on a task | `XeFMApp._run_branch_walk` |
| What the walk lists and descends | `_branch_files` (module level in `xefm/app.py`) on `tree_walk.walk` |
| Entering the pane | `XeFMApp._open_branch` → `_list_virtual(..., entries=…)` |
| Installing read entries without a probe | `FileListManager.compute_virtual_listing(..., entries=…)` |
| Header | `_virtual_header_text`, which handles `"branch"` the same way as `"list"` |

## The virtual dict

```python
{"kind": "branch", "title": "Branch", "root": <the pane's directory>,
 "results": [Path, ...], "meta": {}, "return_to": <focused row's name>}
```

The root is given, not derived, unlike an imported list. The rows are below the
directory the user was in, so that directory is what they are named relative
to, even when every file happens to sit in one subdirectory. `return_to` is the
same field `_open_list` writes, so `_go_parent` lands back on the row the
cursor was on without any change. The action's toggle back is simply
`_go_parent`.

## The walk

`_branch_files(root, cancel, show_hidden)` is `tree_walk.walk` with two rules:

- **shows**: not hidden, unless the pane shows hidden entries. This is the same
  rule a filename search uses (`_search_rules`).
- **descend**: a directory, not a symbolic link, and shown.

It yields files only. Unlike a search, it does not descend into links to
directories. A search is bounded by the dialog's result cap, but branch view
has no cap, so a link back up the tree would never end. `is_dir` describes a
link's target (see
[DIRECTORY_SCAN_SYSTEM.md](DIRECTORY_SCAN_SYSTEM.md)), so the `is_link` check
is needed in addition.

The walk uses `tree_walk`, so it lists several directories at once on backends
that set `LISTING_CONCURRENCY` (SFTP). It runs on a `Task`, the same way
`_run_list_command` does: the `ProgressDialog` stays in its busy phase showing
`task.counted`, and Esc sets the flag. `tree_walk.walk` takes an object with
`is_set()`, so `Task.cancelled` is wrapped in a `SimpleNamespace` rather than
exposing the task's private `Event`.

**Cancel shows nothing.** A partial walk arrives in storage order, not tree
order, so a partial list would look complete and wouldn't be.

## No second read

A list's rows are probed on the listing worker, one attribute read per path,
and that read is the existence check. A walk already has every record from the
listings it made. Probing again would double the round trips on a remote tree
and learn nothing new. So `compute_virtual_listing` takes `entries`, which
replaces the probe with `Probed(entries, 0, 0)`, and `_list_virtual` passes it
through. It passes `entries` only when it was given, because test doubles of
`FileListManager` predate the parameter.

The post-operation refresh still goes through the probe as for any virtual
pane, so a deleted or moved file drops out of `results`.

## Selection

Selected directories become the walk's roots. Selected files are taken as
they are, with the records from the pane's own `_listing_entries`, minus
`cmp_name`. That field was computed for the directory pane (a bare basename),
and `_assemble_listing` fills it only where it is missing, so a stale value
would survive. With nothing selected, the root is the pane's directory.

#547 floated a second key for "selected subdirectories only". Here the
selection decides instead, which is how every other action already scopes
itself.

## Decisions from #547

| Question | Answer |
|---|---|
| Directories in the list? | No: files only. |
| Selected subdirectories only | The selection, on the same key. |
| Scale | A cancellable task, no cap. Rows do not stream in. The list appears when the walk ends. |
| Copy out of a flat list | Flat. Name collisions go to the conflict dialog. A "keep relative paths" option in the copy dialog is not done. |
| Freshness | A snapshot. Monitoring is suspended, as for every virtual pane. |
| Leaving | The same key, or `go_parent`, back to the row the cursor was on. |
| Key | `Shift-B`, not `Ctrl-B` (tmux's prefix). |

## Not done

- **Streaming rows in.** The listing worker installs one result. Streaming
  would need an incremental install path that no virtual pane has yet.
- **Keep relative paths when copying.** This belongs in the copy dialog, and
  it would apply to search results too.
- **Re-walking on refresh.** Refresh is the post-operation reconciliation (see
  FILE_LIST_IMPORT_IMPLEMENTATION.md, "Refresh does not re-run the command").
  The same reasoning holds for a walk.

## Tests

`test/test_branch_view.py`, headless on the memory backend. It covers files
only and relative names, hidden entries following the pane, a link loop not
descended, the toggle back landing on the original row, `go_parent`, a
selection narrowing the walk, an empty tree leaving the pane alone, a list not
being flattened, a deleted file dropping out on refresh, and the header.
