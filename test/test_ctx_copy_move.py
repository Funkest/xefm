"""``ctx.copy`` / ``ctx.move`` — file operations from an action (#716).

They run the engine C / M run (confirmation, conflict dialog, job queue,
progress) on items and a destination the action chose, and report through
``on_done(ctx, outcome)``: on the UI thread, once the operation is over, never
before the call returns, with a list of ``ItemResult`` as the value.

A headless XeFMApp on the memory backend over a real temp tree; the operation
runs for real, driven by animation ticks and the app's pump.

Run with: python -m pytest test/test_ctx_copy_move.py -v
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from xefm import app as xefm_app  # noqa: E402
from xefm import file_operations  # noqa: E402
from xefm.file_operations import FileOperationService  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.user_api import ActionContext, ItemResult  # noqa: E402


class CtxCopyMove(unittest.TestCase):

    def setUp(self):
        from xefm.state_manager import XeFMStateManager
        from puikit.backends import create_backend
        # realpath: macOS /var is a symlink to /private/var (xefm#505).
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.cfgdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        self.dest = os.path.join(self.tmp, "dest")
        for d in (self.src, self.dest):
            os.mkdir(d)
        for name in ("a.txt", "b.txt"):
            with open(os.path.join(self.src, name), "w") as f:
                f.write(name)
        self.sm = XeFMStateManager(db_path=os.path.join(self.cfgdir, "state.db"))
        self.backend = create_backend("memory")
        self.backend.open()
        self.app = xefm_app.XeFMApp(self.backend, self.src, self.dest,
                                    left_provided=True, right_provided=True,
                                    state_manager=self.sm)
        self.app._settle_listings()
        # No confirmation, so the operation starts on the call; the tests that
        # are about the confirmation turn it back on.
        for flag in ("CONFIRM_COPY", "CONFIRM_MOVE"):
            patcher = mock.patch.object(self.app.config, flag, False, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.outcomes = []

    def tearDown(self):
        try:
            self.app.file_monitor.stop_monitoring()
            self.backend.close()
            self.sm.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.cfgdir, ignore_errors=True)

    def ctx(self):
        return ActionContext(self.app)

    def on_done(self, ctx, outcome):
        self.assertIsInstance(ctx, ActionContext)
        self.outcomes.append(outcome)

    def settle(self, timeout=10.0):
        """Drive ticks and the pump until ``on_done`` has run."""
        deadline = time.monotonic() + timeout
        while not self.outcomes and time.monotonic() < deadline:
            self.backend.run_animation_ticks()
            self.app._pump_monitoring()
            time.sleep(0.01)
        self.assertEqual(len(self.outcomes), 1, "on_done did not run once")
        return self.outcomes[0]

    def path(self, *parts):
        return os.path.join(self.tmp, *parts)

    # --- the operation ------------------------------------------------------

    def test_copy_reports_each_item_in_order(self):
        entries = sorted(self.ctx().pane.entries, key=lambda e: e.name)
        self.ctx().copy(entries, self.dest, on_done=self.on_done)
        self.assertEqual(self.outcomes, [], "on_done ran before copy returned")
        outcome = self.settle()
        self.assertEqual(outcome.status, "done")
        self.assertEqual([r.status for r in outcome.value], ["done", "done"])
        self.assertEqual([r.source.name for r in outcome.value], ["a.txt", "b.txt"])
        self.assertTrue(all(isinstance(r, ItemResult) for r in outcome.value))
        self.assertEqual(str(outcome.value[0].dest), self.path("dest", "a.txt"))
        self.assertTrue(os.path.exists(self.path("dest", "a.txt")))
        self.assertTrue(os.path.exists(self.path("src", "a.txt")))

    def test_move_takes_paths_and_strings(self):
        self.ctx().move([Path(self.path("src", "a.txt")), self.path("src", "b.txt")],
                        Path(self.dest), on_done=self.on_done)
        outcome = self.settle()
        self.assertEqual(outcome.status, "done")
        self.assertFalse(os.path.exists(self.path("src", "a.txt")))
        self.assertTrue(os.path.exists(self.path("dest", "b.txt")))

    def test_dest_is_created_when_missing(self):
        new = self.path("new", "deeper")
        self.ctx().copy([self.path("src", "a.txt")], new, on_done=self.on_done)
        self.assertEqual(self.settle().status, "done")
        self.assertTrue(os.path.exists(os.path.join(new, "a.txt")))

    def test_an_empty_list_is_done_with_nothing(self):
        self.ctx().copy([], self.dest, on_done=self.on_done)
        self.assertEqual(self.outcomes, [])
        outcome = self.settle()
        self.assertEqual((outcome.status, outcome.value), ("done", []))

    def test_no_on_done_is_fine(self):
        self.ctx().copy([self.path("src", "a.txt")], self.dest)
        deadline = time.monotonic() + 10
        while (not os.path.exists(self.path("dest", "a.txt"))
               and time.monotonic() < deadline):
            self.backend.run_animation_ticks()
            self.app._pump_monitoring()
            time.sleep(0.01)
        self.assertTrue(os.path.exists(self.path("dest", "a.txt")))

    # --- cancel and failure -------------------------------------------------

    def test_cancel_at_the_confirmation_is_cancelled(self):
        def answer_cancel(panel, message, *, buttons, on_result, **kw):
            on_result(buttons[-1])

        with mock.patch.object(self.app.config, "CONFIRM_COPY", True), \
                mock.patch.object(file_operations, "show_message_box", answer_cancel):
            self.ctx().copy([self.path("src", "a.txt")], self.dest,
                            on_done=self.on_done)
            self.assertEqual(self.outcomes, [])
            outcome = self.settle()
        self.assertEqual((outcome.status, outcome.value), ("cancelled", []))
        self.assertFalse(os.path.exists(self.path("dest", "a.txt")))

    def test_a_broken_operation_is_failed(self):
        def boom(*args, **kwargs):
            raise OSError("disk on fire")

        with mock.patch.object(FileOperationService, "_run", boom):
            self.ctx().copy([self.path("src", "a.txt")], self.dest,
                            on_done=self.on_done)
            outcome = self.settle()
        self.assertEqual(outcome.status, "failed")
        self.assertIsInstance(outcome.error, OSError)

    # --- arguments ----------------------------------------------------------

    def test_a_relative_string_is_an_error(self):
        with self.assertRaises(ValueError):
            self.ctx().copy(["a.txt"], self.dest)
        with self.assertRaises(ValueError):
            self.ctx().copy([self.path("src", "a.txt")], "dest")

    def test_an_item_already_in_dest_is_an_error(self):
        with self.assertRaises(ValueError):
            self.ctx().copy([self.path("src", "a.txt")], self.src)

    def test_an_archive_dest_is_an_error(self):
        with self.assertRaises(ValueError):
            self.ctx().copy([self.path("src", "a.txt")], "archive:///x.zip/inner")

    def test_moving_out_of_an_archive_is_an_error(self):
        with self.assertRaises(ValueError):
            self.ctx().move(["archive:///x.zip/a.txt"], self.dest)

    def test_off_the_ui_thread_is_an_error(self):
        errors = []

        def worker():
            try:
                self.ctx().copy([self.path("src", "a.txt")], self.dest)
            except RuntimeError as exc:
                errors.append(exc)

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        self.assertEqual(len(errors), 1)


class ServiceTargets(unittest.TestCase):
    """The engine's per-target record behind ``ItemResult``, run inline
    (``background=False``), where a conflict resolves to its headless default:
    skip."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.src = os.path.join(self.tmp, "src")
        self.dest = os.path.join(self.tmp, "dest")
        os.mkdir(self.src)
        os.mkdir(self.dest)
        for name in ("a.txt", "b.txt", "c.txt"):
            with open(os.path.join(self.src, name), "w") as f:
                f.write(name)
        with open(os.path.join(self.dest, "b.txt"), "w") as f:
            f.write("already here")
        config = mock.Mock(CONFIRM_COPY=False, CONFIRM_MOVE=False)
        from xefm.task import TaskManager
        self.service = FileOperationService(config, TaskManager())

    def run_copy(self, names):
        results = []
        self.service.copy(mock.Mock(), [Path(os.path.join(self.src, n)) for n in names],
                          Path(self.dest), on_complete=results.append,
                          background=False)
        return results[0]

    def test_each_target_in_the_given_order(self):
        result = self.run_copy(["c.txt", "b.txt", "a.txt"])
        self.assertEqual([(t.name, status) for t, _d, status, _e in result["targets"]],
                         [("c.txt", "done"), ("b.txt", "skipped"), ("a.txt", "done")])

    def test_a_failed_target_carries_its_errors(self):
        os.remove(os.path.join(self.src, "a.txt"))  # gone before the copy runs
        result = self.run_copy(["a.txt"])
        (_t, _d, status, errors), = result["targets"]
        self.assertEqual(status, "failed")
        self.assertTrue(errors)
