"""A permanent delete removes read-only entries on Windows.

Windows refuses to remove a file or directory that carries the read-only
attribute — ``[WinError 5] Access is denied``, whatever the caller's rights —
and XeFM passed the refusal on: nothing in a Google Drive for desktop mirror,
which marks every directory read-only, could be deleted (issue #759). The
local removals now clear the attribute and try once more, and only after
Windows has refused.

The attribute needs no privilege to set (``SetFileAttributesW``), so these run
on any Windows checkout; elsewhere they skip.

Run with: python -m pytest test/test_readonly_delete.py -v
"""

import ctypes
import os
import shutil
import stat
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from xefm import _config  # noqa: E402
from xefm import path as xefm_path  # noqa: E402
from xefm.file_operations import FileOperationService, recursive_delete  # noqa: E402
from xefm.path import Path, move_to  # noqa: E402

_WINDOWS = sys.platform == "win32"

FILE_ATTRIBUTE_READONLY = 0x01
FILE_ATTRIBUTE_HIDDEN = 0x02


def _mark(path, attributes):
    """Set Windows file attributes on ``path``, the way ``attrib +r`` does."""
    if not ctypes.windll.kernel32.SetFileAttributesW(str(path), attributes):
        raise ctypes.WinError(ctypes.get_last_error())


def _attributes(path):
    return os.lstat(path).st_file_attributes


def _denied(*args, **kwargs):
    exc = PermissionError(13, "Access is denied")
    exc.winerror = 5
    raise exc


class ReadOnlyTestBase(unittest.TestCase):
    """A temp directory to mark entries in, emptied of marks before removal."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._remove_tmp)

    def _remove_tmp(self):
        # What a test leaves read-only would keep rmtree from removing it.
        for root, dirs, files in os.walk(self.tmp):
            for name in dirs + files:
                _mark(os.path.join(root, name), 0x80)  # FILE_ATTRIBUTE_NORMAL
        shutil.rmtree(self.tmp, True)

    def make(self, *parts, directory=False, attributes=FILE_ATTRIBUTE_READONLY):
        path = os.path.join(self.tmp, *parts)
        if directory:
            os.mkdir(path)
        else:
            with open(path, "w") as f:
                f.write("x")
        if attributes:
            _mark(path, attributes)
        return path

    def tree(self):
        """tree/ (read-only) holding ro/ (read-only) with ro.txt (read-only)
        and plain.txt, plain/, and top.txt (read-only)."""
        root = self.make("tree", directory=True, attributes=0)
        self.make("tree", "ro", directory=True, attributes=0)
        self.make("tree", "ro", "ro.txt")
        self.make("tree", "ro", "plain.txt", attributes=0)
        self.make("tree", "plain", directory=True, attributes=0)
        self.make("tree", "top.txt")
        _mark(os.path.join(root, "ro"), FILE_ATTRIBUTE_READONLY)
        _mark(root, FILE_ATTRIBUTE_READONLY)
        return root


# ---------------------------------------------------------------------------
# What is removed now
# ---------------------------------------------------------------------------


@unittest.skipUnless(_WINDOWS, "the read-only attribute is Windows-only")
class AReadOnlyEntryIsRemoved(ReadOnlyTestBase):
    def test_pathlib_alone_refuses_it(self):
        # What this is about: the plain removal fails.
        d = self.make("ro", directory=True)
        with self.assertRaises(PermissionError):
            os.rmdir(d)

    def test_a_directory(self):
        d = self.make("ro", directory=True)
        Path(d).rmdir()
        self.assertFalse(os.path.exists(d))

    def test_a_file(self):
        f = self.make("ro.txt")
        Path(f).unlink()
        self.assertFalse(os.path.exists(f))

    def test_a_tree_by_the_permanent_delete(self):
        cfg = _config.Config()
        cfg.CONFIRM_DELETE = False
        result = {}
        root = self.tree()
        FileOperationService(cfg).delete(None, [Path(root)], on_complete=result.update,
                                         background=False)
        self.assertEqual(result["errors"], [])
        self.assertFalse(os.path.exists(root))

    def test_a_tree_by_the_sync_delete(self):
        root = self.tree()
        recursive_delete(Path(root))
        self.assertFalse(os.path.exists(root))

    def test_a_tree_moved_to_another_filesystem(self):
        # The copy + delete a move takes when a rename can't cross devices.
        root = self.tree()
        dest = os.path.join(self.tmp, "moved")
        with mock.patch.object(xefm_path.LocalPathImpl, "rename",
                               side_effect=OSError(18, "cross-device link")):
            self.assertTrue(move_to(Path(root), Path(dest)))
        self.assertFalse(os.path.exists(root))
        self.assertTrue(os.path.exists(os.path.join(dest, "ro", "ro.txt")))


# ---------------------------------------------------------------------------
# What is left alone
# ---------------------------------------------------------------------------


@unittest.skipUnless(_WINDOWS, "the read-only attribute is Windows-only")
class OnlyARefusalForTheAttributeIsRetried(ReadOnlyTestBase):
    def test_a_removal_that_works_touches_no_attribute(self):
        d = self.make("d", directory=True, attributes=0)
        f = self.make("f.txt", attributes=0)
        with mock.patch.object(xefm_path.os, "chmod") as chmod:
            Path(f).unlink()
            Path(d).rmdir()
        chmod.assert_not_called()

    def test_a_file_in_use_is_left_alone(self):
        # Open without delete sharing, it is refused as a sharing violation
        # (WinError 32), not for being read-only.
        f = self.make("ro.txt")
        with open(f), mock.patch.object(xefm_path.os, "chmod") as chmod:
            with self.assertRaises(PermissionError):
                Path(f).unlink()
        chmod.assert_not_called()
        self.assertTrue(_attributes(f) & FILE_ATTRIBUTE_READONLY)

    def test_a_second_refusal_puts_the_attribute_back(self):
        # The entry stays, so it stays as it was: read-only again, Hidden
        # untouched, and tried only once more.
        f = self.make("ro.txt", attributes=FILE_ATTRIBUTE_READONLY | FILE_ATTRIBUTE_HIDDEN)
        with mock.patch.object(type(Path(f)._impl._path), "unlink",
                               autospec=True, side_effect=_denied) as unlink:
            with self.assertRaises(PermissionError):
                Path(f).unlink()
        self.assertEqual(unlink.call_count, 2)
        self.assertEqual(_attributes(f) & (FILE_ATTRIBUTE_READONLY | FILE_ATTRIBUTE_HIDDEN),
                         FILE_ATTRIBUTE_READONLY | FILE_ATTRIBUTE_HIDDEN)

    def test_a_symlink_goes_and_its_target_keeps_the_attribute(self):
        target = self.make("target.txt")
        link = os.path.join(self.tmp, "link.txt")
        try:
            os.symlink(target, link)
        except OSError:
            self.skipTest("a symlink needs Developer Mode or elevation here")
        Path(link).unlink()
        self.assertFalse(os.path.lexists(link))
        self.assertTrue(_attributes(target) & FILE_ATTRIBUTE_READONLY)


if __name__ == "__main__":
    unittest.main()
