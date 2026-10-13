"""Rename in the editor (#581): the name list, the plan read back from it, and
the renames carried out — swaps and cycles included — plus the app's round
trip through a (mocked) TEXT_EDITOR.

Run with: python -m pytest test/test_rename_in_editor.py -v
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from puikit.backends import create_backend  # noqa: E402
from puikit.widgets.message_box import MessageBox  # noqa: E402

from xefm import app as xefm_app  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.rename_in_editor import (UnlistableName, apply_plan,  # noqa: E402
                                   names_text, parse_plan)
from xefm.state_manager import XeFMStateManager  # noqa: E402


class _Dir(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make(self, *names):
        out = []
        for name in names:
            path = os.path.join(self.tmp, name)
            with open(path, "w") as f:
                f.write(name)
            out.append(Path(path))
        return out

    def contents(self):
        """name -> original name, read from each file's content."""
        out = {}
        for name in os.listdir(self.tmp):
            with open(os.path.join(self.tmp, name)) as f:
                out[name] = f.read()
        return out


class NamesText(_Dir):
    def test_one_name_per_line(self):
        files = self.make("a.txt", "b c.txt")
        self.assertEqual(names_text(files), "a.txt\nb c.txt\n")

    def test_a_name_with_a_line_break_is_refused(self):
        class Entry:
            name = "two\nlines"
        with self.assertRaises(UnlistableName):
            names_text([Entry()])


class ParsePlan(_Dir):
    def test_changed_lines_are_renames_and_untouched_ones_are_not(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "a.txt\nB2.txt\n")
        self.assertTrue(plan.ok)
        self.assertEqual([(e.name, n) for e, n in plan.renames], [("b.txt", "B2.txt")])

    def test_full_width_space_survives(self):
        (a,) = self.make("a.txt")
        plan = parse_plan([a], "a　b.txt\n")
        self.assertEqual(plan.renames[0][1], "a　b.txt")

    def test_crlf_and_a_missing_final_newline_are_not_part_of_the_names(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "x.txt\r\ny.txt")
        self.assertEqual([n for _, n in plan.renames], ["x.txt", "y.txt"])

    def test_a_trailing_space_is_kept(self):
        (a,) = self.make("a.txt")
        plan = parse_plan([a], "a.txt \n")
        self.assertEqual(plan.renames[0][1], "a.txt ")

    def test_line_count_change_is_refused(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "a.txt\n")
        self.assertFalse(plan.ok)
        self.assertIn("1 line(s) for 2 file(s)", plan.errors[0])

    def test_empty_and_invalid_names_are_refused(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "\nsub/b.txt\n")
        self.assertEqual(len(plan.errors), 2)
        self.assertIn("line 1", plan.errors[0])
        self.assertIn("line 2", plan.errors[1])
        self.assertEqual(plan.renames, [])

    def test_two_lines_on_one_name_are_refused(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "c.txt\nc.txt\n")
        self.assertFalse(plan.ok)
        self.assertIn("also on line 2", plan.errors[0])

    def test_landing_on_an_unchanged_batch_name_is_refused(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "b.txt\nb.txt\n")
        self.assertFalse(plan.ok)

    def test_a_name_held_outside_the_batch_is_refused(self):
        a, _ = self.make("a.txt", "taken.txt")
        plan = parse_plan([a], "taken.txt\n")
        self.assertFalse(plan.ok)
        self.assertIn("already exists", plan.errors[0])

    def test_a_swap_is_allowed(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "b.txt\na.txt\n")
        self.assertTrue(plan.ok, plan.errors)
        self.assertEqual(len(plan.renames), 2)


class ApplyPlan(_Dir):
    def test_plain_renames(self):
        a, b = self.make("a.txt", "b.txt")
        renamed, errors = apply_plan(parse_plan([a, b], "x.txt\ny.txt\n"))
        self.assertEqual(errors, [])
        self.assertEqual(self.contents(), {"x.txt": "a.txt", "y.txt": "b.txt"})
        self.assertEqual(renamed, {str(a): "x.txt", str(b): "y.txt"})

    def test_swap(self):
        a, b = self.make("a.txt", "b.txt")
        renamed, errors = apply_plan(parse_plan([a, b], "b.txt\na.txt\n"))
        self.assertEqual(errors, [])
        self.assertEqual(self.contents(), {"b.txt": "a.txt", "a.txt": "b.txt"})

    def test_cycle_of_three(self):
        files = self.make("1", "2", "3")
        _, errors = apply_plan(parse_plan(files, "2\n3\n1\n"))
        self.assertEqual(errors, [])
        self.assertEqual(self.contents(), {"2": "1", "3": "2", "1": "3"})

    def test_shift_down_a_chain_into_a_new_name(self):
        files = self.make("1", "2")
        _, errors = apply_plan(parse_plan(files, "2\n3\n"))
        self.assertEqual(errors, [])
        self.assertEqual(self.contents(), {"2": "1", "3": "2"})

    def test_a_failed_final_step_names_the_temporary_file(self):
        a, b = self.make("a.txt", "b.txt")
        plan = parse_plan([a, b], "b.txt\na.txt\n")
        calls = []

        def rename(src, dst):
            calls.append(dst.name)
            # Park both, then fail the first move out of the parking spot.
            if len(calls) == 3:
                raise OSError("disk said no")
            src.rename(dst)

        renamed, errors = apply_plan(plan, rename)
        self.assertEqual(len(errors), 1)
        self.assertIn("now named .xefm-rename-", errors[0])
        parked = [n for n in os.listdir(self.tmp) if n.startswith(".xefm-rename-")]
        self.assertEqual(len(parked), 1, "the file is still there, under that name")


class AppRoundTrip(unittest.TestCase):
    """The editor round trip, with ``subprocess.run`` standing in for it."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.state_dir = tempfile.mkdtemp()
        for name in ("a.txt", "b.txt"):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write(name)
        sm = XeFMStateManager(db_path=os.path.join(self.state_dir, "state.db"))
        self.backend = create_backend("memory")
        self.backend.open()
        self.app = xefm_app.XeFMApp(self.backend, self.tmp, self.tmp,
                                    left_provided=True, right_provided=True,
                                    state_manager=sm)
        self.app.file_monitor.stop_monitoring()
        self.app._settle_listings()
        self._saved_editor = self.app.config.TEXT_EDITOR
        self.app.config.TEXT_EDITOR = "fake-editor"
        pane = self.app.active_pane()
        pane["selected_files"] = {str(f) for f in pane["files"]}

    def tearDown(self):
        self.app.config.TEXT_EDITOR = self._saved_editor
        try:
            self.app.file_monitor.stop_monitoring()
            self.backend.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def _box(self):
        layers = self.app.panel._layers
        self.assertTrue(layers and isinstance(layers[-1].widget, MessageBox),
                        "expected a message box on top")
        return layers[-1].widget

    def _press(self, label):
        box = self._box()
        box._close(box.buttons.index(label))

    def _editor(self, transform):
        def run(argv, **kwargs):
            path = argv[-1]
            with open(path, encoding="utf-8") as f:
                text = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(transform(text))
        return patch("subprocess.run", side_effect=run)

    def _names(self):
        return sorted(os.listdir(self.tmp))

    def test_edited_names_are_confirmed_then_renamed(self):
        with self._editor(lambda t: t.replace("a.txt", "alpha.txt")):
            self.app.rename_in_editor()
        box = self._box()
        self.assertIn("a.txt  →  alpha.txt", box.message)
        self.assertEqual(self._names(), ["a.txt", "b.txt"], "nothing moves before Rename")
        self._press("Rename")
        self.assertEqual(self._names(), ["alpha.txt", "b.txt"])

    def test_cancel_renames_nothing_and_removes_the_list(self):
        seen = []
        with self._editor(lambda t: (seen.append(t), t.replace("a.txt", "z.txt"))[1]):
            self.app.rename_in_editor()
        self._press("Cancel")
        self.assertEqual(self._names(), ["a.txt", "b.txt"])

    def test_a_refused_list_offers_edit_again(self):
        with self._editor(lambda t: "only-one-line\n"):
            self.app.rename_in_editor()
        box = self._box()
        self.assertIn("Edit Again", box.buttons)
        with self._editor(lambda t: "b.txt\na.txt\n"):
            self._press("Edit Again")
        self._press("Rename")
        with open(os.path.join(self.tmp, "a.txt")) as f:
            self.assertEqual(f.read(), "b.txt", "swapped through the editor")

    def test_an_editor_that_returns_at_once_waits_for_apply(self):
        list_paths = []

        def gui_editor(argv, **kwargs):
            list_paths.append(argv[-1])   # a window opens; nothing saved yet

        with patch("subprocess.run", side_effect=gui_editor):
            self.app.rename_in_editor()
        box = self._box()
        self.assertIn("Apply", box.buttons)
        with open(list_paths[0], "w", encoding="utf-8") as f:
            f.write("a.txt\nbeta.txt\n")   # the user saves in that window
        self._press("Apply")
        self._press("Rename")
        self.assertEqual(self._names(), ["a.txt", "beta.txt"])

    def test_nothing_changed_in_a_blocking_editor_just_says_so(self):
        with patch.object(xefm_app.XeFMApp, "_EDITOR_RETURNED_AT_ONCE", 0.0), \
             patch.object(xefm_app, "is_desktop_mode", return_value=False), \
             self._editor(lambda t: t):
            self.app.rename_in_editor()
        layers = self.app.panel._layers
        self.assertFalse(layers and isinstance(layers[-1].widget, MessageBox))
        self.assertEqual(self._names(), ["a.txt", "b.txt"])


if __name__ == "__main__":
    unittest.main()
