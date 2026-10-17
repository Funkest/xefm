"""Edit anywhere (#581): remote files edited through a local copy that is
uploaded on save, with a check for the remote changing underneath.

The "remote" here is a stand-in backed by a local file and named with an
``ssh://`` URI — the session code only ever reads, writes and stats it, and
asks whether it may write, so the stand-in exercises all of it without a
server.

Run with: python -m pytest test/test_remote_edit.py -v
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path as LocalPath
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from xefm.remote_edit import (EditSessions, RemoteChanged,  # noqa: E402
                              can_write_back, local_copy_path)


class FakeRemote:
    def __init__(self, backing: str, uri: str, writable: bool = True):
        self.backing = backing
        self.uri = uri
        self.writable = writable
        self.forgotten = 0

    def __str__(self):
        return self.uri

    @property
    def name(self):
        return self.uri.rsplit("/", 1)[-1]

    def supports(self, capability):
        return self.writable and capability == "write_operations"

    def forget_cached_metadata(self):
        self.forgotten += 1

    def stat(self):
        return os.stat(self.backing)

    def is_dir(self):
        return False

    def read_bytes(self):
        with open(self.backing, "rb") as f:
            return f.read()

    def write_bytes(self, data):
        with open(self.backing, "wb") as f:
            return f.write(data)


def _bump(path):
    """Move a file's mtime forward, so a same-second rewrite still reads as a
    change on filesystems with coarse timestamps."""
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


class LocalCopyPath(unittest.TestCase):
    def test_mirrors_the_remote_path(self):
        root = LocalPath("/r")
        self.assertEqual(local_copy_path(root, "ssh://host/srv/app/a.py"),
                         root / "ssh" / "host" / "srv" / "app" / "a.py")

    def test_cannot_escape_the_root(self):
        root = LocalPath("/r")
        path = local_copy_path(root, "ssh://host/../../etc/passwd")
        self.assertNotIn("..", path.parts)
        self.assertEqual(path.parts[:2], ("/", "r"))

    def test_characters_a_platform_refuses_are_replaced(self):
        path = local_copy_path(LocalPath("/r"), 's3://bucket/a:b?c.txt')
        self.assertEqual(path.name, "a_b_c.txt")


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.backing = os.path.join(self.tmp, "server-a.txt")
        with open(self.backing, "w") as f:
            f.write("v1")
        self.remote = FakeRemote(self.backing, "ssh://host/srv/a.txt")
        self.sessions = EditSessions(LocalPath(self.tmp) / "edit")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _save(self, session, text):
        session.local.write_text(text)
        _bump(session.local)

    def test_writability_is_the_backend_s_declaration(self):
        self.assertTrue(can_write_back(self.remote))
        self.assertFalse(can_write_back(FakeRemote(self.backing, "archive://x", False)))

    def test_open_downloads_to_the_mirrored_copy(self):
        session = self.sessions.open(self.remote)
        self.assertEqual(session.local.read_text(), "v1")
        self.assertTrue(str(session.local).endswith(os.path.join("ssh", "host", "srv", "a.txt")))
        self.assertFalse(session.pending)

    def test_a_save_is_seen_and_uploaded(self):
        session = self.sessions.open(self.remote)
        self.assertEqual(self.sessions.saved(), [])
        self._save(session, "v2")
        self.assertEqual(self.sessions.saved(), [session])
        self.sessions.upload(session)
        with open(self.backing) as f:
            self.assertEqual(f.read(), "v2")
        self.assertFalse(session.pending)
        self.assertEqual(self.sessions.saved(), [], "a save is reported once")

    def test_a_save_that_changes_nothing_is_not_an_upload(self):
        session = self.sessions.open(self.remote)
        self._save(session, "v1")
        self.assertEqual(self.sessions.saved(), [])

    def test_a_remote_change_stops_the_upload_before_it_writes(self):
        session = self.sessions.open(self.remote)
        with open(self.backing, "w") as f:
            f.write("theirs, longer")
        self._save(session, "mine")
        with self.assertRaises(RemoteChanged):
            self.sessions.upload(session)
        with open(self.backing) as f:
            self.assertEqual(f.read(), "theirs, longer")
        self.assertTrue(session.pending)
        self.assertGreater(self.remote.forgotten, 0, "the stat bypassed the cache")

    def test_force_overwrites_and_the_next_upload_needs_no_force(self):
        session = self.sessions.open(self.remote)
        with open(self.backing, "w") as f:
            f.write("theirs, longer")
        self._save(session, "mine")
        self.sessions.upload(session, force=True)
        self._save(session, "mine again")
        self.sessions.upload(session)
        with open(self.backing) as f:
            self.assertEqual(f.read(), "mine again")

    def test_reopening_keeps_an_unsent_edit(self):
        session = self.sessions.open(self.remote)
        self._save(session, "unsent")
        again = self.sessions.open(self.remote)
        self.assertIs(again, session)
        self.assertEqual(session.local.read_text(), "unsent")

    def test_reopening_a_clean_session_fetches_the_remote_again(self):
        session = self.sessions.open(self.remote)
        with open(self.backing, "w") as f:
            f.write("v3")
        self.sessions.open(self.remote)
        self.assertEqual(session.local.read_text(), "v3")

    def test_close_all_removes_clean_copies_and_keeps_pending_ones(self):
        clean = self.sessions.open(self.remote)
        other_backing = os.path.join(self.tmp, "server-b.txt")
        with open(other_backing, "w") as f:
            f.write("b")
        dirty = self.sessions.open(FakeRemote(other_backing, "ssh://host/other/b.txt"))
        self._save(dirty, "unsent")
        kept = self.sessions.close_all()
        self.assertEqual(kept, [dirty])
        self.assertFalse(clean.local.exists())
        self.assertFalse(clean.local.parent.exists(), "empty mirror dirs pruned")
        self.assertTrue(dirty.local.exists())
        self.assertEqual(len(self.sessions), 0)


class AppEditRemote(unittest.TestCase):
    """``edit_file`` on a remote entry: download, editor, upload on save."""

    def setUp(self):
        from puikit.backends import create_backend
        from xefm import app as xefm_app
        from xefm.state_manager import XeFMStateManager
        self.xefm_app = xefm_app
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.state_dir = tempfile.mkdtemp()
        self.backing = os.path.join(self.tmp, "server.txt")
        with open(self.backing, "w") as f:
            f.write("v1")
        sm = XeFMStateManager(db_path=os.path.join(self.state_dir, "state.db"))
        self.backend = create_backend("memory")
        self.backend.open()
        self.app = xefm_app.XeFMApp(self.backend, self.tmp, self.tmp,
                                    left_provided=True, right_provided=True,
                                    state_manager=sm)
        self.app.file_monitor.stop_monitoring()
        self.app._settle_listings()
        self.app._edit_sessions = EditSessions(LocalPath(self.tmp) / "edit")
        self._saved_editor = self.app.config.TEXT_EDITOR
        self.app.config.TEXT_EDITOR = "fake-editor"
        # is_desktop_mode() caches process-global detection other tests can
        # leave True; desktop mode detaches the editor (#644) instead of the
        # subprocess.run these tests stand in for, so pin terminal mode.
        desktop = patch("xefm.app.is_desktop_mode", return_value=False)
        desktop.start()
        self.addCleanup(desktop.stop)

    def tearDown(self):
        self.app.config.TEXT_EDITOR = self._saved_editor
        try:
            self.app.file_monitor.stop_monitoring()
            self.backend.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def _drain(self):
        """Pump the UI until the download and upload tasks finish, as the
        event loop would."""
        deadline = time.time() + 5
        while self.app.tasks.has_active() and time.time() < deadline:
            self.backend.run_animation_ticks()
            time.sleep(0.005)
        self.backend.run_animation_ticks()
        self.assertFalse(self.app.tasks.has_active(), "task did not finish")

    def test_a_terminal_editor_s_save_is_uploaded_on_return(self):
        remote = FakeRemote(self.backing, "ssh://host/srv/notes.txt")

        def editor(argv, **kwargs):
            with open(argv[-1], "w") as f:
                f.write("edited")
            _bump(argv[-1])

        with patch("subprocess.run", side_effect=editor) as run:
            self.app._edit_entries([remote])
            self._drain()
        self.assertTrue(run.call_args.args[0][-1].endswith("notes.txt"))
        with open(self.backing) as f:
            self.assertEqual(f.read(), "edited")

    def test_a_failed_upload_is_loud_and_keeps_the_copy(self):
        from puikit.widgets.message_box import MessageBox
        remote = FakeRemote(self.backing, "ssh://host/srv/notes.txt")

        def fail(data):
            raise PermissionError("read-only share")
        remote.write_bytes = fail

        def editor(argv, **kwargs):
            with open(argv[-1], "w") as f:
                f.write("edited")
            _bump(argv[-1])

        with patch("subprocess.run", side_effect=editor):
            self.app._edit_entries([remote])
            self._drain()
        top = self.app.panel._layers[-1].widget
        self.assertIsInstance(top, MessageBox)
        self.assertIn("read-only share", top.message)
        session = self.app.edit_sessions.get(remote)
        self.assertIn(str(session.local), top.message)
        self.assertEqual(session.local.read_text(), "edited")

    def test_a_remote_change_is_asked_about_before_overwriting(self):
        from puikit.widgets.message_box import MessageBox
        remote = FakeRemote(self.backing, "ssh://host/srv/notes.txt")

        def editor(argv, **kwargs):
            with open(self.backing, "w") as f:
                f.write("someone else, meanwhile")   # the server moves on
            with open(argv[-1], "w") as f:
                f.write("mine")
            _bump(argv[-1])

        with patch("subprocess.run", side_effect=editor):
            self.app._edit_entries([remote])
            deadline = time.time() + 5
            box = None
            while time.time() < deadline:
                self.backend.run_animation_ticks()
                top = self.app.panel._layers[-1].widget
                if isinstance(top, MessageBox):
                    box = top
                    break
                time.sleep(0.005)
        self.assertIsNotNone(box, "no remote-changed question")
        self.assertIn("changed on the server", box.message)
        with open(self.backing) as f:
            self.assertEqual(f.read(), "someone else, meanwhile",
                             "nothing written before the answer")
        box._close(box.buttons.index("Overwrite"))
        self._drain()
        with open(self.backing) as f:
            self.assertEqual(f.read(), "mine")

    def test_a_gui_editor_s_later_save_is_found_by_the_poll(self):
        remote = FakeRemote(self.backing, "ssh://host/srv/notes.txt")
        with patch("subprocess.run"):            # a window opens and returns
            self.app._edit_entries([remote])
            self._drain()
        self.assertIsNotNone(self.app._edit_poll_cancel, "the poll is armed")
        session = self.app.edit_sessions.get(remote)
        session.local.write_text("saved later")
        _bump(session.local)
        self.app._poll_edit_sessions()
        self._drain()
        with open(self.backing) as f:
            self.assertEqual(f.read(), "saved later")

    def test_a_read_only_location_is_refused(self):
        remote = FakeRemote(self.backing, "archive:///x.zip/notes.txt", writable=False)
        with patch("subprocess.run") as run:
            self.app._edit_entries([remote])
            self._drain()
        run.assert_not_called()

    def test_quitting_keeps_only_unsent_copies(self):
        remote = FakeRemote(self.backing, "ssh://host/srv/notes.txt")
        with patch("subprocess.run"):
            self.app._edit_entries([remote])
            self._drain()
        session = self.app.edit_sessions.get(remote)
        self.assertTrue(session.local.exists())
        self.app._close_edit_sessions()
        self.assertFalse(session.local.exists())


if __name__ == "__main__":
    unittest.main()
