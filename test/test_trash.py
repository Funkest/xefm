"""Delete to the system's trash (#591).

The freedesktop implementation is ordinary POSIX file work, so it runs for
real here against a temporary ``XDG_DATA_HOME``. The macOS and Windows calls
go to the user's own Trash / Recycle Bin, which no test may touch (see
``conftest.no_real_trash``): the macOS one is driven through a stand-in
NSFileManager, and the Windows one only on Windows, never here.

Run with: python -m pytest test/test_trash.py -v
"""

import os
import shutil
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path as LocalPath
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from xefm import trash  # noqa: E402

#: Captured at import, before the suite's guard swaps it out, so the macOS
#: path can be exercised against a stand-in manager.
_REAL_TRASH_MACOS = trash._trash_macos


class Freedesktop(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        self.data = os.path.join(self.root, "data")
        self.env = patch.dict(os.environ, {"XDG_DATA_HOME": self.data})
        self.env.start()
        self.trash = LocalPath(self.data) / "Trash"

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def make(self, name, content="x"):
        path = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return path

    def info(self, name):
        text = (self.trash / "info" / f"{name}.trashinfo").read_text()
        fields = dict(line.split("=", 1) for line in text.splitlines()[1:])
        self.assertEqual(text.splitlines()[0], "[Trash Info]")
        return fields

    def test_a_file_goes_to_the_home_trash_with_its_info(self):
        path = self.make("a.txt", "hello")
        name = trash._trash_freedesktop(path, now=0)
        self.assertEqual(name, "a.txt")
        self.assertFalse(os.path.exists(path))
        self.assertEqual((self.trash / "files" / "a.txt").read_text(), "hello")
        fields = self.info("a.txt")
        self.assertEqual(urllib.parse.unquote(fields["Path"]), path)
        self.assertRegex(fields["DeletionDate"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d$")

    def test_a_name_already_in_the_trash_gets_a_number_before_the_extension(self):
        first = self.make("a.txt")
        trash._trash_freedesktop(first)
        second = self.make("a.txt")
        self.assertEqual(trash._trash_freedesktop(second), "a.2.txt")
        self.assertTrue((self.trash / "info" / "a.2.txt.trashinfo").exists())

    def test_dotfiles_and_extensionless_names(self):
        trash._trash_freedesktop(self.make(".rc"))
        self.assertEqual(trash._trash_freedesktop(self.make(".rc")), ".rc.2")
        trash._trash_freedesktop(self.make("README"))
        self.assertEqual(trash._trash_freedesktop(self.make("README")), "README.2")

    def test_a_directory_goes_whole(self):
        self.make("dir/inner/f.txt", "deep")
        trash._trash_freedesktop(os.path.join(self.root, "dir"))
        self.assertEqual((self.trash / "files" / "dir" / "inner" / "f.txt").read_text(), "deep")

    def test_the_recorded_path_is_percent_encoded(self):
        path = self.make("日本 語%.txt")
        trash._trash_freedesktop(path)
        raw = self.info("日本 語%.txt")["Path"]
        self.assertNotIn(" ", raw)
        self.assertEqual(urllib.parse.unquote(raw), path)

    def test_a_failed_move_leaves_no_info_behind(self):
        path = self.make("a.txt")
        with patch.object(trash.os, "rename", side_effect=PermissionError("nope")):
            with self.assertRaises(PermissionError):
                trash._trash_freedesktop(path)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(list((self.trash / "info").iterdir()), [])

    def test_another_volume_uses_its_own_trash_at_the_top(self):
        """The home trash on another device: the file's volume gets
        ``.Trash-$uid`` at its top, and the info records the path relative to
        that top."""
        path = self.make("vol/a.txt")
        top = os.path.join(self.root, "vol")
        real_stat = os.stat

        def stat(p, *a, **k):
            st = real_stat(p, *a, **k)
            if str(p).startswith(self.data):
                fields = list(st)
                fields[2] = st.st_dev + 1
                return os.stat_result(fields)
            return st

        with patch.object(trash.os, "stat", stat), \
             patch.object(trash, "_mount_point", lambda p: top):
            trash._trash_freedesktop(path)
        topdir_trash = LocalPath(top) / f".Trash-{os.getuid()}"
        self.assertTrue((topdir_trash / "files" / "a.txt").exists())
        text = (topdir_trash / "info" / "a.txt.trashinfo").read_text()
        self.assertIn("Path=a.txt\n", text)

    def test_send_uses_it_off_macos_and_windows(self):
        path = self.make("b.txt")
        with patch.object(trash.sys, "platform", "linux"):
            trash.send(path)
        self.assertTrue((self.trash / "files" / "b.txt").exists())


class MacOS(unittest.TestCase):
    def test_finder_s_call_is_made_with_the_file_url(self):
        calls = []

        class Url:
            @staticmethod
            def fileURLWithPath_(path):
                return ("url", path)

        class Manager:
            def trashItemAtURL_resultingItemURL_error_(self, url, _r, _e):
                calls.append(url)
                return True, None, None

        with patch.object(trash, "_mac_manager", lambda: (Manager(), Url)):
            _REAL_TRASH_MACOS("/x/a.txt")
        self.assertEqual(calls, [("url", "/x/a.txt")])

    def test_a_refusal_is_an_oserror_with_the_reason(self):
        class Error:
            def localizedDescription(self):
                return "The volume does not support the Trash."

        class Manager:
            def trashItemAtURL_resultingItemURL_error_(self, url, _r, _e):
                return False, None, Error()

        class Url:
            fileURLWithPath_ = staticmethod(lambda p: p)

        with patch.object(trash, "_mac_manager", lambda: (Manager(), Url)):
            with self.assertRaises(OSError) as caught:
                _REAL_TRASH_MACOS("/x/a.txt")
        self.assertIn("does not support", caught.exception.strerror)


class Availability(unittest.TestCase):
    def test_remote_and_archived_items_have_no_trash(self):
        for path in ("ssh://h/a", "s3://b/k", "archive:///x.zip#a"):
            self.assertFalse(trash.available(path), path)
            with self.assertRaises(OSError):
                trash.send(path)

    def test_the_guard_keeps_tests_off_the_real_trash(self):
        with self.assertRaises(AssertionError):
            trash._trash_macos("/x")


class AppDelete(unittest.TestCase):
    """K sends to the trash where there is one; Shift-K and trash-less places
    delete for good, and the confirmation says which."""

    def setUp(self):
        from puikit.backends import create_backend
        from xefm import app as xefm_app
        from xefm.state_manager import XeFMStateManager
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.state_dir = tempfile.mkdtemp()
        for name in ("a.txt", "b.txt"):
            open(os.path.join(self.tmp, name), "w").close()
        sm = XeFMStateManager(db_path=os.path.join(self.state_dir, "state.db"))
        self.backend = create_backend("memory")
        self.backend.open()
        self.app = xefm_app.XeFMApp(self.backend, self.tmp, self.tmp,
                                    left_provided=True, right_provided=True,
                                    state_manager=sm)
        self.app.file_monitor.stop_monitoring()
        self.app._settle_listings()
        self.calls = []
        self.app._fileops.trash = lambda panel, t, **kw: self.calls.append(("trash", t, kw))
        self.app._fileops.delete = lambda panel, t, **kw: self.calls.append(("delete", t, kw))
        self._saved = getattr(self.app.config, "DELETE_TO_TRASH", True)

    def tearDown(self):
        self.app.config.DELETE_TO_TRASH = self._saved
        try:
            self.app.file_monitor.stop_monitoring()
            self.backend.close()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def test_k_trashes_where_there_is_a_trash(self):
        with patch.object(trash, "available", return_value=True):
            self.app.delete_files()
        self.assertEqual(self.calls[0][0], "trash")

    def test_k_without_a_trash_deletes_and_says_so(self):
        with patch.object(trash, "available", return_value=False):
            self.app.delete_files()
        kind, _targets, kw = self.calls[0]
        self.assertEqual(kind, "delete")
        self.assertIn(f"no {trash.NAME} here", kw["note"])

    def test_shift_k_always_deletes_for_good(self):
        with patch.object(trash, "available", return_value=True):
            self.app.delete_permanently()
        kind, _targets, kw = self.calls[0]
        self.assertEqual(kind, "delete")
        self.assertIsNone(kw.get("note"))

    def test_delete_to_trash_false_makes_k_permanent(self):
        self.app.config.DELETE_TO_TRASH = False
        with patch.object(trash, "available", return_value=True):
            self.app.delete_files()
        self.assertEqual(self.calls[0][0], "delete")


class EngineTrash(unittest.TestCase):
    """The ``trash`` kind through FileOperationService: one move per target,
    errors reported per target, the confirmation naming the trash."""

    def setUp(self):
        from xefm.file_operations import FileOperationService
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.paths = []
        for name in ("a.txt", "b.txt"):
            p = os.path.join(self.tmp, name)
            open(p, "w").close()
            self.paths.append(p)

        class Config:
            CONFIRM_TRASH = False

        self.service = FileOperationService(Config())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_each_target_is_sent_and_failures_are_kept(self):
        from xefm.path import Path
        sent, results = [], []

        def send(path):
            if str(path).endswith("b.txt"):
                raise OSError(13, "Permission denied", str(path))
            sent.append(str(path))

        with patch.object(trash, "send", send):
            self.service.trash(None, [Path(p) for p in self.paths],
                               on_complete=results.append, background=False)
        self.assertEqual(sent, [self.paths[0]])
        result = results[0]
        self.assertEqual(result["done"], 1)
        self.assertEqual(result["errors"][0][1], "Permission denied")


if __name__ == "__main__":
    unittest.main()
