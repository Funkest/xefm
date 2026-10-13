# Directory Sync — Implementation

[#560](https://github.com/crftwr/xefm/issues/560), from discussion
[#471](https://github.com/crftwr/xefm/discussions/471). User-facing behavior is
in [`doc/DIRECTORY_SYNC_FEATURE.md`](../DIRECTORY_SYNC_FEATURE.md). The viewer
it lives in is described in
[DIRECTORY_DIFF_VIEWER_SYSTEM.md](DIRECTORY_DIFF_VIEWER_SYSTEM.md).

## Pieces

| Piece | Where |
|---|---|
| The plan: modes, per-node choices, overrides, operations | `xefm/dir_sync.py` (`SyncPlan`, `Operations`) |
| Running it as one task | `FileOperationService.sync` / `_run_sync` in `xefm/file_operations.py` |
| Plan mode in the viewer | `DirectoryDiffView._sync`, `_open_plan`, `_confirm_plan`, `_on_sync_complete`, `_cycle_focused`, `_plan_footer` |
| What the plan needs from the scan | `TreeNode.left_mtime` / `right_mtime` / `type_mismatch`, written by `_record_sides` |
| Differences-only view | `DirectoryDiffView._diff_only`, read by `_flatten` |
| Actions | `dir_diff.sync` (`s`), `dir_diff.cycle_sync_action` (`SPACE`), `dir_diff.toggle_identical` (`d`) |

`dir_sync` has no UI and does no I/O. It reads `TreeNode`s, so it is tested
against trees the viewer scanned synchronously, with no widget involved. It
compares verdicts by `DifferenceType` value rather than importing the enum,
which keeps the dependency pointing from the viewer to the plan.

## Choices, not one action

Each node has an ordered list of choices (`SyncPlan.choices`), and the first is
its default:

| Node | Update | Mirror |
|---|---|---|
| only on source | copy, skip | copy, skip |
| only on target | skip, back, delete | delete, skip, back |
| differing file | copy, skip, back | same |
| differing file, target newer | skip, copy, back | same |
| file vs directory | skip | skip |
| two-sided directory with differences | descend, skip | same |
| identical / pending | — | — |

`cycle` advances through the list. Overrides are keyed by the node's path
**relative to the roots**, not by the node. A per-file merge or a `C` made
while the plan is open triggers `_restart_scan`, which builds new `TreeNode`s,
and the user's choices have to survive that. An override that is no longer
among a node's choices (the merge made the file identical) is ignored rather
than applied. Cycling back to the default deletes the override instead of
storing it.

A skipped two-sided directory skips its subtree. `action()` checks the
ancestors, so the gutter shows `·` on every row below it. `operations()` does
not descend into it, and counts it once.

## Operations

`operations(root)` walks the tree:

- A node on **one side only** is taken whole: one copy or one deletion of the
  directory. Nothing below it is visited. This matches what the scan does,
  since one-sided directories are only listed when the user expands them.
- A **two-sided directory** is descended unless skipped.
- A copy's destination is the target's existing path when there is one
  (overwrite), otherwise `parent's target path / name`. A node is reached only
  through the root or two-sided directories, so the parent always has a path
  on both sides.

The counts (`new`, `replaced`, `back`, `skipped`, `newer_kept`, `mismatched`)
exist for the confirmation. They are computed by walking the plan, so the
footer and the summary agree with what will run.

## Running: `FileOperationService.sync`

`copy` and `move` take one destination directory and resolve conflicts with
the dialog. A plan writes into many directories, and every conflict has already
been decided by the plan itself. So `sync` takes `(source, destination,
overwrite)` triples and a list of deletions, and runs them through the existing
`_execute_one` with no prompts:

- `_release_archives` runs over both lists, so an archive XeFM holds open
  inside something being deleted or overwritten is closed first, or the item
  fails naming its owner (#516).
- Monitor suppression covers each destination's parent and each deletion's
  parent.
- One progress total covers both: `_count` over the copies (with bytes) plus
  `_count` over the deletions.
- **Copies before deletions.** A cancelled Mirror has added before it has
  removed.
- It runs sequentially. The parallel pool (`_run_parallel`) assumes one
  `dest_dir`, which is exactly what a plan does not have.

## Plan mode in the viewer

- `s` with no plan: refused while `_scanning` or while any verdict is still
  `PENDING` (`dir_sync.is_settled`). Otherwise a `ChoiceDialog` picks the
  mode, and the plan opens with `_diff_only` on.
- The gutter draws `plan.glyph(node)` in place of the verdict glyph, which
  still shows where a node has no action. Arrows use the accent color, `×`
  the difference color, and `·` the muted color.
- `Space` → `_cycle_focused`. `Tab` flips `active`, and with it `plan.source`,
  clearing overrides: a choice made for one direction means nothing in the
  other.
- `Esc` / `quit` close the plan first, and the viewer only on a second press.
- `s` with a plan open: refused while a rescan is running. Otherwise a message
  box shows the summary. With deletions it uses the warning icon and the
  default button is **Cancel**, the same as the delete confirmation.
- `_on_sync_complete` closes the plan, reports a cancel or up to five errors,
  and rescans.

`_plan` and `_diff_only` also exist as class attributes, because
`test_tree_management.py` builds views with `__new__` and calls `_flatten`
directly.

## Decisions from #471 and its comment

| Point | Done |
|---|---|
| Update and Mirror first, two-way later | Yes. Two-way is not built. Per-item "back" covers combining two folders. |
| Per-item direction, not just exclusion | Yes, `Space`. A directory row skips its subtree. |
| Display filter | Differences-only (`d`). Filtering by category or by action is not built. |
| Target-newer files flagged, default skip | Yes. They are counted as `newer_kept` in the summary. |
| Delete count apart from copies | Yes. Cancel is the default when anything is deleted for good. |
| Active side as the source | Yes. `Tab` reverses the plan. |
| `Enter` / `E` while planning, re-evaluated after a merge | Yes. Overrides survive the rescan by relative path. |
| Mirror deletions to the trash | Yes, since #603. `_run_sync` makes each deletion a `trash` step where `FileOperationService.goes_to_trash` says there is a trash (local, and `DELETE_TO_TRASH` on), and a `delete` step elsewhere. A trash step counts as one item. The confirmation names the two groups apart (`_split_deletes`) and starts on Cancel only when something is deleted for good. |
| Comparison criteria for mixed storage | Unchanged: the viewer compares content, so S3's upload-time `LastModified` only affects the "target newer" default, not what counts as changed. |
| Exclude patterns (`FILTERS`) | Not built. |
| Background execution | Not built (#468). The task runs behind the usual progress dialog. |

## Tests

`test/test_dir_sync.py`. The plan half covers Update and Mirror operations and
destinations, newer-target skip, cycling and dropping overrides, a skipped
subtree, a file-vs-directory name, the reversed direction, and glyphs. The
viewer half, on the TUI and GUI profiles, covers an Update run end to end,
Mirror's Cancel default followed by a real run, `Space` skipping a file, `Esc`
leaving only the plan, `Tab` reversing it, the `d` toggle, and the plan opening
on differences only.
