"""The file clipboard (#577, discussion #342): copy or cut now, paste
wherever you go next.

A second, permanent transfer path beside ``C`` / ``M``. Those name a
*spatial* destination — the other pane, visible now; the clipboard a
*temporal* one — the folder you are standing in when you paste, or another
application.

XeFM's own clipboard is the model, on every platform and backend: it holds
``Path`` s, so S3, SSH and archive entries ride it too. A cut is consumed by
the paste that moves it; a copy stays until replaced or cleared.

On the desktop apps (macOS, Windows) the OS clipboard is a bridge to other
applications, through PuiKit's ``clipboard_files``: a copy of local files
also goes there, and files copied in Finder or Explorer can be pasted here.
Which one a paste takes is decided by the OS clipboard's change count — if
anything has written it since XeFM did, and it holds files, those are newer
than what XeFM holds. In a terminal and on Linux the PuiKit calls are no-ops,
so XeFM's own clipboard is the only one, by design.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Optional

from xefm.path import Path


@dataclass(frozen=True)
class Contents:
    """What a paste would take: ``paths``, whether it moves them, and where
    they came from (``"xefm"`` or ``"os"`` — another application)."""

    paths: tuple
    cut: bool
    origin: str

    @property
    def from_other_app(self) -> bool:
        return self.origin == "os"


class FileClipboard:
    """XeFM's clipboard, with the OS clipboard as a bridge where the panel
    has one. ``version`` changes on every change, for callers that cache what
    they derive from it (a pane footer's conflict count)."""

    def __init__(self, panel=None):
        self.panel = panel
        self.paths: list = []
        self.cut = False
        self.version = 0
        #: The OS clipboard's change count as of XeFM's last copy, cut or clear
        #: — whether or not XeFM wrote it then (S3 paths cannot go there). The
        #: OS clipboard counts as newer only once it has moved past this.
        self._os_count: Optional[int] = None
        self._os_cache: tuple = (None, None)   # (change count, ClipboardFiles | None)

    # --- writing ---------------------------------------------------------------

    def put(self, paths, *, cut: bool, local_paths=None) -> bool:
        """Hold ``paths`` (cut or copied). ``local_paths`` — the ones that
        exist on this machine's filesystem — go to the OS clipboard too, where
        there is one. Returns True when they reached it."""
        self.paths = list(paths)
        self.cut = cut
        self.version += 1
        reached = False
        if local_paths and self._bridge("set_clipboard_files") is not None:
            reached = bool(self.panel.set_clipboard_files(list(local_paths), cut=cut))
        self._mark_seen()
        return reached

    def clear(self) -> None:
        self.paths = []
        self.cut = False
        self.version += 1
        self._mark_seen()

    def consume(self) -> None:
        """A cut has been pasted: its files are gone from where they were."""
        if self.cut:
            self.clear()

    def take_os(self) -> None:
        """The OS clipboard's files have been pasted: what XeFM holds is now
        older than nothing, so the next paste looks at the OS clipboard only
        if it changes again."""
        self._mark_seen()
        self.version += 1

    def _mark_seen(self) -> None:
        count_of = self._bridge("clipboard_change_count")
        self._os_count = count_of() if count_of is not None else None

    # --- reading ---------------------------------------------------------------

    def _bridge(self, name: str):
        """The panel's file-clipboard call ``name``, or None on a PuiKit that
        predates it (or with no panel, in a bare test)."""
        return getattr(self.panel, name, None) if self.panel is not None else None

    def _os_files(self):
        """The OS clipboard's files when another application put them there
        after XeFM last wrote — read once per change count, not per frame."""
        count_of = self._bridge("clipboard_change_count")
        if count_of is None:
            return None
        count = count_of()
        if count is None or count == self._os_count:
            return None
        cached_count, files = self._os_cache
        if cached_count != count:
            files = self.panel.get_clipboard_files()
            self._os_cache = (count, files)
        return files if files and files.paths else None

    def superseded(self) -> bool:
        """Whether the OS clipboard has changed since XeFM last wrote it — text
        copied anywhere, XeFM's own log included, or files from another
        application. It is one clipboard: the newest copy is the one held, so
        what XeFM holds no longer counts. Never true without an OS bridge."""
        count_of = self._bridge("clipboard_change_count")
        if count_of is None:
            return False
        count = count_of()
        return count is not None and count != self._os_count

    def contents(self) -> Optional[Contents]:
        """What a paste would take now, or None when there is nothing."""
        files = self._os_files()
        if files is not None:
            return Contents(tuple(Path(p) for p in files.paths), bool(files.cut), "os")
        if self.paths and not self.superseded():
            return Contents(tuple(self.paths), self.cut, "xefm")
        return None

    def marks(self) -> frozenset:
        """``str`` of every path XeFM holds, for marking rows — none once a
        newer copy has replaced them."""
        if not self.paths or self.superseded():
            return frozenset()
        return frozenset(str(p) for p in self.paths)

    def status(self) -> str:
        """The status bar's segment: ``[COPY 3]``, ``[CUT 1]``, ``[2 from
        another app]`` — empty when nothing is held."""
        c = self.contents()
        if c is None:
            return ""
        n = len(c.paths)
        if c.from_other_app:
            return f"[{'CUT ' if c.cut else ''}{n} from another app]"
        return f"[{'CUT' if c.cut else 'COPY'} {n}]"


def _key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def conflicts(contents: Optional[Contents], dest_dir, listed_names) -> int:
    """How many of ``contents`` would meet an existing name in ``dest_dir``,
    judged from ``listed_names`` — the names the pane already shows, so the
    preview costs no I/O. An item already in ``dest_dir`` is not a conflict:
    pasting a cut there does nothing, and pasting a copy makes a second one."""
    if contents is None:
        return 0
    names = {_key(n) for n in listed_names}
    dest = str(dest_dir)
    return sum(1 for p in contents.paths
               if str(p.parent) != dest and _key(p.name) in names)
