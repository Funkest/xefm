"""The file clipboard (#577): copy or cut now, paste wherever you go next.

The model is tested on its own, then in the app on the memory backend. That
backend keeps a process-local *OS* file clipboard with a change counter
(PuiKit ``clipboard_files``), so a test can play Finder or Explorer by
writing to it; a clipboard with no panel stands for a terminal or Linux,
where XeFM's own clipboard is the only one.

Run with: python -m pytest test/test_file_clipboard.py -v
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
from xefm.file_clipboard import FileClipboard, conflicts  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402


class _Panel:
    """Just the file-clipboard calls, over a memory backend."""

    def __init__(self):
        from puikit.backends.memory_backend import MemoryBackend
        self.backend = MemoryBackend()

    def set_clipboard_files(self, paths, *, cut=False):
        return self.backend.set_clipboard_files([str(p) for p in paths], cut)

    def get_clipboard_files(self):
        return self.backend.get_clipboard_files()

    def clipboard_change_count(self):
        return self.backend.clipboard_change_count()


class Model(unittest.TestCase):

    def test_xefms_own_clipboard(self):
        clip = FileClipboard(None)           # a terminal, or Linux
        self.assertIsNone(clip.contents())
        self.assertEqual(clip.status(), "")
        clip.put([Path("/a/x.txt"), Path("s3://bucket/y")], cut=False)
        c = clip.contents()
        self.assertEqual((len(c.paths), c.cut, c.origin), (2, False, "xefm"))
        self.assertEqual(clip.status(), "[COPY 2]")
        self.assertIn("s3://bucket/y", clip.marks())
        clip.consume()                       # a copy survives its paste
        self.assertEqual(clip.status(), "[COPY 2]")
        clip.put([Path("/a/x.txt")], cut=True)
        self.assertEqual(clip.status(), "[CUT 1]")
        clip.consume()                       # a cut does not
        self.assertIsNone(clip.contents())

    def test_local_files_reach_the_os_clipboard(self):
        panel = _Panel()
        clip = FileClipboard(panel)
        self.assertTrue(clip.put([Path("/a/x.txt")], cut=True, local_paths=["/a/x.txt"]))
        files = panel.get_clipboard_files()
        self.assertEqual((files.paths, files.cut), (("/a/x.txt",), True))
        # XeFM's own write is not "another app".
        self.assertEqual(clip.contents().origin, "xefm")

    def test_another_apps_files_are_newer(self):
        panel = _Panel()
        clip = FileClipboard(panel)
        clip.put([Path("/a/x.txt")], cut=False, local_paths=["/a/x.txt"])
        panel.backend.set_clipboard_files(["/from/finder.pdf", "/from/finder2.pdf"])
        c = clip.contents()
        self.assertEqual((c.origin, [str(p) for p in c.paths]),
                         ("os", [str(Path("/from/finder.pdf")),
                                 str(Path("/from/finder2.pdf"))]))
        self.assertEqual(clip.status(), "[2 from another app]")

    def test_an_older_os_clipboard_does_not_win_over_a_remote_copy(self):
        panel = _Panel()
        panel.backend.set_clipboard_files(["/from/finder.pdf"])     # earlier
        clip = FileClipboard(panel)
        clip.put([Path("s3://bucket/key")], cut=False, local_paths=[])
        self.assertEqual(clip.contents().origin, "xefm")

    def test_an_explorer_cut_is_taken_once(self):
        panel = _Panel()
        clip = FileClipboard(panel)
        panel.backend.set_clipboard_files(["C:/a.txt"], cut=True)
        self.assertEqual(clip.status(), "[CUT 1 from another app]")
        clip.take_os()
        self.assertIsNone(clip.contents())

    def test_a_newer_text_copy_replaces_the_files(self):
        """It is one clipboard: text copied after XeFM's files — in another
        application, or XeFM's own log — is what the clipboard holds now, so
        the files are no longer there to paste or to mark."""
        panel = _Panel()
        clip = FileClipboard(panel)
        clip.put([Path("/a/x.txt")], cut=False, local_paths=["/a/x.txt"])
        panel.backend.set_clipboard("some text")
        self.assertIsNone(clip.contents())
        self.assertEqual(clip.marks(), frozenset())
        self.assertEqual(clip.status(), "")

    def test_conflict_preview(self):
        clip = FileClipboard(None)
        clip.put([Path("/src/a.txt"), Path("/src/B.txt"), Path("/dst/c.txt")], cut=False)
        n = conflicts(clip.contents(), Path("/dst"), ["a.txt", "b.txt", "c.txt", "other"])
        # a.txt and B.txt (case-insensitively) meet names; c.txt is already here.
        self.assertEqual(n, 2)


class InTheApp(unittest.TestCase):

    def setUp(self):
        from puikit.backends import create_backend
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.src = os.path.join(self.root, "src")
        self.dst = os.path.join(self.root, "dst")
        os.makedirs(self.src)
        os.makedirs(self.dst)
        for name in ("a.txt", "b.txt"):
            with open(os.path.join(self.src, name), "w") as f:
                f.write(name)
        with open(os.path.join(self.dst, "a.txt"), "w") as f:
            f.write("existing")
        self.state = tempfile.mkdtemp()
        self.b = create_backend("memory")
        self.b.open()
        self.app = xefm_app.XeFMApp(
            self.b, self.src, self.dst, left_provided=True, right_provided=True,
            state_manager=XeFMStateManager(db_path=os.path.join(self.state, "s.db")))
        self.app.config.CONFIRM_COPY = False
        self.app.config.CONFIRM_MOVE = False
        self.app.file_monitor.stop_monitoring()
        self.app.file_monitor.enabled = False
        self.app._settle_listings()

    def tearDown(self):
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def _focus(self, name):
        pane = self.app.active_pane()
        pane["focused_index"] = [f.name for f in pane["files"]].index(name)

    def _wait(self):
        deadline = time.monotonic() + 10
        while self.app.tasks.has_active() and time.monotonic() < deadline:
            self.b.run_animation_ticks()
            time.sleep(0.01)
        self.b.run_animation_ticks()
        self.app._settle_listings()

    def _logs(self):
        return [t for t, _s in self.app.log.lines]

    def test_copy_then_paste_in_the_other_pane(self):
        self._focus("b.txt")
        self.app.dispatch("clipboard_copy")
        self.assertEqual(self.app.clipboard.status(), "[COPY 1]")
        self.assertIn(os.path.join(self.src, "b.txt"), self.app.left_view.clipboard_marks)
        self.app.dispatch("switch_pane")
        self.app.dispatch("clipboard_paste")
        self._wait()
        with open(os.path.join(self.dst, "b.txt")) as f:
            self.assertEqual(f.read(), "b.txt")
        self.assertTrue(os.path.exists(os.path.join(self.src, "b.txt")))
        self.assertEqual(self.app.clipboard.status(), "[COPY 1]")   # still there

    def test_cut_moves_on_paste_and_is_then_gone(self):
        self._focus("b.txt")
        self.app.dispatch("clipboard_cut")
        self.assertTrue(self.app.left_view.clipboard_cut)
        self.app.dispatch("switch_pane")
        self.app.dispatch("clipboard_paste")
        self._wait()
        self.assertTrue(os.path.exists(os.path.join(self.dst, "b.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.src, "b.txt")))
        self.assertEqual(self.app.clipboard.status(), "")
        self.assertTrue(any("Tip:" in line for line in self._logs()))

    def test_a_cut_pasted_where_it_is_does_nothing(self):
        self._focus("a.txt")
        self.app.dispatch("clipboard_cut")
        self.app.dispatch("clipboard_paste")
        self.assertIn("already here", self._logs()[-1])

    def test_the_footer_previews_conflicts(self):
        self._focus("a.txt")
        self.app.dispatch("clipboard_copy")
        self.assertEqual(self.app._paste_preview(self.app.pm.right_pane), "paste: 1 conflict")
        self.assertEqual(self.app._paste_preview(self.app.pm.left_pane), "")

    def test_files_from_another_app_paste(self):
        outside = os.path.join(self.root, "outside.txt")
        with open(outside, "w") as f:
            f.write("from finder")
        self.b.set_clipboard_files([outside])
        self.app.dispatch("switch_pane")
        self.assertEqual(self.app.clipboard.status(), "[1 from another app]")
        self.app.dispatch("clipboard_paste")
        self._wait()
        self.assertTrue(os.path.exists(os.path.join(self.dst, "outside.txt")))
        self.assertTrue(any("from another app" in line for line in self._logs()))

    def test_copy_reaches_the_system_clipboard(self):
        self._focus("a.txt")
        self.app.dispatch("clipboard_copy")
        files = self.b.get_clipboard_files()
        self.assertEqual(files.paths, (os.path.join(self.src, "a.txt"),))

    def test_copying_log_text_replaces_the_files(self):
        """One clipboard (#577 hand check): Cmd/Ctrl-C on a log selection
        copies the text, and the files XeFM held are no longer held."""
        self._focus("a.txt")
        self.app.dispatch("clipboard_copy")
        self.assertTrue(self.app.clipboard.paths)
        self.app.log_info("a line to copy")
        self.app.panel.render()
        self.app.log._select_all()
        self.app.dispatch("clipboard_copy")
        self.assertEqual(self.app.clipboard.paths, [])
        self.assertEqual(self.app.clipboard.status(), "")
        self.assertIn("a line to copy", self.b.get_clipboard())

    def test_clicking_the_status_shows_what_is_held(self):
        from puikit.event import Event, EventType
        from puikit.widgets.message_box import MessageBox
        self._focus("a.txt")
        self.app.dispatch("clipboard_copy")
        self.app.panel.render()
        x0, x1 = self.app.status._clip_hit
        self.app.status.handle_event(Event(type=EventType.MOUSE_CLICK,
                                           x=(x0 + x1) / 2, y=0.0, button="left"))
        box = self.app.panel._layers[-1].widget
        self.assertIsInstance(box, MessageBox)
        self.assertIn("a.txt", box.message)
        self.assertEqual(box.buttons, ["Paste Here", "Clear", "Close"])
        box._close(box.buttons.index("Clear"))
        self.assertEqual(self.app.clipboard.paths, [])

    def test_paste_is_refused_into_a_list(self):
        # The list comes from text on the clipboard, so it is made first: a
        # text copy replaces files on the one clipboard.
        self.app.panel.set_clipboard(os.path.join(self.dst, "a.txt"))
        self.app.dispatch("switch_pane")
        self.app.dispatch("open_list_from_clipboard")
        self.app._settle_listings()
        self.app.dispatch("switch_pane")
        self._focus("a.txt")
        self.app.dispatch("clipboard_copy")
        self.app.dispatch("switch_pane")
        self.app.dispatch("clipboard_paste")
        self.assertIn("not a folder", self._logs()[-1])

    def test_the_status_bar_leads_with_what_is_carried(self):
        self._focus("a.txt")
        self.app.dispatch("clipboard_cut")
        self.app.panel.render()
        bottom = self.b.snapshot()[-1]
        self.assertTrue(bottom.strip().startswith("[CUT 1]"), bottom)


if __name__ == "__main__":
    unittest.main()
