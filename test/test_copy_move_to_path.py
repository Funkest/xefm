"""Copy / Move to a typed path (Shift-C / Shift-M, #528).

``copy_files_to`` / ``move_files_to`` prompt for a destination directory and
then hand off to the same engine C / M use. The prompt is Jump to Path's: it
starts at the other pane's directory, completes directories only, and resolves
relative input — ``.`` included — against the *active* pane.

The engine call itself is replaced by a recorder: what is under test is which
targets go to which directory, and which input the prompt refuses.

Run with: python -m pytest test/test_copy_move_to_path.py -v
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from xefm import app as xefm_app  # noqa: E402


class _AcceptImmediately:
    """Stands in for ``show_input``: no dialog, just accept ``text`` if it
    validates. Records the keyword arguments for the prefill / completer."""

    def __init__(self, text):
        self.text = text
        self.kwargs = None
        self.error = "not called"

    def __call__(self, panel, *, on_accept, validate=None, **kwargs):
        self.kwargs = kwargs
        self.error = validate(self.text) if validate is not None else None
        if self.error is None:
            on_accept(self.text)


class CopyMoveToPath(unittest.TestCase):
    """A headless XeFMApp on the memory backend over a real temp tree:
    left pane at ``src`` (holding a.txt), right pane at ``other``."""

    def setUp(self):
        from xefm.state_manager import XeFMStateManager
        from puikit.backends import create_backend
        # realpath: macOS /var is a symlink to /private/var (xefm#505).
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.cfgdir = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src")
        self.other = os.path.join(self.tmp, "other")
        self.third = os.path.join(self.tmp, "third")
        for d in (self.src, self.other, self.third, os.path.join(self.src, "inner")):
            os.mkdir(d)
        open(os.path.join(self.src, "a.txt"), "w").close()
        self.sm = XeFMStateManager(db_path=os.path.join(self.cfgdir, "state.db"))
        self.backend = create_backend("memory")
        self.backend.open()
        self.app = xefm_app.XeFMApp(self.backend, self.src, self.other,
                                    left_provided=True, right_provided=True,
                                    state_manager=self.sm)
        self.app._settle_listings()
        pane = self.app.active_pane()
        pane["selected_files"].add(os.path.join(self.src, "a.txt"))
        self.calls = []

        def recorder(kind):
            def op(panel, targets, dest_dir, **kw):
                self.calls.append((kind, [str(t) for t in targets], str(dest_dir)))
            return op
        self.app._fileops.copy = recorder("copy")
        self.app._fileops.move = recorder("move")

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
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.cfgdir, ignore_errors=True)

    def _run(self, action, text):
        stub = _AcceptImmediately(text)
        with mock.patch.object(xefm_app, "show_input", stub):
            getattr(self.app, action)()
        return stub

    def test_copy_to_typed_directory(self):
        stub = self._run("copy_files_to", self.third)
        self.assertIsNone(stub.error)
        self.assertEqual(self.calls, [("copy", [os.path.join(self.src, "a.txt")], self.third)])

    def test_move_to_typed_directory(self):
        self._run("move_files_to", self.third)
        self.assertEqual(self.calls, [("move", [os.path.join(self.src, "a.txt")], self.third)])

    def test_relative_input_resolves_against_the_active_pane(self):
        self._run("copy_files_to", "inner")
        self.assertEqual(self.calls[0][2], os.path.join(self.src, "inner"))
        self._run("copy_files_to", os.path.join("..", "third"))
        self.assertEqual(self.calls[1][2], self.third)

    def test_prefill_is_the_other_pane(self):
        stub = self._run("copy_files_to", self.third)
        self.assertEqual(stub.kwargs["text"], self.other + os.sep)

    def test_completion_offers_directories_only(self):
        stub = self._run("copy_files_to", self.third)
        self.assertTrue(stub.kwargs["completer"].directories_only)

    def test_missing_directory_is_rejected(self):
        stub = self._run("copy_files_to", os.path.join(self.tmp, "nope"))
        self.assertIsNotNone(stub.error)
        self.assertEqual(self.calls, [])

    def test_file_is_rejected(self):
        stub = self._run("copy_files_to", os.path.join(self.src, "a.txt"))
        self.assertIsNotNone(stub.error)
        self.assertEqual(self.calls, [])

    def test_empty_input_is_rejected(self):
        stub = self._run("move_files_to", "  ")
        self.assertIsNotNone(stub.error)
        self.assertEqual(self.calls, [])

    def test_copy_into_own_directory_duplicates(self):
        """``.`` is the active pane: copying there is C's duplicate case."""
        with mock.patch.object(self.app, "_run_duplicate", return_value=False) as dup:
            self._run("copy_files_to", ".")
        dup.assert_called_once()
        self.assertEqual(self.calls, [])

    def test_move_into_own_directory_is_refused(self):
        self._run("move_files_to", ".")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
