"""Flat view: every file below a directory as one flat list (#547).

Driven headless on the ``memory`` backend, as ``test_path_list.py`` drives the
clipboard import: flat view enters the same virtual pane, so what is under
test here is the walk — what it lists, what it skips, what it descends — and
the way in and out.

Run with: python -m pytest test/test_flat_view.py -v
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from xefm import app as xefm_app  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402


class FlatView(unittest.TestCase):

    def setUp(self):
        from puikit.backends import create_backend
        # Real path: macOS's temp dir sits behind the /var -> /private/var
        # symlink, and the app resolves its start directory.
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.state_dir = tempfile.mkdtemp()
        self.sm = XeFMStateManager(db_path=os.path.join(self.state_dir, "state.db"))
        self.b = create_backend("memory")
        self.b.open()
        self.app = xefm_app.XeFMApp(self.b, self.tmp, self.tmp,
                                    left_provided=True, right_provided=True,
                                    state_manager=self.sm)
        self.app.file_monitor.stop_monitoring()
        self.app.file_monitor.enabled = False
        self.app.flm.show_hidden = False
        self.pane = self.app.active_pane()

    def tearDown(self):
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def _write(self, rel):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write("x")
        return p

    def _list(self):
        self.app._relist(self.pane)
        self.app._settle_listings()

    def _flat(self):
        self.assertTrue(self.app.dispatch("flat_view"))
        # The walk runs on a task, on a worker where the backend drives frame
        # ticks: wait for it to hand over, then for the listing it starts.
        deadline = time.monotonic() + 10
        while self.app.tasks.has_active() and time.monotonic() < deadline:
            self.b.run_animation_ticks()
            time.sleep(0.01)
        self.b.run_animation_ticks()
        self.app._settle_listings()

    def _shown(self):
        view = self.app._active_view()
        return sorted(view._display_name(f) for f in self.pane["files"])

    def _last_log(self):
        text, _style = self.app.log.lines[-1]
        return text

    def _select(self, *names):
        for f in self.pane["files"]:
            if f.name in names:
                self.pane["selected_files"].add(str(f))

    def test_every_file_below_named_relative_to_the_directory(self):
        self._write("top.txt")
        self._write(os.path.join("a", "one.txt"))
        self._write(os.path.join("a", "b", "two.txt"))
        os.makedirs(os.path.join(self.tmp, "empty"))
        self._list()
        self._flat()
        virtual = self.pane["virtual"]
        self.assertEqual(virtual["kind"], "flat")
        self.assertEqual(str(virtual["root"]), str(Path(self.tmp)))
        # Files only: no row for a, a/b or the empty directory.
        self.assertEqual(self._shown(), sorted([
            "top.txt", os.path.join("a", "one.txt"),
            os.path.join("a", "b", "two.txt")]))
        self.assertIn("3 files below", self._last_log())

    def test_hidden_entries_follow_the_pane(self):
        self._write("seen.txt")
        self._write(".dot")
        self._write(os.path.join(".hidden", "inside.txt"))
        self._list()
        self._flat()
        self.assertEqual(self._shown(), ["seen.txt"])

        self._flat()
        self.app.flm.show_hidden = True
        self._list()
        self._flat()
        self.assertEqual(self._shown(), sorted([
            ".dot", "seen.txt", os.path.join(".hidden", "inside.txt")]))

    @unittest.skipIf(sys.platform == "win32", "symlinks need privileges on Windows")
    def test_a_link_to_a_directory_is_not_descended(self):
        self._write(os.path.join("real", "f.txt"))
        # A link back up the tree: descending it would never end.
        os.symlink(self.tmp, os.path.join(self.tmp, "real", "loop"))
        self._list()
        self._flat()
        self.assertEqual(self._shown(), [os.path.join("real", "f.txt")])

    def test_the_same_key_goes_back_to_the_row_it_came_from(self):
        self._write(os.path.join("a", "one.txt"))
        self._write(os.path.join("z", "two.txt"))
        self._list()
        names = [f.name for f in self.pane["files"]]
        self.pane["focused_index"] = names.index("z")
        self._flat()
        self.assertIsNotNone(self.pane["virtual"])
        self._flat()
        self.assertIsNone(self.pane["virtual"])
        self.assertEqual(str(self.pane["path"]), str(Path(self.tmp)))
        self.assertEqual(self.pane["files"][self.pane["focused_index"]].name, "z")

    def test_go_parent_leaves_it_too(self):
        self._write(os.path.join("a", "one.txt"))
        self._list()
        self._flat()
        self.app.dispatch("go_parent")
        self.app._settle_listings()
        self.assertIsNone(self.pane["virtual"])
        self.assertEqual(str(self.pane["path"]), str(Path(self.tmp)))

    def test_a_selection_narrows_it_to_what_is_selected(self):
        self._write(os.path.join("in", "deep", "x.txt"))
        self._write(os.path.join("out", "y.txt"))
        self._write("picked.txt")
        self._write("left.txt")
        self._list()
        self._select("in", "picked.txt")
        self._flat()
        self.assertEqual(self._shown(), sorted([
            "picked.txt", os.path.join("in", "deep", "x.txt")]))
        # Entering starts with nothing selected, as every virtual pane does.
        self.assertFalse(self.pane["selected_files"])

    def test_nothing_below_leaves_the_pane_alone(self):
        os.makedirs(os.path.join(self.tmp, "empty"))
        self._list()
        before = list(self.pane["files"])
        self._flat()
        self.assertIsNone(self.pane["virtual"])
        self.assertEqual(self.pane["files"], before)
        self.assertIn("no files below", self._last_log())

    def test_a_list_is_not_flattened(self):
        a = self._write("a.txt")
        self.app.panel.set_clipboard(a)
        self.app.dispatch("open_list_from_clipboard")
        self.app._settle_listings()
        self._flat()
        self.assertEqual(self.pane["virtual"]["kind"], "list")
        self.assertIn("showing a list", self._last_log())

    def test_a_deleted_file_leaves_on_refresh(self):
        a = self._write(os.path.join("d", "a.txt"))
        b = self._write(os.path.join("d", "b.txt"))
        self._list()
        self._flat()
        os.remove(a)
        self.app._refresh(self.pane)
        self.app._settle_listings()
        self.assertEqual([str(f) for f in self.pane["files"]], [b])
        self.assertEqual(self.pane["virtual"]["kind"], "flat")

    def test_the_header_names_it_and_its_root(self):
        self._write(os.path.join("d", "a.txt"))
        self._list()
        self._flat()
        text = xefm_app._virtual_header_text(self.pane["virtual"], 500)
        self.assertTrue(text.startswith("[Flat view] "))
        self.assertIn(os.path.basename(self.tmp), text)


if __name__ == "__main__":
    unittest.main()
