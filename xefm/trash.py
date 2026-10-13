"""Deleting to the operating system's trash (#591, discussion #468 §2).

``K`` used to remove files for good. It now sends them where the system keeps
deleted files, so they can be restored from Finder, Explorer or the desktop's
file manager, and the old behaviour stays one key away
(``delete_permanently``). Each platform's own mechanism is used — nothing here
keeps a private trash:

- **macOS** — ``NSFileManager trashItemAtURL:``, which is what Finder calls:
  the item lands in the Trash of its volume and *Put Back* knows where it came
  from. PyObjC comes with PuiKit on macOS, terminal installs included.
- **Windows** — ``SHFileOperationW`` with ``FOF_ALLOWUNDO``: the Recycle Bin.
  Only on fixed drives: on a USB stick or a network share the same call
  *deletes permanently without saying so*, so those report no trash here and
  ``K`` asks for a permanent delete instead. ``FOF_WANTNUKEWARNING`` is a
  second guard should the shell decide to nuke a file anyway.
- **Linux and other freedesktop systems** — the Trash specification, written
  out here: the file is renamed into ``files/`` of the trash for its volume,
  next to an ``info/<name>.trashinfo`` recording where it was and when, which
  is what GNOME Files, Dolphin and ``gio trash --restore`` read. Home trash
  for the home volume; ``$topdir/.Trash/$uid`` or ``$topdir/.Trash-$uid`` for
  any other.

Remote locations and archive members have no trash: :func:`available` says
so, and the caller deletes permanently after saying that it will.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
import time
import urllib.parse
from pathlib import Path as LocalPath
from typing import Optional

from xefm.log_manager import getLogger

logger = getLogger("Trash")

#: What the platform calls it, for messages.
NAME = {"darwin": "Trash", "win32": "Recycle Bin"}.get(sys.platform, "Trash")


def _local(path) -> Optional[str]:
    text = str(path)
    return None if "://" in text else text


# --- macOS ----------------------------------------------------------------------

def _mac_manager():
    try:
        from Foundation import NSURL, NSFileManager
    except ImportError:
        return None
    return NSFileManager.defaultManager(), NSURL


def _trash_macos(path: str) -> None:
    pair = _mac_manager()
    if pair is None:
        raise OSError(errno.ENOTSUP, "the Trash needs PyObjC (Foundation)", path)
    manager, nsurl = pair
    ok, _where, error = manager.trashItemAtURL_resultingItemURL_error_(
        nsurl.fileURLWithPath_(path), None, None)
    if not ok:
        message = error.localizedDescription() if error is not None else "failed"
        raise OSError(errno.EIO, str(message), path)


# --- Windows --------------------------------------------------------------------

_FO_DELETE = 3
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400
_FOF_WANTNUKEWARNING = 0x4000
_DRIVE_FIXED = 3


def _windows_fixed_drive(path: str) -> bool:
    import ctypes
    root = os.path.splitdrive(os.path.abspath(path))[0]
    if not root or root.startswith("\\\\"):
        return False  # a UNC share: no Recycle Bin
    return ctypes.windll.kernel32.GetDriveTypeW(root + "\\") == _DRIVE_FIXED


def _trash_windows(path: str) -> None:
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", wintypes.LPCWSTR)]

    # pFrom is a list of paths, each NUL-terminated, the list ending in a
    # second NUL; the buffer's own terminator supplies the last one.
    source = ctypes.create_unicode_buffer(os.path.abspath(path) + "\0")
    op = SHFILEOPSTRUCTW(None, _FO_DELETE, ctypes.cast(source, wintypes.LPCWSTR), None,
                         _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT
                         | _FOF_NOERRORUI | _FOF_WANTNUKEWARNING, False, None, None)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code != 0 or op.fAnyOperationsAborted:
        raise OSError(errno.EIO, f"the Recycle Bin refused it (code {code:#x})", path)


# --- freedesktop ----------------------------------------------------------------

def _home_trash() -> LocalPath:
    data = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"),
                                                           ".local", "share")
    return LocalPath(data) / "Trash"


def _mount_point(path: str) -> str:
    path = os.path.realpath(os.path.dirname(os.path.abspath(path)) or "/")
    dev = os.lstat(path).st_dev
    while True:
        parent = os.path.dirname(path)
        if parent == path or os.lstat(parent).st_dev != dev:
            return path
        path = parent


def _ensure(directory: LocalPath) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    (directory / "files").mkdir(exist_ok=True, mode=0o700)
    (directory / "info").mkdir(exist_ok=True, mode=0o700)


def freedesktop_trash_for(path: str) -> tuple[LocalPath, Optional[str]]:
    """The trash directory ``path`` goes to, and the directory its recorded
    path is relative to (None for the home trash, which records absolute
    paths). Raises OSError when the volume has no usable trash."""
    dev = os.lstat(path).st_dev
    home = _home_trash()
    try:
        _ensure(home)
        if os.stat(home).st_dev == dev:
            return home, None
    except OSError:
        pass
    top = _mount_point(path)
    uid = os.getuid()
    shared = LocalPath(top) / ".Trash"
    try:
        st = os.lstat(shared)
        if stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode) \
                and st.st_mode & stat.S_ISVTX:
            candidate = shared / str(uid)
            _ensure(candidate)
            return candidate, top
    except OSError:
        pass
    candidate = LocalPath(top) / f".Trash-{uid}"
    _ensure(candidate)
    if os.stat(candidate).st_dev != dev:
        raise OSError(errno.EXDEV, "this volume has no trash", path)
    return candidate, top


def _trash_freedesktop(path: str, now: Optional[float] = None) -> str:
    """Move ``path`` into its trash; returns the name it was given there."""
    path = os.path.abspath(path)
    trash, top = freedesktop_trash_for(path)
    recorded = os.path.relpath(path, top) if top else path
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now))
    body = ("[Trash Info]\nPath=" + urllib.parse.quote(recorded, safe="/")
            + f"\nDeletionDate={stamp}\n").encode("utf-8")
    base = os.path.basename(path.rstrip(os.sep)) or "item"
    stem, dot, ext = base.partition(".") if not base.startswith(".") else (base, "", "")
    for n in range(1, 10000):
        name = base if n == 1 else (f"{stem}.{n}{dot}{ext}" if dot else f"{base}.{n}")
        info = trash / "info" / f"{name}.trashinfo"
        try:
            fd = os.open(info, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        target = trash / "files" / name
        if os.path.lexists(target):
            os.unlink(info)
            continue
        try:
            os.rename(path, target)
        except OSError:
            os.unlink(info)
            raise
        return name
    raise OSError(errno.EEXIST, "too many items of this name in the trash", path)


# --- the API --------------------------------------------------------------------

def available(path) -> bool:
    """Whether ``path`` can go to the system's trash — a local item on a
    volume that has one. Cheap: decides from the path and the platform, and on
    Windows the drive type; a freedesktop volume whose trash cannot be made is
    found out by :func:`send`."""
    local = _local(path)
    if local is None:
        return False
    if sys.platform == "darwin":
        return _mac_manager() is not None
    if sys.platform == "win32":
        try:
            return _windows_fixed_drive(local)
        except Exception:  # noqa: BLE001 — no answer is no trash
            return False
    return os.name == "posix"


def send(path) -> None:
    """Move ``path`` (a file or a whole directory) to the system's trash.
    Raises OSError with the reason when it cannot; nothing is deleted then."""
    local = _local(path)
    if local is None:
        raise OSError(errno.ENOTSUP, "remote and archived items have no trash", str(path))
    if sys.platform == "darwin":
        _trash_macos(local)
    elif sys.platform == "win32":
        _trash_windows(local)
    else:
        _trash_freedesktop(local)
    logger.info(f"Moved to {NAME}: {local}")
