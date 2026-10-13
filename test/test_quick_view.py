"""Quick view (#569): the other pane previews the cursor item.

The pure half is the hex dump and what a file loads as. The app half toggles
quick view on the memory backend, moves the cursor, and drives the preview's
tick until it has loaded — the debounce and the worker are real.

Run with: python -m pytest test/test_quick_view.py -v
"""

import os
import shutil
import sys
import tempfile
import time
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from xefm import app as xefm_app  # noqa: E402
from xefm import quick_view  # noqa: E402
from xefm.quick_view import QuickView  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402


class Pure(unittest.TestCase):

    def test_hex_lines(self):
        rows = quick_view.hex_lines(bytes(range(20)))
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].startswith("00000000  00 01 02"))
        self.assertTrue(rows[1].startswith("00000010  10 11 12 13"))
        self.assertTrue(rows[0].endswith("." * 16))

    def test_remote(self):
        self.assertTrue(quick_view.is_remote("s3://bucket/key"))
        self.assertFalse(quick_view.is_remote("/tmp/x"))

    def test_a_large_remote_file_is_not_read(self):
        class Remote:
            name = "big.log"
            suffix = ".log"

            def __str__(self):
                return "ssh://host/big.log"

            def stat(self):
                return types.SimpleNamespace(st_size=quick_view.REMOTE_CAP + 1)

            def open(self, *_a):
                raise AssertionError("must not be read")

        view = QuickView(types.SimpleNamespace(images=False))
        kind, _lines, note, _img = view._load_file(Remote(), {}, {}, False)
        self.assertEqual(kind, "details")
        self.assertIn("not read", note)


class InTheApp(unittest.TestCase):

    def setUp(self):
        from puikit.backends import create_backend
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.other = os.path.realpath(tempfile.mkdtemp())
        with open(os.path.join(self.tmp, "notes.py"), "w") as f:
            f.write("def hello():\n    return 'quick view works'\n")
        with open(os.path.join(self.tmp, "blob.bin"), "wb") as f:
            f.write(bytes(range(256)) * 4)
        os.makedirs(os.path.join(self.tmp, "folder", "sub"))
        for name in ("a", "b", os.path.join("sub", "c")):
            with open(os.path.join(self.tmp, "folder", name), "w") as f:
                f.write("12345")
        self.state_dir = tempfile.mkdtemp()
        self.b = create_backend("memory")
        self.b.open()
        self.app = xefm_app.XeFMApp(
            self.b, self.tmp, self.other, left_provided=True, right_provided=True,
            state_manager=XeFMStateManager(db_path=os.path.join(self.state_dir, "s.db")))
        self.app.file_monitor.stop_monitoring()
        self.app.file_monitor.enabled = False
        self.app._settle_listings()
        self.app.panel.render()
        self.pane = self.app.active_pane()

    def tearDown(self):
        self.app._close_quick_view()
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        for d in (self.tmp, self.other, self.state_dir):
            shutil.rmtree(d, ignore_errors=True)

    def _focus(self, name):
        self.pane["focused_index"] = [f.name for f in self.pane["files"]].index(name)
        self.app._quick_view_follow()

    def _settle(self, until, timeout=5.0):
        deadline = time.monotonic() + timeout
        while not until() and time.monotonic() < deadline:
            self.b.run_animation_ticks()
            time.sleep(0.02)
        self.assertTrue(until())

    def _screen(self):
        self.app.panel.render()
        return "\n".join(self.b.snapshot())

    def test_toggling_takes_the_other_pane_and_gives_it_back(self):
        right_column = self.app.pane_splitter.second
        self.app.dispatch("quick_view")
        self.assertIsNotNone(self.app._quick_view)
        self.assertIsNot(self.app.pane_splitter.second, right_column)
        self.app.dispatch("quick_view")
        self.assertIsNone(self.app._quick_view)
        self.assertIs(self.app.pane_splitter.second, right_column)

    def test_a_text_file_shows_its_start(self):
        self.app.dispatch("quick_view")
        self._focus("notes.py")
        view = self.app._quick_view
        self._settle(lambda: view.kind == "text")
        self.assertIn("quick view works", self._screen())

    def test_a_binary_file_shows_a_hex_dump(self):
        self.app.dispatch("quick_view")
        self._focus("blob.bin")
        view = self.app._quick_view
        self._settle(lambda: view.kind == "hex")
        self.assertIn("00000000  00 01 02", self._screen())

    def test_a_folder_shows_its_totals(self):
        self.app.dispatch("quick_view")
        self._focus("folder")
        view = self.app._quick_view
        self._settle(lambda: view.kind == "dir" and view._scan is not None
                     and view._scan.done)
        screen = self._screen()
        self.assertIn("3 files, 1 folders", screen)

    def test_only_the_item_the_cursor_rests_on_is_loaded(self):
        self.app.dispatch("quick_view")
        view = self.app._quick_view
        self._focus("blob.bin")
        self._focus("notes.py")      # moved on before the debounce ran out
        self._settle(lambda: view.kind == "text")
        self.assertEqual(view.entry.name, "notes.py")

    def test_switching_panes_closes_it(self):
        right_column = self.app.pane_splitter.second
        self.app.dispatch("quick_view")
        self.app.dispatch("switch_pane")
        self.assertIsNone(self.app._quick_view)
        self.assertIs(self.app.pane_splitter.second, right_column)
        self.assertEqual(self.app.pm.active_pane, "right")

    # --- from the hand check ------------------------------------------------

    def test_entering_a_folder_previews_the_item_the_cursor_lands_on(self):
        """The new listing lands after the key that asked for it; the preview
        follows the cursor then, rather than staying on the empty pane."""
        from puikit.event import Event, EventType
        self.app.dispatch("quick_view")
        self._focus("folder")
        self.app.on_event(Event(type=EventType.KEY, key="enter"))
        self.app._settle_listings()
        self.app._pump_monitoring()
        view = self.app._quick_view
        self.assertIsNotNone(view.entry)
        self.assertEqual(str(view.entry.parent), os.path.join(self.tmp, "folder"))

    def test_esc_closes_it(self):
        from puikit.event import Event, EventType
        right_column = self.app.pane_splitter.second
        self.app.dispatch("quick_view")
        self.app.on_event(Event(type=EventType.KEY, key="escape"))
        self.assertIsNone(self.app._quick_view)
        self.assertIs(self.app.pane_splitter.second, right_column)

    def test_operations_on_the_other_pane_are_refused(self):
        """The other pane's directory is hidden behind the preview, so a copy
        there would land somewhere not on screen."""
        calls = []
        self.app._fileops.copy = lambda *a, **k: calls.append(a)
        self.app.dispatch("quick_view")
        self._focus("notes.py")
        self.app.dispatch("copy_files")
        self.assertEqual(calls, [])
        self.assertIn("Quick view is open", self.app.log.lines[-1][0])
        self.app.dispatch("quick_view")
        self.app.dispatch("copy_files")
        self.assertEqual(len(calls), 1, "allowed again once it is closed")


if __name__ == "__main__":
    unittest.main()
