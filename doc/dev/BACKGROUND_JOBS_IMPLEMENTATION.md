# Background Jobs — Implementation

[#567](https://github.com/crftwr/xefm/issues/567), part 1 of discussion
[#468](https://github.com/crftwr/xefm/discussions/468). User-facing behavior is
in [`doc/BACKGROUND_JOBS_FEATURE.md`](../BACKGROUND_JOBS_FEATURE.md). The task
system it extends is described in
[TASK_FRAMEWORK_IMPLEMENTATION.md](TASK_FRAMEWORK_IMPLEMENTATION.md).

## What was already true

A `Task`'s worker already ran off the UI thread. What kept the user waiting was
the `ProgressDialog`: a modal layer, and while a layer is up `on_event`
routes every key to it. So "background" here means only this: **the dialog
leaves the screen while the worker goes on.** Nothing about the worker
changes.

## `TaskManager`

| Piece | |
|---|---|
| `_Job` | One running task: its dialog, `finished` event, `on_done`, `z`, and whether it holds the queue's slot |
| `submit(..., detached=True)` | Start in the background, through the queue |
| `detach(task)` | Close the dialog and set `task.background` |
| `bring_forward(task)` | Show the dialog again, or drop a queued task |
| `background_tasks()`, `queued_count()` | For the status bar and the jobs list |
| `_tick(job)` | The per-frame pump, now per job |
| `_start_next()` | Give the slot to the next queued job |

**The serial queue.** One background job runs at a time. `_slot_taken()` is
true while any job either holds the slot (it was started detached) or is
background (it was detached later). A detached `submit` waits in `_queue`
while the slot is taken. Every teardown calls `_start_next()`. A queued task
cancelled before it started is finished and reported as cancelled without
running. A foreground `submit` never waits, because the user chose to watch
it.

**Prompts wait.** `Task.ask` already blocks the worker on a request that the
main thread services. `_tick` now calls `dialog.pump` only while the task is
in the foreground. A background job's request stays queued.
`Task.needs_attention` (background and a request pending) is what the status
bar shows. `bring_forward` puts the dialog back, and the next tick's pump
opens the prompt. This is #468's option (a). Option (b), a policy chosen when
detaching, would sit in front of it later.

**Repaint.** A foreground job repaints every frame, as before. A background
one repaints every 0.25 s (`_BACKGROUND_REPAINT_S`), enough for the status
bar's percentage.

## `ProgressDialog`

It takes `on_background` (the manager's `detach`). **B** calls it. The Esc box
became **Run in background / Cancel operation / Keep running**, with Keep
running as both the default and the cancel button, so a stray Enter or Esc
changes nothing. A dialog built without a manager behind it offers no
background button.

## `FileOperationService`

The `CONFIRM_*` box gains **Background** between the verb and Cancel, for
copy, move and delete when `background=True` (synchronous test runs have no
pump to run a detached task on). The defaults are unchanged: the verb for
copy and move, Cancel for delete. `_submit(..., detached=)` passes it through
to `TaskManager.submit`.

## The app

- `StatusBar.draw` draws `XeFMApp._jobs_text()` at the right end, in the
  accent color, and the key hints give way to it.
- `show_jobs` (action `jobs`, `Ctrl-G`, View → Background Jobs…) is a
  `ChoiceDialog` of `background_tasks()`. Choosing one calls `bring_forward`.
- `confirm_quit` with background jobs names them and defaults to Cancel.
  Quitting anyway calls `TaskManager.cancel_all(timeout=3.0)`, which cancels
  the queue and every running task and waits for the workers to unwind at
  their next checkpoint (which removes a half-written file) instead of dying
  mid-write with the process. A worker still busy after three seconds is
  logged and abandoned.

`on_done` needed nothing new. A background job's completion runs the same
callback on the main thread, which refreshes the panes and logs the summary.

## Not done

From #468: delete to the trash, the operation journal and undo, a guard
against operating on paths a job owns, a conflict policy at detach time, and
parallel background jobs.

## Tests

`test/test_background_jobs.py`, on the memory backend with real animation
ticks. Each task body waits on an `Event` the test releases. It covers detach
(the dialog goes, the task completes), queued jobs running in order, a
foreground task not waiting for the queue, a background prompt waiting until
brought forward and then answered, dropping a queued job, **B** and the Esc
box, the copy confirmation's Background button copying with no dialog, delete
still defaulting to Cancel, the status bar text, the quit guard, and
`cancel_all` waiting for the workers.
