"""The other pane follows a delete, trash or duplicate on its directory.

While an operation runs, the watcher of every directory it changes is
silenced and its events are dropped (issue #243): the operation's completion
handler is what brings the panes up to date. Copy and move re-list every pane
showing the destination; delete, trash and duplicate re-listed only the pane
they ran in, so with both panes on one directory the other pane kept the
deleted entries (or lacked the copy) until it was refreshed by hand
(issue #758).

Run with: python -m pytest test/test_other_pane_after_file_ops.py -v
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from xefm import app as xefm_app  # noqa: E402
from xefm.path import Path  # noqa: E402


class OtherPaneTestBase(unittest.TestCase):
    """A headless XeFMApp on the memory backend, both panes on one temp
    directory (the right one on another when ``SAME_DIRECTORY`` is False)."""

    #: Created in the left pane's directory during setUp, in sort order.
    FILES = ("a.txt", "b.txt", "c.txt")
    SAME_DIRECTORY = True

    def setUp(self):
        from xefm.state_manager import XeFMStateManager
        from puikit.backends import create_backend
        self.tmp = tempfile.mkdtemp()
        self.elsewhere = tempfile.mkdtemp()
        self.cfgdir = tempfile.mkdtemp()
        for name in self.FILES:
            open(os.path.join(self.tmp, name), "w").close()
        self.sm = XeFMStateManager(db_path=os.path.join(self.cfgdir, "state.db"))
        self.backend = create_backend("memory")
        self.backend.open()
        right = self.tmp if self.SAME_DIRECTORY else self.elsewhere
        self.app = xefm_app.XeFMApp(self.backend, self.tmp, right,
                                    left_provided=True, right_provided=True,
                                    state_manager=self.sm)
        self.app._settle_listings()
        # Delete and duplicate without the confirm dialog, and on this thread,
        # so the whole operation is done by the time the action returns.
        self.app.config.CONFIRM_DELETE = False
        self.app.config.CONFIRM_DUPLICATE = False
        real_delete = self.app._fileops.delete
        self.app._fileops.delete = (
            lambda panel, targets, **kw: real_delete(panel, targets,
                                                     background=False, **kw))
        real_duplicate = self.app._fileops.duplicate
        self.app._fileops.duplicate = (
            lambda panel, targets, dest_dir, **kw: real_duplicate(
                panel, targets, dest_dir, background=False, **kw))
        # The trash itself is the system's; what these tests are about is the
        # completion handler, which the trash shares with the delete.
        self.app._fileops.trash = (
            lambda panel, targets, **kw: self.app._fileops.delete(panel, targets, **kw))

    def tearDown(self):
        try:
            self.app.file_monitor.stop_monitoring()
        except Exception:
            pass
        try:
            self.backend.close()
            if hasattr(self.sm, "close"):
                self.sm.close()
        except Exception:
            pass
        for d in (self.tmp, self.elsewhere, self.cfgdir):
            shutil.rmtree(d, ignore_errors=True)

    # --- helpers -------------------------------------------------------------

    def pane(self):
        return self.app.active_pane()

    def other_pane(self):
        return self.app.pm.get_inactive_pane()

    def names(self, pane=None):
        return [f.name for f in (pane or self.pane())["files"]]

    def focus_on(self, name):
        self.pane()["focused_index"] = self.names().index(name)

    def delete(self):
        self.app.delete_permanently()
        self.app._settle_listings()


class DeleteReachesTheOtherPane(OtherPaneTestBase):
    def test_a_delete_leaves_the_other_pane_without_the_file(self):
        self.focus_on("b.txt")

        self.delete()

        self.assertEqual(self.names(), ["a.txt", "c.txt"])
        self.assertEqual(self.names(self.other_pane()), ["a.txt", "c.txt"])

    def test_a_trash_leaves_the_other_pane_without_the_file(self):
        self.focus_on("b.txt")

        with mock.patch.object(xefm_app.trash, "available", return_value=True):
            self.app.delete_files()
        self.app._settle_listings()

        self.assertEqual(self.names(self.other_pane()), ["a.txt", "c.txt"])

    def test_the_other_pane_keeps_its_cursor_file(self):
        other = self.other_pane()
        other["focused_index"] = self.names(other).index("c.txt")
        self.focus_on("a.txt")

        self.delete()

        self.assertEqual(other["files"][other["focused_index"]].name, "c.txt")


class APaneElsewhereIsLeftAlone(OtherPaneTestBase):
    SAME_DIRECTORY = False

    def test_a_delete_re_lists_only_the_pane_it_ran_in(self):
        self.focus_on("b.txt")

        with mock.patch.object(self.app, "_relist", wraps=self.app._relist) as relist:
            self.delete()

        self.assertEqual([c.args[0] for c in relist.call_args_list], [self.pane()])


class AVirtualOtherPaneIsASnapshot(OtherPaneTestBase):
    """A search-results / imported-list / flat-view pane follows what is done
    in it and Reread, not an operation in the other pane — even one that
    removes rows it shows."""

    def test_a_delete_does_not_re_list_a_flat_view_of_the_directory(self):
        self.app.pm.switch_pane()
        self.app.dispatch("flat_view")
        deadline = time.monotonic() + 10
        while self.app.tasks.has_active() and time.monotonic() < deadline:
            self.backend.run_animation_ticks()
            time.sleep(0.01)
        self.backend.run_animation_ticks()
        self.app._settle_listings()
        self.app.pm.switch_pane()
        other = self.other_pane()
        self.assertIsNotNone(other["virtual"])
        self.focus_on("b.txt")

        with mock.patch.object(self.app, "_relist", wraps=self.app._relist) as relist:
            self.delete()

        self.assertEqual([c.args[0] for c in relist.call_args_list], [self.pane()])
        self.assertIn("b.txt", self.names(other))


class MoveTestBase(OtherPaneTestBase):
    """A move that runs on this thread, without the confirm dialog."""

    def setUp(self):
        super().setUp()
        self.app.config.CONFIRM_MOVE = False
        real_move = self.app._fileops.move
        self.app._fileops.move = (
            lambda panel, targets, dest_dir, **kw: real_move(
                panel, targets, dest_dir, background=False, **kw))

    def move_focused_to(self, dest):
        self.app._run_transfer("move", self.pane(),
                               self.app._selected_or_focused(self.pane()), Path(dest))
        self.app._settle_listings()


class MoveReachesTheOtherPane(MoveTestBase):
    """Move re-lists the panes on the destination and the ones on a source
    directory too — the other pane, when a typed destination (Shift-M) took the
    files from the directory both panes show."""

    def test_a_move_elsewhere_leaves_the_other_pane_without_the_file(self):
        self.focus_on("b.txt")

        self.move_focused_to(self.elsewhere)

        self.assertEqual(self.names(), ["a.txt", "c.txt"])
        self.assertEqual(self.names(self.other_pane()), ["a.txt", "c.txt"])
        self.assertTrue(os.path.exists(os.path.join(self.elsewhere, "b.txt")))


class MoveIntoTheOtherPane(MoveTestBase):
    SAME_DIRECTORY = False

    def test_the_other_pane_on_the_destination_shows_the_file(self):
        self.focus_on("b.txt")

        self.move_focused_to(self.other_pane()["path"])

        self.assertEqual(self.names(), ["a.txt", "c.txt"])
        self.assertEqual(self.names(self.other_pane()), ["b.txt"])


class DuplicateReachesTheOtherPane(OtherPaneTestBase):
    def test_the_other_pane_shows_the_copy(self):
        self.focus_on("a.txt")

        self.app.duplicate_files()
        self.app._settle_listings()

        self.assertIn("a (1).txt", self.names())
        self.assertIn("a (1).txt", self.names(self.other_pane()))


if __name__ == "__main__":
    unittest.main()
