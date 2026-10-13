"""Background file operations (#567): detach, queue, and pause on a prompt.

Driven on the memory backend, which runs animation ticks on request — the
TaskManager's pump. A task's body waits on an Event the test releases, so
"still running" is a state the test holds rather than a race it hopes to win.

Run with: python -m pytest test/test_background_jobs.py -v
"""

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from puikit import Event, EventType, Panel, PROFILE_TUI  # noqa: E402
from puikit.backends.memory_backend import MemoryBackend  # noqa: E402

from xefm import _config  # noqa: E402
from xefm.file_operations import FileOperationService  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.task import ProgressDialog, Task, TaskManager, TaskStatus  # noqa: E402


@pytest.fixture
def panel():
    return Panel(MemoryBackend(width=100, height=30, capabilities=PROFILE_TUI))


def _key(name, char=None):
    return Event(type=EventType.KEY, key=name, char=char)


def _pump(panel, until, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        panel.backend.run_animation_ticks()
        time.sleep(0.01)
    panel.backend.run_animation_ticks()
    assert until(), "condition never held"


def _held_task(manager, panel, *, detached=False, title="Copy…"):
    """Submit a task whose body runs until ``release`` is set."""
    release = threading.Event()
    done = []
    task = Task(title)

    def run(t):
        while not release.wait(0.01):
            t.checkpoint()
        return {"done": 1}

    manager.submit(task, panel, run=run, on_done=done.append, detached=detached)
    return task, release, done


def _dialogs(panel):
    return [layer.widget for layer in panel._layers
            if isinstance(layer.widget, ProgressDialog)]


def test_detach_takes_the_dialog_away_and_the_task_goes_on(panel):
    manager = TaskManager()
    task, release, done = _held_task(manager, panel)
    assert len(_dialogs(panel)) == 1
    manager.detach(task)
    assert task.background
    assert _dialogs(panel) == []
    assert manager.background_tasks() == [task]
    release.set()
    _pump(panel, lambda: done)
    assert done == [{"done": 1}]
    assert manager.background_tasks() == []


def test_detached_jobs_run_one_at_a_time_in_order(panel):
    manager = TaskManager()
    first, release1, done1 = _held_task(manager, panel, detached=True, title="One…")
    second, release2, done2 = _held_task(manager, panel, detached=True, title="Two…")
    assert _dialogs(panel) == []
    assert first.status is TaskStatus.RUNNING
    assert second.status is TaskStatus.PENDING
    assert manager.queued_count() == 1
    release2.set()       # the second may finish at once, but has not started
    release1.set()
    _pump(panel, lambda: done1 and done2)
    assert manager.queued_count() == 0


def test_a_foreground_task_does_not_wait_for_the_queue(panel):
    manager = TaskManager()
    _bg, release1, _ = _held_task(manager, panel, detached=True)
    fg, release2, done2 = _held_task(manager, panel)
    assert fg.status is TaskStatus.RUNNING
    release2.set()
    _pump(panel, lambda: done2)
    release1.set()


def test_a_background_prompt_waits_until_brought_forward(panel):
    manager = TaskManager()
    shown = []
    done = []
    task = Task("Copy…")

    def show(panel_, deliver):
        shown.append(deliver)

    def run(t):
        return {"answer": t.ask(show, headless=None)}

    started = threading.Event()

    def run_after_detach(t):
        started.wait(2)
        return run(t)

    manager.submit(task, panel, run=run_after_detach, on_done=done.append)
    manager.detach(task)
    started.set()
    _pump(panel, lambda: task.needs_attention)
    for _ in range(5):
        panel.backend.run_animation_ticks()
    assert shown == []                 # nothing opened behind the user's back
    assert manager.bring_forward(task)
    assert not task.background
    _pump(panel, lambda: shown)
    shown[0]("overwrite")
    _pump(panel, lambda: done)
    assert done == [{"answer": "overwrite"}]


def test_bringing_forward_a_queued_job_drops_it(panel):
    manager = TaskManager()
    _first, release1, _ = _held_task(manager, panel, detached=True)
    second, _release2, done2 = _held_task(manager, panel, detached=True)
    assert manager.bring_forward(second)
    assert done2 and done2[0]["cancelled"]
    assert manager.queued_count() == 0
    release1.set()


def test_the_progress_dialog_has_buttons_for_both(panel):
    """No hidden key (#599): the dialog says what it can do."""
    manager = TaskManager()
    _task, release, done = _held_task(manager, panel)
    panel.render()
    screen = "\n".join(panel.backend.snapshot())
    assert "Run in background" in screen
    assert "Cancel" in screen
    release.set()
    _pump(panel, lambda: done)


def test_the_background_button_sends_it_there(panel):
    manager = TaskManager()
    task, release, done = _held_task(manager, panel)
    panel.dispatch_event(_key("enter"))        # focus starts on Run in background
    assert task.background
    assert _dialogs(panel) == []
    release.set()
    _pump(panel, lambda: done)


def test_b_is_no_longer_a_key(panel):
    manager = TaskManager()
    task, release, done = _held_task(manager, panel)
    panel.dispatch_event(_key("b", "b"))
    assert not task.background
    release.set()
    _pump(panel, lambda: done)


def test_the_cancel_button_asks_and_keeps_running_by_default(panel):
    manager = TaskManager()
    task, release, done = _held_task(manager, panel)
    panel.dispatch_event(_key("tab"))          # → Cancel
    panel.dispatch_event(_key("enter"))
    panel.render()
    screen = "\n".join(panel.backend.snapshot())
    assert "Cancel operation" in screen
    panel.dispatch_event(_key("enter"))        # default: Keep running
    assert not task.background and not task.cancelled()
    panel.dispatch_event(_key("escape"))       # Esc asks the same
    panel.dispatch_event(_key("left"))         # Keep running → Cancel operation
    panel.dispatch_event(_key("enter"))
    assert task.cancelled()
    release.set()
    _pump(panel, lambda: done)


# --- one at a time, really (#599) ---------------------------------------------

def test_a_job_sent_back_waits_its_turn_suspended(panel):
    """Sent to the background while another job runs there, a job stops at its
    next file boundary and joins the queue, so only one background job runs."""
    manager = TaskManager()
    first, release1, done1 = _held_task(manager, panel, detached=True, title="One…")
    second, release2, done2 = _held_task(manager, panel, title="Two…")
    assert not second.paused
    manager.detach(second)
    assert second.suspended
    assert manager.queued_count() == 1
    assert manager.running_task() is first
    _pump(panel, lambda: second.paused)        # held at its checkpoint
    release2.set()
    for _ in range(10):
        panel.backend.run_animation_ticks()
        time.sleep(0.01)
    assert not done2, "a suspended job does not finish behind the running one"
    release1.set()
    _pump(panel, lambda: done1 and done2)
    assert manager.background_tasks() == []


def test_a_job_sent_back_to_a_free_slot_keeps_running(panel):
    manager = TaskManager()
    task, release, done = _held_task(manager, panel)
    manager.detach(task)
    assert not task.suspended
    assert manager.running_task() is task
    assert manager.queued_count() == 0
    release.set()
    _pump(panel, lambda: done)


def test_bringing_forward_a_suspended_job_runs_it_in_front(panel):
    manager = TaskManager()
    _first, release1, _ = _held_task(manager, panel, detached=True)
    second, release2, done2 = _held_task(manager, panel)
    manager.detach(second)
    _pump(panel, lambda: second.paused)
    assert manager.bring_forward(second)
    assert not second.suspended and not second.background
    assert manager.queued_count() == 0
    assert len(_dialogs(panel)) == 1
    release2.set()
    _pump(panel, lambda: done2)
    release1.set()


def test_a_suspended_job_can_be_cancelled(panel):
    manager = TaskManager()
    _first, release1, _ = _held_task(manager, panel, detached=True)
    second, _release2, done2 = _held_task(manager, panel)
    manager.detach(second)
    _pump(panel, lambda: second.paused)
    second.request_cancel()
    _pump(panel, lambda: done2)
    assert manager.queued_count() == 0
    release1.set()


def test_a_transfer_never_pauses_mid_file():
    task = Task("Copy…")
    task.suspend()
    started = time.monotonic()
    task.checkpoint(pausable=False)            # returns at once
    assert time.monotonic() - started < 0.5
    assert not task.paused


def test_the_copy_confirmation_starts_it_in_the_background(panel, tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "a.txt").write_text("a")
    service = FileOperationService(_config.Config())
    done = []
    service.copy(panel, [Path(str(src / "a.txt"))], Path(str(dst)),
                 on_complete=done.append)
    panel.render()
    assert "Background" in "\n".join(panel.backend.snapshot())
    panel.dispatch_event(_key("right"))      # Copy → Background
    panel.dispatch_event(_key("enter"))
    assert _dialogs(panel) == []
    _pump(panel, lambda: done)
    assert (dst / "a.txt").read_text() == "a"


def test_the_delete_confirmation_still_defaults_to_cancel(panel, tmp_path):
    victim = tmp_path / "v.txt"
    victim.write_text("x")
    service = FileOperationService(_config.Config())
    service.delete(panel, [Path(str(victim))])
    panel.dispatch_event(_key("enter"))
    assert victim.exists()
    assert manager_idle(service)


def manager_idle(service):
    return not service.tasks.has_active()


# --------------------------------------------------------------------------- #
# the app: the status bar and quitting
# --------------------------------------------------------------------------- #

@pytest.fixture
def app(tmp_path):
    from puikit.backends import create_backend
    from xefm import app as xefm_app
    from xefm.state_manager import XeFMStateManager
    root = os.path.realpath(str(tmp_path))
    backend = create_backend("memory")
    backend.open()
    a = xefm_app.XeFMApp(backend, root, root, left_provided=True,
                         right_provided=True,
                         state_manager=XeFMStateManager(
                             db_path=os.path.join(root, "state.db")))
    a.file_monitor.stop_monitoring()
    a.file_monitor.enabled = False
    a._settle_listings()
    yield a
    for t in a.tasks.active_tasks():
        t.request_cancel()
    backend.close()


def test_the_status_bar_names_the_running_job(app):
    task, release, done = _held_task(app.tasks, app.panel, detached=True)
    _second, release2, _ = _held_task(app.tasks, app.panel, detached=True)
    text = app._jobs_text()
    assert text.startswith("⟳ Copy")
    assert "+1 queued" in text
    third, release3, _ = _held_task(app.tasks, app.panel)
    app.tasks.detach(third)                    # sent back: suspended, queued
    assert "+2 queued" in app._jobs_text()
    release3.set()
    assert "Ctrl-G" in text or "Ctrl+G" in text or "⌃G" in text
    release.set()
    release2.set()


def test_quitting_with_jobs_asks_and_defaults_to_cancel(app):
    _task, release, _ = _held_task(app.tasks, app.panel, detached=True)
    quit_called = []
    app._quit = lambda: quit_called.append(True)
    app.confirm_quit()
    app.panel.render()
    assert "still running" in "\n".join(app.backend.snapshot())
    app.panel.dispatch_event(_key("enter"))
    assert quit_called == []
    release.set()


def test_cancel_all_waits_for_the_workers_to_unwind(panel):
    manager = TaskManager()
    running, _r1, done1 = _held_task(manager, panel, detached=True)
    queued, _r2, _done2 = _held_task(manager, panel, detached=True)
    assert manager.cancel_all(timeout=2.0)
    assert running.cancelled() and queued.cancelled()
    assert manager.queued_count() == 0


# --- what the jobs list says (#599) -------------------------------------------

def test_describe_operation_names_what_and_where(tmp_path):
    from xefm.file_operations import describe_operation
    src = Path(str(tmp_path / "photos"))
    dst = Path("s3://bucket/backup")
    one = [Path(str(tmp_path / "photos" / "a.jpg"))]
    many = one + [Path(str(tmp_path / "photos" / "b.jpg"))]
    assert describe_operation("copy", one, dst) == f"a.jpg  {src} → s3://bucket/backup"
    assert describe_operation("move", many, dst).startswith("2 items  ")
    assert describe_operation("delete", many, None) == f"2 items in {src}"


def test_the_jobs_list_shows_detail_and_state(app):
    from unittest.mock import patch
    from xefm import app as xefm_app
    first, release1, _ = _held_task(app.tasks, app.panel, detached=True)
    first.detail = "a.jpg  ~/photos → s3://bucket"
    second, release2, _ = _held_task(app.tasks, app.panel)
    app.tasks.detach(second)
    third, release3, _ = _held_task(app.tasks, app.panel, detached=True)
    rows = []
    with patch.object(xefm_app, "show_choice_dialog",
                      lambda panel, title, items, **k: rows.extend(items)):
        app.show_jobs()
    labels = [label for _value, label in rows]
    assert labels[0].startswith("Copy a.jpg  ~/photos → s3://bucket — ")
    assert labels[1].endswith("paused, queued (Enter runs it now)")
    assert labels[2].endswith("queued (Enter removes it)")
    for release in (release1, release2, release3):
        release.set()
