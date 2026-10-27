# File Operations System

## Overview

Copy, move, duplicate, and delete are provided by a single class, `FileOperationService` (`xefm/file_operations.py`). It confirms the operation on the main thread, then runs the actual work as a background **task** (see [Task Framework](TASK_FRAMEWORK_IMPLEMENTATION.md)) whose body is one **linear** function — prepare → resolve conflicts → count → execute, top to bottom. There is no state machine and no separate UI / executor / list-manager split; the earlier four-layer design was removed in the PuiKit port.

The same service instance serves any view. `XeFMApp` owns one (`self._fileops = FileOperationService(config, self.tasks)`); a full-window modal such as the directory-diff viewer can construct its own and pass a higher `z` so its dialogs stack above itself.

## Copy operation — end to end

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant App as XeFMApp
    participant Svc as FileOperationService
    participant Mgr as TaskManager + ProgressDialog
    participant W as worker thread — _run()

    U->>App: press C (copy)
    App->>Svc: copy(panel, targets, dest_dir, on_complete)
    Svc->>U: CONFIRM_COPY message box (if enabled)
    U-->>Svc: confirm
    Svc->>Mgr: submit(task, run=_run)
    Mgr->>U: show ProgressDialog (modal)
    Mgr->>W: spawn worker
    W->>W: _resolve() — build plan of survivors
    loop each colliding destination
        W->>U: ask() → ConflictDialog (via pump)
        U-->>W: Overwrite / Overwrite older / Skip / Keep both / Cancel
    end
    W->>W: _count() → set progress total
    loop each planned target
        W->>W: checkpoint(); _execute_one(); update progress
    end
    W-->>Mgr: result {done, skipped, failed, items, errors, cancelled}
    Mgr->>U: close dialog
    Mgr->>App: on_complete(result) → summary in the log
```

## Public API

```python
FileOperationService(config, tasks: TaskManager | None = None)
```

Each entry point takes the `panel` to draw on plus keyword options (`on_complete`, `log`, `z`, `background`):

| Method | Destination | Confirm flag | Conflict handling |
|---|---|---|---|
| `copy(panel, targets, dest_dir, …)` | `dest_dir/name` | `CONFIRM_COPY` | per-file prompt |
| `move(panel, targets, dest_dir, …)` | `dest_dir/name` | `CONFIRM_MOVE` | per-file prompt |
| `duplicate(panel, targets, dest_dir, …)` | in place (source's own dir) | `CONFIRM_DUPLICATE` | none — always auto-renamed `name (N)` |
| `delete(panel, targets, …)` | — | `CONFIRM_DELETE` (default button = Cancel) | — |

`_start` shows the relevant `CONFIRM_*` message box (skipped when its config flag is off); on confirm, `_submit` builds a `Task` and hands it to `TaskManager.submit(run=self._run, …)`.

## The linear worker (`_run`)

Runs on the task thread, top to bottom:

1. **Plan.** Build a list of `(target, dest_base, overwrite)`:
   - **delete** — trivial (one entry per target).
   - **duplicate** — pre-plan a fresh ` (N)` name per target (an in-place copy always collides, so it never prompts).
   - **copy / move** — `_resolve` checks each destination for an existing file and prompts only for collisions.
2. **Count.** `_count` recursively totals the nodes and bytes to process, so the progress bar is determinate. A move that stays within one *filesystem* is a single atomic rename, so it counts as one node and its subtree is never walked (`_is_atomic_move`); a move to another filesystem is walked like a copy, because that is what it is.
3. **Execute.** For each planned target: `task.checkpoint()` (cancellation point), then `_execute_one`, updating `task.progress`. Per-target exceptions are recorded in `errors` and processing continues; a `Cancelled` unwinds the loop.

### Result summary

`_run` returns a dict the caller reports via `format_op_summary` / `format_op_errors`:

| Key | Meaning |
|---|---|
| `done` / `skipped` / `failed` | counts of **top-level targets** (what the user selected) |
| `items` | total individual entries actually processed (recursive) |
| `errors` | list of `(name, message)` for failed targets |
| `cancelled` | `True` if a checkpoint or a "Cancel" conflict choice unwound the run |

A top-level target is `done` if any of its entries succeeded; `failed` only if it produced nothing and raised. Inner file failures stay in `errors` without sinking the whole target.

## Conflict resolution (`ConflictDialog`)

For copy/move, `_resolve` prompts per collision through the task's UI bridge — `task.ask(_conflict_prompt(...))` pushes a `ConflictDialog` (a `FocusContainer` + `Widget`) that stacks just above the progress dialog. `_conflict_prompt` stats both sides into a `ConflictSide` (path, folder?, size, mtime) **on the task thread** before posting the prompt, so a remote stat never blocks the UI; the dialog renders them as a Markdown table under the message (`_sides_markdown`), marking the newer and the larger side. It offers these actions plus an **apply-to-all-remaining** checkbox, and reports `(action, apply_to_all)`:

| Action | Key | Effect |
|---|---|---|
| Overwrite | `o` | replace the destination (`overwrite=True`) |
| Overwrite older | `u` | a file: `overwrite=True` if `_dest_is_older`, else counted as skipped. A folder merge: `overwrite=OverwriteOlder()`, decided per file (below) |
| Skip | `s` | leave it; increment `skipped` |
| Keep both | `k` | write to a fresh `name (N)` (via `_unique_dest`) |
| Compare | `d` / `=` | not an answer: `show_diff_viewer` above the dialog (`z + 5`); closing the viewer lands back on the dialog, still waiting. Offered only when both sides are files |
| Cancel | `c` / `Esc` | raise `Cancelled` — abort the whole operation |

`a` / Space toggles apply-to-all, Tab moves focus, Enter activates the focused button. Left/Right walk the buttons (wrapping at the ends, as `MessageBox` does); Up/Down hop between the buttons and the checkbox above them, returning to the button last focused. When apply-to-all is checked, the chosen action is reused for every remaining collision without prompting — for Overwrite older that still means a per-item date check, which is what makes it "overwrite all older".

The box is sized to its content, not to a row count. `show` asks the message for its height — `MarkdownView.measure(panel.layout_context(), "y", w - 4)`, the same layout its draw runs — because the table's height is the backend's: a GUI table's border and cell rows are not whole base units, so any fixed row estimate leaves spare space on one backend or scrolls on the other. Title (`title_content_top`), message, a one-row gap, the checkbox and the button rows add up to the height, rounded up to whole rows on a grid. Six buttons do not fit one row of a narrow dialog, so `_button_rows` breaks them into rows by measured width; `show` runs the same breaking with the same `LayoutContext` for the height, and `draw` places what it returns.

**Skip is the default** (`_DEFAULT_CONFLICT_ACTION`): focus starts on it, so a bare Enter skips — the safe resolution, matching the app's other destructive confirms (Delete, archive overwrite), whose focus starts on Cancel. Every button is `secondary`: Enter presses the *focused* button and focus always rests on one, so the focus ring is the one cue for what Enter does. An accent fill pinned to Skip would only repeat that until focus moved, then mark a button Enter no longer presses. PuiKit's `MessageBox` follows the same rule.

### Folder conflicts

A folder colliding with a folder is a merge (`_merges_into`), and `_resolve` asks once for it — the per-file decisions happen inside the merge, without prompting. The folders' own mtime and size say nothing about those decisions (a directory's mtime moves only when its direct entries are added, removed or renamed), so before posting the prompt `_resolve` runs `_merge_summary` on the task thread: a walk of the source (symlinks not followed, a subtree missing at the destination counted without a stat per file, `task.checkpoint()` per entry) that classifies each file with the Overwrite-older rule into `older` / `not_older` / `only_source`. It stops at `_SUMMARY_LIMIT` (10,000) files and sets `capped`, so a huge or remote tree does not hold the prompt back. The dialog (titled "Folder exists") shows that `MergeSummary` in place of the size/date table, and offers no Compare.

### Overwrite older

`compare_mtimes(a, b)` is the one newer/older rule — 1, -1, or 0 within `_MTIME_SLACK` or when either time is unknown — shared by the dialog's "newer" mark, the folder summary, and the directory diff viewer's details row. `_dest_is_older(src, dest)` is `compare_mtimes > 0`: true when the source's mtime exceeds the destination's by more than `_MTIME_SLACK` (2 s — FAT/exFAT's resolution, the same allowance as rsync's `--modify-window`). An unreadable time on either side answers false: the rule never overwrites on a guess. The dialog's "newer" mark uses the same slack, so what it shows is what the action will do.

Collisions are resolved at the top level only, so a folder merged under this rule carries the rule down as its `overwrite` value: an `OverwriteOlder` instance, truthy so every flag-style check treats it as a merge. `_copy_file` is the one place that looks inside — on an inner collision it overwrites when `_dest_is_older`, otherwise returns False (skipped, logged by `_log_kept`) and sets the instance's `kept`. It hands only a plain `bool` on to the storage layer. One instance per target, shared by the parallel pool's jobs for that target; `kept` is only ever assigned True, so no lock is needed.

A move removes its source after a merge only when nothing failed **and** nothing was kept (`_kept_any`) — in both the sequential `_execute_one` and the parallel `_run_parallel` — so a file whose destination was newer is never deleted from the source without having been carried over.

## Duplicate

In-place duplication (GitHub issue #192) is a thin `"duplicate"` operation kind layered onto the shared copy engine, plus app wiring for the two entry points. No new copy/rename logic was written — it reuses `_unique_dest()` and the existing threaded task pipeline.

### Engine — `xefm/file_operations.py`

`"duplicate"` is registered alongside `copy`/`move`/`delete`:

- `_VERB["duplicate"] = "Duplicate"`, `_OP_TYPE["duplicate"] = OperationType.COPY`.
- `FileOperationService.duplicate(panel, targets, dest_dir, …)` mirrors `copy()` and calls `_start(..., "duplicate", ...)`. `dest_dir` is the source's own directory.

It differs from copy in exactly one place — plan building in `_run()`. A duplicate always collides with itself, so it **never prompts**; instead every target is pre-planned to a fresh ` (N)` name up front:

```python
elif kind == "duplicate":
    plan = [(t, _unique_dest(dest_dir, t.name, is_dir=t.is_dir()), False)
            for t in targets]
    result["created"] = [dest.name for _t, dest, _o in plan]
```

Because distinct targets in one directory have distinct names, computing all destinations against the pre-op filesystem state is collision-free (unlike duplicating the *same* file twice, which cannot happen — targets are distinct list entries). `result["created"]` carries the new names back to the caller for cursor placement.

Everything else falls through the copy path: `_count()` walks the plan, `_execute_one()` routes to `_copy_tree()` (the `if kind == "move"` source-delete is skipped, so the original is never removed), and the per-file log line reads "Duplicated" via the verb map `{"move": "Moved", "duplicate": "Duplicated"}.get(kind, "Copied")`.

The confirm prompt in `_start()` gets a duplicate-specific line ("Duplicate **N** item(s) in `<dir>`?") and honors `CONFIRM_DUPLICATE` through the existing `getattr(config, f"CONFIRM_{verb.upper()}", True)` — no special casing needed. `CONFIRM_DUPLICATE = True` lives in `xefm/_config.py`.

### App wiring — `xefm/app.py`

Two entry points, one shared runner:

- `duplicate_files()` — guards (virtual pane, read-only archive, empty targets), gathers `_selected_or_focused(pane)`, then delegates to `_run_duplicate`. Returns `True` on a synchronous guard bail, `False` after handoff — same contract as `copy_files()`.
- `_run_duplicate(pane, targets)` — calls `self._fileops.duplicate(...)` with `pane["path"]` as the destination. `on_complete` clears the source selection, re-lists via `_relist(pane, on_ready=lambda p: _select_by_name(p, created[0]))` so the cursor lands on the new copy, re-lists the other pane too when it shows the same directory (`_relist_others_showing`), logs `format_op_summary("Duplicate", …)`, and reports failures.

Reachability (no default key binding):

- Dispatch: `elif action == "duplicate_files": return self.duplicate_files()` — so a user-defined `duplicate_files` key binding works.
- Menu bar (`_build_menu` → File menu) and right-click context menu (`_show_context_menu`): a **Duplicate** item after **Rename…**.

The same-directory copy relaxation lives in `_run_transfer()` (shared by `_transfer()` and `_transfer_to_path()`): when `dest_dir == src_pane["path"]` and `kind == "copy"`, it routes to `_run_duplicate(src_pane, targets)` instead of logging the old "source and destination are the same directory" error. Move keeps that error.

### Tests

`test/test_file_operations.py` — the `cfg` fixture sets `CONFIRM_DUPLICATE = False` for headless runs; tests exercise file, directory, and multi-target duplication (each getting its own ` (N)`) plus the "Duplicated" log line, all via the existing `_run_sync(svc, svc.duplicate, …)` harness.

## Helpers

- `recursive_delete(entry)` — delete a file or directory tree.

  On Windows, a file or directory with the read-only attribute can't be removed (`ERROR_ACCESS_DENIED`, whatever the caller's rights). `LocalPathImpl.rmdir` / `unlink` therefore clear the attribute and try once more when that is why they were refused, and only then: a removal that works touches no attribute, and a second refusal puts the attribute back. Every local delete goes through them — `_delete_tree`, `recursive_delete`, and the source half of a move to another filesystem, whose `shutil.rmtree` gets the same retry. Google Drive for desktop marks every directory of its mirrored folder read-only, so without this nothing there could be deleted.
- `_unique_dest(dest_dir, name, is_dir=…)` — the shared ` (N)` non-colliding-name scheme (used by duplicate and "Keep both").
- `_is_atomic_move(kind, target, dest_dir)` — true when a move stays within one *filesystem* (a single rename); anything wider copies the tree then deletes the source.
- `_entry_device(path)` — `st_dev` of the filesystem holding `path`, or `None` when it isn't local / can't be stat'ed.

  One storage backend is not one filesystem. `rename` only works inside a single filesystem, so a local move to an external drive, another partition, or a network share is really a copy followed by a delete — it takes as long as a copy and needs the same feedback. `_is_atomic_move` therefore compares schemes *and* devices: the device holding the source's parent (where its directory entry lives) against the one holding `dest_dir` (where the new entry lands). When either device is unknown the scheme test decides alone, which is safe: `Path.move_to` still falls back to copy+delete on `EXDEV`, so the only cost of guessing "atomic" is an unprogressed move rather than a wrong one.
- `format_op_summary(verb, result)` / `format_op_errors(verb, result)` — human-readable reporting from the result dict.

## Integration

- `XeFMApp.__init__` — `self.tasks = TaskManager()`, `self._fileops = FileOperationService(self.config, self.tasks)`.
- `XeFMApp.copy_files()` / `move_files()` / `duplicate_files()` / `delete_files()` gather the active pane's selection and delegate to `self._fileops`, passing an `on_complete` that refreshes panes and logs the summary.
- `XeFMApp.copy_files_to()` / `move_files_to()` (Shift-C / Shift-M, #528) go through `_transfer_to_path()`: the source-side guards of `_transfer()`, then a `show_input` prompt shaped like Jump to Path's — prefilled with the other pane's directory, `FilepathCompleter(directories_only=True)` rooted at the active pane, input resolved by `_resolve_jump_target` against the active pane (so `.` is "here"). The destination guards (non-empty, not a read-only archive, an existing directory) run as the prompt's `validate`; accept hands off to `_run_transfer()`. Its `on_complete` re-lists every pane whose path equals the destination, plus the source on a move — for C / M that is exactly the other pane, as before.

## References

- [Task Framework](TASK_FRAMEWORK_IMPLEMENTATION.md)
- [Task Cancellation](TASK_FRAMEWORK_IMPLEMENTATION.md#cancellation)
- [Progress Manager System](PROGRESS_MANAGER_SYSTEM.md)
- [Path Polymorphism System](PATH_POLYMORPHISM_SYSTEM.md) — storage-agnostic operations behind `Path`
