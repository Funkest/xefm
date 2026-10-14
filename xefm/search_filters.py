"""The search dialog's filter chips (#609): kind, modified date, size.

Three conditions every mode of the search dialog honours — filename search,
content search and the OS index — chosen from a short list rather than written
in any engine's syntax. They are kept apart from the query text: the field
holds what the user typed, the chips hold the conditions, and the two are
combined with AND when a search runs. Nobody has to know that Spotlight spells
"pictures" ``kind:image``.

The meaning of each value lives here, once, as a predicate over what a
listing already knows about an entry (``is_dir``, ``size``, ``mtime`` — the
:mod:`xefm.dir_scan` record), so the walk filters without a second ``stat``.
The OS index's results are paths only, and are stat'ed once each.

The kinds are the ones the three engines agree on, decided by extension here.
That is coarser than Spotlight's content types, and it is the same answer in
every mode, which is the point: a chip must not mean one thing in filename
search and another in the index.

The chips start at "any" every time the dialog opens (``persist=False``), for
the reason the subfolder option does: a search narrowed once must not quietly
narrow the next one.
"""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timezone
from typing import Callable, Optional

from xefm.options import Option

KIND = "kind"
MODIFIED = "modified"
SIZE = "size"

ANY = "any"

#: Kind values, in chip order.
FOLDER = "folder"
DOCUMENT = "document"
IMAGE = "image"
VIDEO = "video"
AUDIO = "audio"
ARCHIVE = "archive"

_EXTENSIONS = {
    DOCUMENT: {
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp",
        "rtf", "txt", "md", "markdown", "csv", "tsv", "pages", "numbers", "key",
        "epub", "tex", "html", "htm",
    },
    IMAGE: {
        "jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp", "heic", "heif",
        "avif", "jxl", "svg", "ico", "psd", "raw", "dng", "cr2", "cr3", "nef",
        "arw", "orf", "rw2",
    },
    VIDEO: {
        "mp4", "m4v", "mov", "avi", "mkv", "webm", "wmv", "flv", "mpg", "mpeg",
        "3gp", "ts", "mts", "m2ts",
    },
    AUDIO: {
        "mp3", "m4a", "aac", "wav", "flac", "ogg", "oga", "opus", "aif", "aiff",
        "wma", "alac", "mid", "midi",
    },
    ARCHIVE: {
        "zip", "tar", "gz", "tgz", "bz2", "tbz", "xz", "txz", "7z", "rar", "zst",
        "lz4", "lzma", "cab", "dmg", "iso", "jar",
    },
}

#: Modified values.
TODAY = "today"
WEEK = "week"
MONTH = "month"
YEAR = "year"

#: Size values, with their lower bounds in bytes.
_SIZES = {"1mb": 1 << 20, "100mb": 100 << 20, "1gb": 1 << 30}

SEARCH_FILTERS = (
    # Labels first: the initial is the key in the options box — k, m, z — and
    # must not collide with the other search options (c, w, r, s).
    Option(KIND, "Kind", flag="Kind", persist=False, choices=(
        (ANY, "Any kind"), (FOLDER, "Folders"), (DOCUMENT, "Documents"),
        (IMAGE, "Images"), (VIDEO, "Videos"), (AUDIO, "Audio"),
        (ARCHIVE, "Archives"))),
    Option(MODIFIED, "Modified", flag="Date", persist=False, choices=(
        (ANY, "Any date"), (TODAY, "Today"), (WEEK, "Past 7 days"),
        (MONTH, "Past 30 days"), (YEAR, "This year"))),
    Option(SIZE, "Size", flag="Size", accel="z", persist=False, choices=(
        (ANY, "Any size"), ("1mb", "1 MB or more"), ("100mb", "100 MB or more"),
        ("1gb", "1 GB or more"))),
)


def kind_of(name: str, is_dir: bool) -> Optional[str]:
    """The kind an entry is, or None when it is none of them."""
    if is_dir:
        return FOLDER
    ext = os.path.splitext(name)[1][1:].lower()
    for kind, exts in _EXTENSIONS.items():
        if ext in exts:
            return kind
    return None


def since(value: str, now: Optional[float] = None) -> Optional[float]:
    """The earliest modification time ``value`` admits, or None for any."""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).date()
    if value == TODAY:
        return datetime.combine(today, datetime.min.time()).timestamp()
    if value == WEEK:
        return now - 7 * 86400
    if value == MONTH:
        return now - 30 * 86400
    if value == YEAR:
        return datetime.combine(date(today.year, 1, 1), datetime.min.time()).timestamp()
    return None


def min_size(value: str) -> Optional[int]:
    return _SIZES.get(value)


def active(values: dict) -> bool:
    """Whether any filter narrows the search."""
    return any(values.get(name, ANY) != ANY for name in (KIND, MODIFIED, SIZE))


def predicate(values: dict, now: Optional[float] = None
              ) -> Optional[Callable[[str, dict], bool]]:
    """``(name, attrs) -> bool`` for the chips in ``values``, or None when
    they are all "any". ``attrs`` is a listing record: ``is_dir``, ``size``,
    ``mtime``. A size condition admits files only — a folder has no size of
    its own to compare."""
    kind = values.get(KIND, ANY)
    floor = since(values.get(MODIFIED, ANY), now)
    least = min_size(values.get(SIZE, ANY))
    if kind == ANY and floor is None and least is None:
        return None

    def keep(name: str, attrs: dict) -> bool:
        is_dir = bool(attrs.get("is_dir"))
        if kind != ANY and kind_of(name, is_dir) != kind:
            return False
        if floor is not None and (attrs.get("mtime") or 0) < floor:
            return False
        if least is not None and (is_dir or (attrs.get("size") or 0) < least):
            return False
        return True
    return keep


def stat_attrs(path: str) -> Optional[dict]:
    """A listing record for one path the OS index returned, or None when it
    is gone (an index lags the disk)."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    import stat as _stat
    return {"is_dir": _stat.S_ISDIR(st.st_mode), "size": st.st_size,
            "mtime": st.st_mtime}


def describe(values: dict) -> str:
    """The chips in force, in words — ``Images · Past 7 days`` — for the
    status line and a results pane's title. Empty when none narrows."""
    words = []
    for option in SEARCH_FILTERS:
        value = values.get(option.name, ANY)
        if value != ANY:
            words.append(option.choice_label(value))
    return " · ".join(words)


# --- the OS index ---------------------------------------------------------------

_SPOTLIGHT_KIND = {
    FOLDER: 'kMDItemContentTypeTree == "public.folder"',
    DOCUMENT: '(kMDItemContentTypeTree == "public.content" && '
              'kMDItemContentTypeTree != "public.image" && '
              'kMDItemContentTypeTree != "public.audiovisual-content")',
    IMAGE: 'kMDItemContentTypeTree == "public.image"',
    VIDEO: 'kMDItemContentTypeTree == "public.movie"',
    AUDIO: 'kMDItemContentTypeTree == "public.audio"',
    ARCHIVE: 'kMDItemContentTypeTree == "public.archive"',
}

_WINDOWS_KIND = {
    FOLDER: "System.Kind = 'folder'",
    DOCUMENT: "System.Kind = 'document'",
    IMAGE: "System.Kind = 'picture'",
    VIDEO: "System.Kind = 'video'",
    AUDIO: "System.Kind = 'music'",
    ARCHIVE: "System.FileExtension IN ('.zip', '.7z', '.rar', '.tar', '.gz', '.tgz', '.xz', '.bz2', '.zst', '.cab', '.iso')",
}


def index_query(engine: str, values: dict, now: Optional[float] = None) -> str:
    """A query the OS index can run on the chips alone, for when the field is
    empty: "every image here changed this week" needs no words. Only ever
    *narrows* what the index returns — every result is still checked against
    :func:`predicate`, so a content type the index files differently from the
    extension table cannot let a wrong one through. Empty when no chip is
    set."""
    kind = values.get(KIND, ANY)
    floor = since(values.get(MODIFIED, ANY), now)
    least = min_size(values.get(SIZE, ANY))
    if engine == "Spotlight":
        terms = []
        if kind != ANY:
            terms.append(_SPOTLIGHT_KIND[kind])
        if floor is not None:
            days = max(0, int((time.time() if now is None else now) - floor) // 86400 + 1)
            terms.append(f"kMDItemFSContentChangeDate >= $time.today(-{days})")
        if least is not None:
            terms.append(f"kMDItemFSSize >= {least}")
        return " && ".join(terms)
    terms = []
    if kind != ANY:
        terms.append(_WINDOWS_KIND[kind])
    if floor is not None:
        # Windows Search compares dates in UTC.
        stamp = datetime.fromtimestamp(floor, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        terms.append(f"System.DateModified >= '{stamp}'")
    if least is not None:
        terms.append(f"System.Size >= {least}")
    return ("where " + " AND ".join(terms)) if terms else ""
