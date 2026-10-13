"""xefm.task — a small central task system for XeFM's background operations.

XeFM runs long jobs (copy / move / delete, and later archive / search) on a worker
thread while the UI stays live. This module gives those jobs a *single, linear*
shape instead of a callback state machine:

- a :class:`Task` owns a background worker plus a :class:`ProgressManager`, a
  cancel flag, and a **blocking UI bridge** — :meth:`Task.ask` lets the worker
  thread pop a modal on the main thread and *wait* for the answer, so an operation
  reads top-to-bottom (prepare → ask about each conflict → execute) rather than
  being split across states.
- a :class:`TaskManager` (one per app) knows which tasks exist, shows each running
  task's :class:`ProgressDialog`, and pumps the bridge on the animation tick. It is
  deliberately more than this change needs: it is the seam for future *background*
  (non-modal) execution, a task queue, and a common task-management UI. For now it
  runs one modal task at a time.

Threading contract: the worker only touches its own ``Task`` (progress, cancel
flag, request queue). Everything that draws or reads the panel happens on the main
thread inside :meth:`TaskManager._tick`. The worker never calls ``panel.*``.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time
from enum import Enum
from typing import Any, Callable, Optional

from puikit.backend import DEFAULT_STYLE, Style, TextAttribute
from puikit.event import Event, EventType
from puikit.widgets import BusyIndicator, ProgressBar, show_message_box
from puikit.widgets.base import Widget

from xefm.dialog_geometry import OPEN_MS_VIEWER, animate_open
from xefm.log_manager import getLogger
from xefm.progress_manager import ProgressManager
from xefm.str_format import abbreviate_path, format_size

logger = getLogger("TaskMgr")

#: Transfer rows the progress dialog reserves — the local copy pool's size.
#: A wider pool (S3) folds its overflow into a final "… N more files" row.
_TRANSFER_ROWS = 4
#: A transfer row prints its byte counts only for files at least this large;
#: below it the copy is one shot and the numbers would just flicker.
_BYTE_TEXT_MIN = 1024 * 1024


class TaskStatus(Enum):
    """Lifecycle of a :class:`Task`. Preparing / running / cancelling are *not*
    here — they are display states derived from the progress manager and cancel
    flag (see :class:`ProgressDialog`); only the true lifecycle is stored."""
    PENDING = "pending"      # created / enqueued, worker not started yet
    RUNNING = "running"      # worker thread active
    DONE = "done"            # finished normally
    CANCELLED = "cancelled"  # cancelled (before or during the run)
    FAILED = "failed"        # worker raised an unexpected exception


class Cancelled(Exception):
    """Raised out of :meth:`Task.ask` / :meth:`Task.checkpoint` to unwind a
    cancelled worker back to the top of its ``run`` body."""


class _UiRequest:
    """One worker→main-thread request: run ``show_fn(panel, deliver)`` on the main
    thread, then block the worker on :attr:`event` until ``deliver(answer)`` fires."""

    __slots__ = ("show_fn", "answer", "event")

    def __init__(self, show_fn: Callable[[Any, Callable[[Any], None]], None]):
        self.show_fn = show_fn
        self.answer: Any = None
        self.event = threading.Event()

    def deliver(self, answer: Any) -> None:
        self.answer = answer
        self.event.set()


_task_ids = itertools.count(1)


class Task:
    """A cancellable background job with a progress model and a blocking UI bridge.

    The worker body is an ordinary function ``run(task)`` handed to
    :meth:`TaskManager.submit`; it drives ``task.progress`` and calls
    :meth:`ask` / :meth:`checkpoint`. It must never touch the panel directly."""

    #: Poll interval (s) while a blocked ``ask`` waits, so cancellation interrupts
    #: a pending prompt promptly without a busy-spin.
    _WAIT_TICK = 0.05

    def __init__(self, title: str, *, config: Any = None, kind: str = "",
                 busy_label: str = "Preparing…"):
        self.id = next(_task_ids)
        self.title = title
        self.kind = kind
        #: What the dialog says while the task has no item total to show — the
        #: counting phase of a copy, or the whole of a task that never has one.
        self.busy_label = busy_label
        self.status = TaskStatus.PENDING
        self.progress = ProgressManager(config)
        #: Files seen so far during the (pre-total) counting phase — display only.
        self.counted = 0
        self.result: Optional[dict] = None
        self.error: Optional[BaseException] = None
        self._cancel = threading.Event()
        self._requests: "queue.Queue[_UiRequest]" = queue.Queue()
        #: In synchronous (test) mode there is no main-thread pump, so ``ask``
        #: returns the caller's headless default instead of blocking on a dialog.
        self._headless = False
        #: Running (or queued) without its progress dialog on screen (#567). A
        #: prompt it raises meanwhile waits until it is brought forward.
        self.background = False

    # --- worker-side API (called on the worker thread) -----------------------

    def ask(self, show_fn: Callable[[Any, Callable[[Any], None]], None], *,
            headless: Any) -> Any:
        """Show a modal via ``show_fn(panel, deliver)`` on the main thread and
        block until it delivers an answer; return that answer. Raises
        :class:`Cancelled` if the task is cancelled while waiting. In headless
        mode returns ``headless`` without prompting."""
        if self._headless:
            return headless
        if self._cancel.is_set():
            raise Cancelled()
        req = _UiRequest(show_fn)
        self._requests.put(req)
        while not req.event.wait(self._WAIT_TICK):
            if self._cancel.is_set():
                raise Cancelled()
        return req.answer

    def checkpoint(self) -> None:
        """Raise :class:`Cancelled` if cancellation was requested. Call between
        units of work (e.g. per file / per chunk)."""
        if self._cancel.is_set():
            raise Cancelled()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    @property
    def needs_attention(self) -> bool:
        """A background task waiting on an answer only the user can give — a
        conflict prompt it raised while its dialog was off screen."""
        return self.background and not self._requests.empty()

    # --- control (main thread) -----------------------------------------------

    def request_cancel(self) -> None:
        """Ask the worker to stop. Sets the cooperative flag; a blocked
        :meth:`ask` wakes within :attr:`_WAIT_TICK` and unwinds."""
        self._cancel.set()

    def _next_request(self) -> Optional[_UiRequest]:
        try:
            return self._requests.get_nowait()
        except queue.Empty:
            return None


class _Job:
    """What the manager keeps for one running task: the dialog it shows when it
    is in the foreground, and how to finish it."""

    __slots__ = ("task", "panel", "dialog", "finished", "on_done", "z",
                 "queued_slot", "last_render")

    def __init__(self, task, panel, dialog, on_done, z):
        self.task = task
        self.panel = panel
        self.dialog = dialog
        self.finished = threading.Event()
        self.on_done = on_done
        self.z = z
        #: True for the job holding the background queue's one slot.
        self.queued_slot = False
        self.last_render = 0.0


class TaskManager:
    """Central registry + main-thread pump for :class:`Task` s. One per app.

    Holds every live task, shows each foreground task's :class:`ProgressDialog`,
    and services its UI bridge on the animation tick.

    A task can run in the **background** (#567): its dialog leaves the screen
    and the user goes on working. :meth:`detach` sends a running one there;
    ``submit(..., detached=True)`` starts one there, through a **serial
    queue** — background jobs compete for the same disk or connection, so one
    runs at a time and the rest wait their turn. :meth:`bring_forward` puts a
    job's dialog back, which is also how a background job's pending prompt
    gets answered: a prompt never opens on its own while the job is out of
    sight, it waits and the job is flagged (:attr:`Task.needs_attention`)."""

    #: How often a background job repaints, for the status bar's progress.
    _BACKGROUND_REPAINT_S = 0.25

    def __init__(self):
        self.tasks: list[Task] = []
        self._jobs: dict[int, _Job] = {}
        #: Background jobs waiting for the slot: ``(task, panel, run, on_done, z)``.
        self._queue: list[tuple] = []

    def active_tasks(self) -> list[Task]:
        return [t for t in self.tasks
                if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)]

    def has_active(self) -> bool:
        return any(t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
                   for t in self.tasks)

    def background_tasks(self) -> list[Task]:
        """Running background jobs first, then the queued ones in order."""
        running = [t for t in self.tasks
                   if t.background and t.status is TaskStatus.RUNNING]
        return running + [entry[0] for entry in self._queue]

    def queued_count(self) -> int:
        return len(self._queue)

    def submit(self, task: Task, panel: Any, *, run: Callable[[Task], dict],
               on_done: Optional[Callable[[dict], None]] = None,
               z: int = 70, background: bool = True,
               detached: bool = False) -> Task:
        """Run ``run(task)``. In background mode: show a :class:`ProgressDialog`,
        spawn the worker, and pump the bridge + repaint each frame, closing the
        dialog and calling ``on_done(result)`` on the main thread when it ends. In
        synchronous mode (tests): run inline, ``ask`` resolves to its headless
        default, no dialog, ``on_done`` fires immediately. A backend that cannot
        drive animation ticks gets the synchronous treatment too — with no tick
        there would be nothing to pump prompts, service Cancel, or close the
        dialog.

        ``detached`` starts the task in the background instead, with no dialog,
        through the serial queue: it waits while another background job holds
        the slot."""
        self.tasks.append(task)

        if not background:
            task._headless = True
            task.status = TaskStatus.RUNNING
            result = self._run_inline(task, run)
            self._finish(task)
            if on_done is not None:
                on_done(result)
            return task

        if detached:
            task.background = True
            if self._slot_taken():
                self._queue.append((task, panel, run, on_done, z))
                panel.render()
                return task
        self._start(task, panel, run, on_done, z, queued_slot=detached)
        return task

    def _slot_taken(self) -> bool:
        return any(job.queued_slot or job.task.background
                   for job in self._jobs.values())

    def _start(self, task: Task, panel: Any, run, on_done, z: int, *,
               queued_slot: bool) -> None:
        dialog = ProgressDialog(task, on_background=self.detach)
        job = _Job(task, panel, dialog, on_done, z)
        job.queued_slot = queued_slot
        if not task.background:
            dialog.show(panel, z=z)
        task.status = TaskStatus.RUNNING

        def worker() -> None:
            try:
                task.result = run(task)
            except BaseException as exc:  # noqa: BLE001 — recorded, surfaced on tick
                task.error = exc
            finally:
                job.finished.set()

        def tick() -> bool:
            return self._tick(job)

        # Register the tick before the worker exists: if this backend cannot
        # drive frame ticks, nothing would ever pump the prompt bridge, service
        # Cancel, or close the dialog — the worker would mutate the filesystem
        # behind a dialog that can never be dismissed. Fall back to running the
        # task inline (prompts resolve to their headless defaults), exactly as
        # the synchronous mode above does.
        if not panel.request_animation_ticks(tick):
            dialog.close()
            task._headless = True
            result = self._run_inline(task, run)
            self._finish(task)
            if on_done is not None:
                on_done(result)
            return

        self._jobs[task.id] = job
        threading.Thread(target=worker, name=f"xefm-task-{task.id}", daemon=True).start()

    def _tick(self, job: _Job) -> bool:
        """Main thread, each frame: service at most one pending prompt (only
        while the job is in the foreground), repaint, and on completion tear
        down and report the result."""
        task, panel, dialog = job.task, job.panel, job.dialog
        if not task.background:
            dialog.pump(panel)
        if not job.finished.is_set():
            if not task.background:
                panel.render()
            else:
                now = time.monotonic()
                if now - job.last_render >= self._BACKGROUND_REPAINT_S:
                    job.last_render = now
                    panel.render()
            return True
        # Teardown runs exactly once (the tick unregisters below), so it must
        # not be derailed: close first, and keep an on_done failure from
        # escaping into the backend's tick dispatch.
        dialog.close()
        self._jobs.pop(task.id, None)
        self._finish(task)
        if job.on_done is not None:
            try:
                job.on_done(task.result or _empty_result())
            except Exception as exc:  # noqa: BLE001 — logged, teardown completes
                logger.error(f"Task completion callback failed: {exc}")
        self._start_next()
        # One repaint so the closed dialog leaves the screen even when
        # on_done did not render (or was None / raised).
        panel.render()
        return False

    def _start_next(self) -> None:
        """Hand the background slot to the next queued job, if it is free."""
        if self._queue and not self._slot_taken():
            task, panel, run, on_done, z = self._queue.pop(0)
            if task.cancelled():
                self._finish(task)
                if on_done is not None:
                    on_done(dict(_empty_result(), cancelled=True))
                self._start_next()
                return
            self._start(task, panel, run, on_done, z, queued_slot=True)

    def cancel_all(self, timeout: float = 3.0) -> bool:
        """Cancel every task — the running ones and the queue — and wait up to
        ``timeout`` seconds for the running workers to unwind, so a half-written
        file is cleaned up before the process exits. True when all of them
        did. For quitting: nothing is reported, the app is going away."""
        for task, *_rest in self._queue:
            task.request_cancel()
        self._queue.clear()
        jobs = list(self._jobs.values())
        for job in jobs:
            job.task.request_cancel()
        deadline = time.monotonic() + timeout
        for job in jobs:
            if not job.finished.wait(max(0.0, deadline - time.monotonic())):
                return False
        return True

    def detach(self, task: Task) -> None:
        """Send a running foreground task to the background: its dialog
        leaves the screen and the task goes on."""
        job = self._jobs.get(task.id)
        if job is None or task.background:
            return
        job.dialog.close()
        task.background = True
        job.panel.render()

    def bring_forward(self, task: Task) -> bool:
        """Put a background task's dialog back on screen — where its pending
        prompt is answered and Esc can cancel it. A queued task that has not
        started is cancelled instead of shown: there is nothing to show yet,
        and the only thing to do with it is drop it. False when ``task`` is
        neither."""
        for i, entry in enumerate(self._queue):
            if entry[0] is task:
                self._queue.pop(i)
                task.request_cancel()
                self._finish(task)
                on_done = entry[3]
                if on_done is not None:
                    on_done(dict(_empty_result(), cancelled=True))
                entry[1].render()
                return True
        job = self._jobs.get(task.id)
        if job is None or not task.background:
            return False
        task.background = False
        job.dialog.show(job.panel, z=job.z)
        job.panel.render()
        return True

    @staticmethod
    def _run_inline(task: Task, run: Callable[[Task], dict]) -> dict:
        try:
            task.result = run(task)
        except BaseException as exc:  # noqa: BLE001
            task.error = exc
        return task.result or _empty_result()

    def _finish(self, task: Task) -> None:
        if task.error is not None:
            task.status = TaskStatus.FAILED
        elif task.cancelled() or (task.result or {}).get("cancelled"):
            task.status = TaskStatus.CANCELLED
        else:
            task.status = TaskStatus.DONE
        if task in self.tasks:
            self.tasks.remove(task)


def _empty_result() -> dict:
    return {"done": 0, "skipped": 0, "failed": 0, "cancelled": False}


def transfer_bytes_text(transfer: dict) -> str:
    """The right-hand column of one transfer row.

    Normally the file's byte counts, and nothing at all for a file too small
    for them to be worth the width. While the file is being *closed* it says so
    instead, with the seconds it has been at it.

    That last case is the one that earns this its own function. Where the
    destination holds a file in a local cache until it is closed — WebDAV, and
    NFS's close-to-open flush — the close is where the bytes actually travel,
    and the row would otherwise hold at its total for the whole of it: the
    operation's real work, shown as a number that had stopped moving. Nothing
    here is specific to such a destination, though. One whose close is instant
    passes through this in a single frame."""
    if transfer.get("closing_since") and not transfer.get("done"):
        waited = int(max(0.0, time.monotonic() - transfer["closing_since"]))
        return f"finishing… {waited}s" if waited else "finishing…"
    if transfer["total"] >= _BYTE_TEXT_MIN:
        return (f"{format_size(transfer['copied'], compact=True)}"
                f" / {format_size(transfer['total'], compact=True)}")
    return ""


class ProgressDialog(Widget):
    """Modal progress surface for a running :class:`Task`. Generic — it renders
    only from ``task.title`` + ``task.progress`` (the :class:`ProgressManager`), so
    any task type reuses it:

    - **Preparing** (``ProgressManager`` still ``counting``): a :class:`BusyIndicator`
      and a "Preparing…" line — an indeterminate phase with no total yet.
    - **Running**: a determinate primary :class:`ProgressBar` (weighted by items
      *and* bytes when the operation measured them), then either the current file
      name with a **secondary byte bar** (operations that work one file at a
      time — delete, archives), or — once the copy engine's per-file transfer
      slots report in — **one row per in-flight file**, each with its own byte
      counts, so a parallel copy shows every worker's file rather than whichever
      one most recently started.
    - **Cancelling** (derived from the cancel flag): a "Cancelling…" line until the
      worker unwinds.

    ``Esc`` opens a confirm box; confirming requests cancellation on the task. The
    dialog only *reads* progress state during ``draw`` — the worker mutates it."""

    focusable = True

    def __init__(self, task: Task,
                 on_background: Optional[Callable[[Task], None]] = None):
        self.task = task
        #: Sends the task to the background (:meth:`TaskManager.detach`);
        #: None hides the choice, for a dialog with no manager behind it.
        self._on_background = on_background
        self._panel: Any = None
        self._bar = ProgressBar()
        self._byte_bar = ProgressBar()
        self._busy = BusyIndicator(label="")
        #: True while a bridged prompt (conflict dialog) is on screen, so the pump
        #: shows one at a time and the worker's next request waits its turn.
        self._request_in_flight = False
        #: True while the cancel-confirm box is up, so Esc doesn't stack another.
        self._confirming_cancel = False
        #: The open cancel-confirm box itself, so close() can dismiss it along
        #: with the dialog — its question is moot once the task has ended.
        self._cancel_box: Any = None

    # --- lifecycle -----------------------------------------------------------

    def show(self, panel: Any, z: int = 70) -> None:
        self._panel = panel
        self._z = z
        sw, _sh = panel.backend.size_units
        w = float(max(44, min(70, int(sw) - 4)))
        # title + primary bar/label + either (current item + secondary bar/label)
        # or up to four per-file transfer rows. The rows are reserved whether or
        # not anything fills them: an operation alternates between files that
        # report bytes and files that don't, and a box that resized under each
        # one would jitter for its whole run. The height stays *even*: an odd box
        # centers onto a half cell, and the rounding then walks the foot-anchored
        # rows onto the bottom border.
        h = 10.0
        panel.push_layer(self, z=z, hints={"shadow": True, "w": w, "h": h})
        animate_open(panel, self, OPEN_MS_VIEWER)

    def close(self) -> None:
        """Remove this dialog's layer — and the cancel-confirm box, if one is
        still open above it. Removal is by identity, wherever each layer sits:
        the dialog is *not* necessarily topmost at teardown (the task can
        finish while the confirm box is covering it), and the old "pop only if
        topmost" guard then silently skipped the pop, stranding the dialog on
        screen with nothing left to ever close it (#333)."""
        panel = self._panel
        if panel is None:
            return
        if self._cancel_box is not None:
            panel.remove_layer(self._cancel_box)
            self._cancel_box = None
            self._confirming_cancel = False
        panel.remove_layer(self)

    # --- bridge pump (main thread) -------------------------------------------

    def pump(self, panel: Any) -> None:
        """Service at most one pending UI request from the worker: pop it and show
        its dialog. Only one runs at a time — the worker blocks on the answer
        before it can post the next, so conflicts prompt sequentially."""
        if self._request_in_flight:
            return
        req = self.task._next_request()
        if req is None:
            return
        self._request_in_flight = True

        def deliver(answer: Any) -> None:
            self._request_in_flight = False
            req.deliver(answer)

        req.show_fn(panel, deliver)

    # --- drawing -------------------------------------------------------------

    def draw(self, ctx) -> None:
        self._panel = ctx.panel
        theme = ctx.theme
        box_style = (Style(bg=theme.popup_bg, fg=theme.popup_border)
                     if theme is not None else DEFAULT_STYLE)
        surface_bg = theme.popup_bg if theme is not None else None
        box_w, box_h = ctx.size_units
        ctx.draw_box(0, 0, box_w, box_h, box_style, hints={"fill": True})
        text_style = Style(bg=surface_bg)
        ctx.draw_text(2, 0.5, self.task.title, Style(bg=surface_bg, attr=TextAttribute.BOLD))
        # The popup surface, handed to the child widgets (bars, spinner)
        # explicitly: their glyph runs name no background, and on a grid backend
        # an unbackgrounded cell falls to the *terminal default* rather than the
        # theme surface — a light theme showed dark strips through the dialog.
        child_hints = {"bg": surface_bg}

        op = self.task.progress.get_current_operation()
        width = max(1.0, box_w - 4)
        if op is None or op.get("counting"):
            self._draw_preparing(ctx, op, box_w, box_h, text_style, child_hints)
            return
        transfers = self.task.progress.get_transfers()
        if transfers:
            self._draw_transfers(ctx, op, transfers, box_h, width, text_style,
                                 child_hints)
            return
        if self.task.cancelled():
            ctx.draw_text(2, 2.2, "Cancelling…", text_style)

        # Current item above the bars, abbreviated the way the pane header is:
        # measured through the backend, so a wide CJK glyph and a proportional
        # GUI font each count for what they really take rather than for one
        # character, and cut in the middle, so the extension — the part that
        # says what the file *is* — survives a name too long to show whole.
        item = (op.get("current_item") or "") if not self.task.cancelled() else ""
        if item:
            ctx.draw_text(2, 2.2, abbreviate_path(item, width, measure=ctx.measure_text),
                          text_style)

        # Primary bar: items processed / total.
        self._bar.value = self.task.progress.get_progress_percentage() / 100.0
        ctx.draw_child(self._bar, 2, 3.4, width, 1.0, hints=child_hints)
        ctx.draw_text(2, 4.3, f"{op['processed_items']} / {op['total_items']} items", text_style)

        # Secondary bar: bytes of the current file (only when a total is known).
        # Placed by measuring up from the foot of the box — label on the last row
        # inside the frame, bar above it — rather than at absolute offsets. A
        # centered box can land on a half cell, and absolute offsets then round a
        # row further down: that is how the label came to be drawn *on* the border.
        bc, bt = op.get("file_bytes_copied", 0), op.get("file_bytes_total", 0)
        if bt > 0:
            label_y = box_h - 2.0
            self._byte_bar.value = min(1.0, bc / bt) if bt else 0.0
            ctx.draw_child(self._byte_bar, 2, label_y - 1.0, width, 1.0,
                           hints=child_hints)
            ctx.draw_text(
                2, label_y,
                f"{format_size(bc, compact=True)} / {format_size(bt, compact=True)}",
                text_style)

    def _draw_transfers(self, ctx, op, transfers, box_h, width, text_style,
                        child_hints) -> None:
        """The copy engine's layout: the primary bar (items and, when measured,
        bytes) directly under the title, then one row per transfer slot — each
        worker's current file with its own byte counts. Rows are keyed by slot,
        and a finished file holds its row until the worker's next file replaces
        it, so the lines stay put instead of blinking."""
        self._bar.value = self.task.progress.get_progress_percentage() / 100.0
        ctx.draw_child(self._bar, 2, 1.9, width, 1.0, hints=child_hints)
        label = f"{op['processed_items']} / {op['total_items']} items"
        if op.get("total_bytes"):
            label += (f" — {format_size(op['processed_bytes'], compact=True)}"
                      f" / {format_size(op['total_bytes'], compact=True)}")
        ctx.draw_text(2, 2.9, label, text_style)
        # The file rows are anchored up from the foot of the box (the same
        # proven-safe rule as the single-file byte label), which leaves a blank
        # line under the summary — the operation total and the per-file section
        # read as two parts on the grid backends as well as the vector ones.
        foot = box_h - 2.0
        first_row = foot - (_TRANSFER_ROWS - 1) * 0.9
        if self.task.cancelled():
            ctx.draw_text(2, first_row, "Cancelling…", text_style)
            return
        rows = transfers
        extra = len(rows) - _TRANSFER_ROWS
        if extra > 0:
            rows = rows[:_TRANSFER_ROWS - 1]
        for i, (_slot, t) in enumerate(rows):
            y = first_row + i * 0.9
            bytes_text = transfer_bytes_text(t)
            bytes_w = ctx.measure_text(bytes_text) if bytes_text else 0.0
            name_w = max(1.0, width - (bytes_w + 2.0 if bytes_text else 0.0))
            ctx.draw_text(2, y, abbreviate_path(t["item"], name_w,
                                                measure=ctx.measure_text),
                          text_style)
            if bytes_text:
                ctx.draw_text(2 + width - bytes_w, y, bytes_text, text_style)
        if extra > 0:
            ctx.draw_text(2, foot, f"… {extra + 1} more files", text_style)

    def _draw_preparing(self, ctx, op, box_w, box_h, text_style,
                        child_hints) -> None:
        ctx.draw_child(self._busy, 2, 3.0, 2.0, 1.0, hints=child_hints)
        n = self.task.counted
        busy = self.task.busy_label
        label = f"{busy} ({n} item{'s' if n != 1 else ''})" if n else busy
        ctx.draw_text(4, 3.0, label, text_style)

    # --- events --------------------------------------------------------------

    def handle_event(self, event: Event) -> bool:
        if event.type is EventType.KEY and event.key == "escape":
            self._confirm_cancel()
        elif (event.type is EventType.KEY and event.key == "b"
              and not event.modifiers and self._on_background is not None
              and not self.task.cancelled()):
            self._on_background(self.task)
        return True  # modal: swallow everything else

    def _confirm_cancel(self) -> None:
        """Esc: pop a confirm box (above this dialog); on Yes, request cancel. The
        worker keeps running while the user decides — cancel only takes effect if
        confirmed."""
        if self._confirming_cancel or self.task.cancelled() or self._panel is None:
            return
        self._confirming_cancel = True

        def on_result(label: str) -> None:
            self._confirming_cancel = False
            self._cancel_box = None
            if label == "Cancel operation":
                self.task.request_cancel()
            elif label == "Run in background" and self._on_background is not None:
                self._on_background(self.task)
            if self._panel is not None:
                self._panel.render()

        # The operation keeps running while this is asked. Background is the
        # first choice, not the default: Enter and Esc both keep it running in
        # front, so a stray key changes nothing.
        buttons = (("Run in background",) if self._on_background is not None
                   else ()) + ("Cancel operation", "Keep running")
        self._cancel_box = show_message_box(
            self._panel, f"Stop waiting for {self.task.title.rstrip('… ')}?",
            title="Running", icon="warning", buttons=buttons,
            default=len(buttons) - 1, cancel=len(buttons) - 1,
            on_result=on_result, z=getattr(self, "_z", 70) + 5)
