"""File tags, kept where the operating system keeps them (#585).

The principle from discussion #475: where the OS already has tags, XeFM reads
and writes the OS's own, so a tag added here shows up in Finder (or Dolphin, or
the S3 console) and the other way round. There is no XeFM-private tag database.

A :class:`TagStore` is one place tags live, chosen per path by
:func:`store_for` — the same capability-based pattern as path backends:

- **Finder tags** (macOS, local files): the
  ``com.apple.metadata:_kMDItemUserTags`` extended attribute, a binary plist of
  ``"Name\\n<color>"`` strings. Spotlight indexes it as ``kMDItemUserTags``.
  Colors are read, shown and kept; a new tag named like a Finder color ("Red")
  takes that color, as it does in Finder.
- **XDG tags** (Linux, local files): ``user.xdg.tags``, comma-separated — what
  KDE's Dolphin and Baloo use. Names only.
- **S3 object tags**: a tag is a key with an empty value; key–value tags with a
  value are someone else's and are kept untouched. One request per object, so
  the file list does not show them; the tag dialog and find-by-tag still work.

Everywhere else — Windows, SSH, archives — there is no store, and the tag
features say so instead of keeping a private copy that would drift from the
files. A fallback (state.db or NTFS streams) is a later decision.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import errno
import os
import plistlib
import sys
from dataclasses import dataclass
from typing import Iterable, Optional

from xefm.log_manager import getLogger

logger = getLogger("Tags")

#: Finder's color indices, in the order Finder's own tag menu lists them.
COLORS = {0: None, 1: "gray", 2: "green", 3: "purple", 4: "blue",
          5: "yellow", 6: "red", 7: "orange"}
#: A new tag with one of these names gets the matching color, as in Finder.
_COLOR_BY_NAME = {"gray": 1, "grey": 1, "green": 2, "purple": 3, "blue": 4,
                  "yellow": 5, "red": 6, "orange": 7}
#: RGB for drawing each color's marker; ``None`` (no color) uses the muted ink.
RGB = {"gray": (142, 142, 147), "green": (52, 199, 89), "purple": (175, 82, 222),
       "blue": (0, 122, 255), "yellow": (255, 204, 0), "red": (255, 59, 48),
       "orange": (255, 149, 0)}


@dataclass(frozen=True)
class Tag:
    name: str
    #: Finder color index (0 = none). Stores without colors use 0.
    color: int = 0

    @property
    def color_name(self) -> Optional[str]:
        return COLORS.get(self.color)


class TagError(OSError):
    """A tag store could not read or write a file's tags."""


class TagStore:
    """Where one kind of path keeps its tags."""

    #: Short name for messages ("Finder tags").
    label = ""
    #: Whether reading is cheap enough to do for every visible row.
    cheap = True
    #: Whether the store keeps a color per tag.
    has_colors = False

    def read(self, path) -> list[Tag]:
        raise NotImplementedError

    def write(self, path, tags: list[Tag]) -> None:
        raise NotImplementedError

    def find(self, root, name: str, *, checkpoint=lambda: None) -> Optional[list[str]]:
        """Paths under ``root`` tagged ``name`` by an index, or None when this
        store has no index (the caller walks instead)."""
        return None

    def read_many(self, paths: list) -> dict[str, list[Tag]]:
        """Tags of several paths, keyed by ``str(path)``; a path that could not
        be read maps to its :class:`TagError` instead. Stores that pay per
        call (SSH) override this to ask once."""
        out: dict = {}
        for path in paths:
            try:
                out[str(path)] = self.read(path)
            except (TagError, OSError) as exc:
                out[str(path)] = exc
        return out

    def write_many(self, changes: list) -> list[str]:
        """Write ``(path, tags)`` pairs; return one message per failure."""
        failed = []
        for path, tags in changes:
            try:
                self.write(path, tags)
            except (TagError, OSError) as exc:
                failed.append(f"{path}: {exc}")
        return failed


# --- macOS: Finder tags ------------------------------------------------------

_FINDER_ATTR = b"com.apple.metadata:_kMDItemUserTags"
_ENOATTR = 93  # macOS errno for "attribute not found"


def _libc():
    lib = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    lib.getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                             ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.getxattr.restype = ctypes.c_ssize_t
    lib.setxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p,
                             ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    lib.setxattr.restype = ctypes.c_int
    lib.removexattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    lib.removexattr.restype = ctypes.c_int
    return lib


def parse_finder(data: bytes) -> list[Tag]:
    """Finder's xattr value — a plist array of ``"Name"`` or ``"Name\\nN"`` —
    as tags."""
    try:
        items = plistlib.loads(data)
    except Exception:  # noqa: BLE001 — a malformed value is "no tags", not a crash
        return []
    tags = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, str) or not item:
            continue
        name, _, color = item.partition("\n")
        tags.append(Tag(name, int(color) if color.isdigit() and int(color) in COLORS else 0))
    return tags


def format_finder(tags: Iterable[Tag]) -> bytes:
    return plistlib.dumps([f"{t.name}\n{t.color}" if t.color else t.name for t in tags],
                          fmt=plistlib.FMT_BINARY)


class FinderTags(TagStore):
    label = "Finder tags"
    has_colors = True

    def __init__(self):
        self._lib = _libc()

    def read(self, path) -> list[Tag]:
        p = os.fsencode(str(path))
        size = self._lib.getxattr(p, _FINDER_ATTR, None, 0, 0, 0)
        if size < 0:
            err = ctypes.get_errno()
            if err == _ENOATTR:
                return []
            raise TagError(err, os.strerror(err), str(path))
        buf = ctypes.create_string_buffer(size)
        got = self._lib.getxattr(p, _FINDER_ATTR, buf, size, 0, 0)
        if got < 0:
            err = ctypes.get_errno()
            if err == _ENOATTR:
                return []
            raise TagError(err, os.strerror(err), str(path))
        return parse_finder(buf.raw[:got])

    def write(self, path, tags: list[Tag]) -> None:
        p = os.fsencode(str(path))
        if not tags:
            if self._lib.removexattr(p, _FINDER_ATTR, 0) != 0:
                err = ctypes.get_errno()
                if err != _ENOATTR:
                    raise TagError(err, os.strerror(err), str(path))
            return
        data = format_finder(tags)
        if self._lib.setxattr(p, _FINDER_ATTR, data, len(data), 0, 0) != 0:
            err = ctypes.get_errno()
            raise TagError(err, os.strerror(err), str(path))

    def find(self, root, name: str, *, checkpoint=lambda: None) -> Optional[list[str]]:
        """Spotlight's answer, or None when Spotlight cannot give one (not
        installed, or the volume is not indexed — an empty answer is treated the
        same, so the caller's walk decides)."""
        import subprocess
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        try:
            out = subprocess.run(
                ["mdfind", "-onlyin", str(root), f"kMDItemUserTags == '{escaped}'"],
                capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        paths = [line for line in out.stdout.splitlines() if line]
        return paths or None


# --- Linux: user.xdg.tags ----------------------------------------------------

_XDG_ATTR = "user.xdg.tags"


class XdgTags(TagStore):
    label = "tags"

    def read(self, path) -> list[Tag]:
        try:
            raw = os.getxattr(str(path), _XDG_ATTR)
        except OSError as exc:
            if exc.errno in (errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)):
                return []
            raise TagError(exc.errno, exc.strerror, str(path)) from None
        names = raw.decode("utf-8", "replace").split(",")
        return [Tag(n.strip()) for n in names if n.strip()]

    def write(self, path, tags: list[Tag]) -> None:
        try:
            if tags:
                os.setxattr(str(path), _XDG_ATTR,
                            ",".join(t.name for t in tags).encode("utf-8"))
            else:
                try:
                    os.removexattr(str(path), _XDG_ATTR)
                except OSError as exc:
                    if exc.errno not in (errno.ENODATA,
                                         getattr(errno, "ENOATTR", errno.ENODATA)):
                        raise
        except OSError as exc:
            raise TagError(exc.errno, exc.strerror, str(path)) from None


# --- Windows: an NTFS alternate data stream -----------------------------------
#
# Windows has no filesystem-wide tags (Explorer's "Tags" are a property inside
# certain file formats), so XeFM keeps them in a named stream on the file
# itself: any file type can carry one, it travels with the file on renames and
# moves within NTFS, and Explorer and other programs never see it. It is lost
# on a copy to FAT/exFAT, cloud folders or archives — XeFM's own copies carry
# it (:func:`carry`), other tools may not.

_ADS = ":xefm.tags"


class NtfsStreamTags(TagStore):
    label = "tags"
    has_colors = True   # kept, so a Finder color survives a round trip

    def read(self, path) -> list[Tag]:
        import json
        try:
            with open(str(path) + _ADS, "rb") as f:
                data = json.loads(f.read().decode("utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as exc:
            raise TagError(getattr(exc, "errno", errno.EIO) or errno.EIO,
                           str(exc), str(path)) from None
        return [Tag(str(t.get("name", "")), int(t.get("color", 0)))
                for t in data if isinstance(t, dict) and t.get("name")]

    def write(self, path, tags: list[Tag]) -> None:
        import json
        stream = str(path) + _ADS
        try:
            if tags:
                payload = json.dumps([{"name": t.name, "color": t.color} for t in tags],
                                     ensure_ascii=False).encode("utf-8")
                with open(stream, "wb") as f:
                    f.write(payload)
            else:
                try:
                    os.remove(stream)
                except FileNotFoundError:
                    pass
        except OSError as exc:
            raise TagError(exc.errno or errno.EIO,
                           f"{exc.strerror or exc} (tags need an NTFS volume)",
                           str(path)) from None


# --- SSH: the remote host's own tags, through a remote command ----------------
#
# SFTP v3 has no extended attributes, but XeFM's ssh runs with BatchMode (key
# authentication, never a prompt), so a second ssh process can run the remote
# system's own tools: getfattr/setfattr on Linux (user.xdg.tags), xattr on
# macOS (Finder tags). Every call is a round trip, so the file list does not
# show SSH tags and every operation batches all its files into one command.

_FINDER_ATTR_STR = _FINDER_ATTR.decode()
_PROBE = ("uname -s; command -v getfattr >/dev/null 2>&1 && echo getfattr; "
          "command -v setfattr >/dev/null 2>&1 && echo setfattr; "
          "command -v xattr >/dev/null 2>&1 && echo xattr; "
          "command -v mdfind >/dev/null 2>&1 && echo mdfind")


def _unescape_getfattr(text: str) -> str:
    """A getfattr ``-e text`` value: quoted, with octal escapes for bytes."""
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    raw = bytearray()
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 3 < len(text) + 1 and text[i + 1:i + 4].isdigit():
            raw.append(int(text[i + 1:i + 4], 8))
            i += 4
        elif c == "\\" and i + 1 < len(text):
            raw.extend(text[i + 1].encode())
            i += 2
        else:
            raw.extend(c.encode("utf-8"))
            i += 1
    return raw.decode("utf-8", "replace")


class SshTags(TagStore):
    label = "tags (over SSH)"
    cheap = False
    has_colors = True

    def __init__(self):
        self._hosts: dict[str, tuple[str, set]] = {}

    @staticmethod
    def _where(path):
        impl = getattr(path, "_impl", path)
        return impl._get_connection(), impl.remote_path, impl.hostname

    def _run(self, conn, command: str) -> "subprocess.CompletedProcess":
        try:
            return conn.run_remote(command)
        except Exception as exc:  # noqa: BLE001 — timeout, ssh missing
            raise TagError(errno.EIO, f"ssh failed: {exc}", conn.hostname) from None

    def _system(self, conn, host: str) -> tuple[str, set]:
        if host not in self._hosts:
            result = self._run(conn, _PROBE)
            lines = result.stdout.decode("utf-8", "replace").split()
            self._hosts[host] = (lines[0] if lines else "", set(lines[1:]))
        return self._hosts[host]

    def _tools(self, conn, host: str, *needed: str) -> str:
        system, tools = self._system(conn, host)
        missing = [t for t in needed if t not in tools]
        if system not in ("Linux", "Darwin"):
            raise TagError(errno.ENOTSUP, f"tags are not supported on a {system or 'unknown'} host",
                           host)
        if missing:
            hint = " (the 'attr' package)" if system == "Linux" else ""
            raise TagError(errno.ENOTSUP, f"{', '.join(missing)} is not installed on "
                           f"{host}{hint}", host)
        return system

    def read(self, path) -> list[Tag]:
        result = self.read_many([path])[str(path)]
        if isinstance(result, Exception):
            raise result
        return result

    def write(self, path, tags: list[Tag]) -> None:
        failed = self.write_many([(path, tags)])
        if failed:
            raise TagError(errno.EIO, failed[0], str(path))

    def _by_host(self, items, key=lambda x: x):
        groups: dict = {}
        for item in items:
            conn, remote, host = self._where(key(item))
            groups.setdefault(host, (conn, []))[1].append((item, remote))
        return groups

    def read_many(self, paths: list) -> dict:
        import shlex
        out: dict = {}
        for host, (conn, items) in self._by_host(paths).items():
            try:
                system = self._tools(conn, host, "getfattr" if self._system(conn, host)[0]
                                     == "Linux" else "xattr")
            except TagError as exc:
                for path, _ in items:
                    out[str(path)] = exc
                continue
            if system == "Linux":
                body = ('printf "%s\\0" "$f"; getfattr --only-values -n user.xdg.tags '
                        '-- "$f" 2>/dev/null; printf "\\0"')
            else:
                body = (f'printf "%s\\0" "$f"; xattr -px {_FINDER_ATTR_STR} "$f" '
                        '2>/dev/null | tr -d " \\n"; printf "\\0"')
            script = f'for f in "$@"; do {body}; done'
            command = "sh -c " + shlex.quote(script) + " sh " + " ".join(
                shlex.quote(remote) for _, remote in items)
            result = self._run(conn, command)
            fields = result.stdout.split(b"\0")
            values = dict(zip(fields[0::2], fields[1::2]))
            for path, remote in items:
                raw = values.get(remote.encode("utf-8"), b"")
                if system == "Linux":
                    names = raw.decode("utf-8", "replace").split(",")
                    out[str(path)] = [Tag(n.strip()) for n in names if n.strip()]
                else:
                    try:
                        out[str(path)] = parse_finder(bytes.fromhex(raw.decode())) if raw else []
                    except ValueError:
                        out[str(path)] = []
        return out

    def write_many(self, changes: list) -> list[str]:
        import shlex
        failed: list[str] = []
        for host, (conn, items) in self._by_host(changes, key=lambda c: c[0]).items():
            linux = self._system(conn, host)[0] == "Linux"
            try:
                self._tools(conn, host, "setfattr" if linux else "xattr")
            except TagError as exc:
                failed += [f"{path}: {exc.strerror}" for (path, _), _ in items]
                continue
            lines = []
            for (path, tags), remote in items:
                q = shlex.quote(remote)
                if linux and tags:
                    value = shlex.quote(",".join(t.name for t in tags))
                    cmd = f"setfattr -n user.xdg.tags -v {value} -- {q}"
                elif linux:
                    cmd = f"{{ setfattr -x user.xdg.tags -- {q} 2>/dev/null || true; }}"
                elif tags:
                    cmd = f"xattr -wx {_FINDER_ATTR_STR} {format_finder(tags).hex()} {q}"
                else:
                    cmd = f"{{ xattr -d {_FINDER_ATTR_STR} {q} 2>/dev/null || true; }}"
                lines.append(f"{cmd} || printf '%s\\n' {q}")
            result = self._run(conn, "\n".join(lines))
            bad = set(result.stdout.decode("utf-8", "replace").splitlines())
            failed += [f"{path}: could not set tags on {host}"
                       for (path, _), remote in items if remote in bad]
        return failed

    def find(self, root, name: str, *, checkpoint=lambda: None) -> Optional[list[str]]:
        import shlex
        conn, remote, host = self._where(root)
        system, tools = self._system(conn, host)
        if system == "Darwin" and "mdfind" in tools:
            escaped = name.replace("\\", "\\\\").replace("'", "\\'")
            command = (f"mdfind -onlyin {shlex.quote(remote)} "
                       + shlex.quote(f"kMDItemUserTags == '{escaped}'"))
            lines = self._run(conn, command).stdout.decode("utf-8", "replace").splitlines()
            return [f"ssh://{host}{p}" for p in lines if p] or None
        if system == "Linux" and "getfattr" in tools:
            command = (f"getfattr -R --absolute-names -n user.xdg.tags -- "
                       f"{shlex.quote(remote)} 2>/dev/null")
            text = self._run(conn, command).stdout.decode("utf-8", "replace")
            hits, current = [], None
            for line in text.splitlines():
                if line.startswith("# file: "):
                    current = _unescape_getfattr(line[len("# file: "):])
                elif line.startswith("user.xdg.tags=") and current:
                    names = _unescape_getfattr(line.split("=", 1)[1]).split(",")
                    if any(n.strip().casefold() == name.casefold() for n in names):
                        hits.append(f"ssh://{host}{current}")
            return hits
        return None


# --- S3 object tagging -------------------------------------------------------

class S3Tags(TagStore):
    label = "S3 object tags"
    cheap = False

    @staticmethod
    def _impl(path):
        return getattr(path, "_impl", path)

    def _get(self, path) -> list[dict]:
        impl = self._impl(path)
        try:
            response = impl._client().get_object_tagging(Bucket=impl._bucket, Key=impl._key)
        except Exception as exc:  # noqa: BLE001 — boto errors are not OSError
            raise TagError(errno.EIO, str(exc), str(path)) from None
        return list(response.get("TagSet", []))

    def read(self, path) -> list[Tag]:
        return [Tag(t["Key"]) for t in self._get(path) if t.get("Value", "") == ""]

    def write(self, path, tags: list[Tag]) -> None:
        impl = self._impl(path)
        others = [t for t in self._get(path) if t.get("Value", "") != ""]
        tag_set = others + [{"Key": t.name, "Value": ""} for t in tags]
        try:
            if tag_set:
                impl._client().put_object_tagging(
                    Bucket=impl._bucket, Key=impl._key, Tagging={"TagSet": tag_set})
            else:
                impl._client().delete_object_tagging(Bucket=impl._bucket, Key=impl._key)
        except Exception as exc:  # noqa: BLE001
            raise TagError(errno.EIO, str(exc), str(path)) from None


# --- choosing a store ----------------------------------------------------------

_finder: Optional[FinderTags] = None
_xdg = XdgTags()
_s3 = S3Tags()
_ntfs = NtfsStreamTags()
_ssh = SshTags()


def store_for(path) -> Optional[TagStore]:
    """The store ``path``'s tags live in, or None where there is none."""
    global _finder
    text = str(path)
    if text.startswith("s3://"):
        return _s3 if "/" in text[len("s3://"):].strip("/") else None
    if text.startswith("ssh://"):
        return _ssh
    if "://" in text:
        return None  # archives, user schemes: no tags
    if sys.platform == "darwin":
        if _finder is None:
            _finder = FinderTags()
        return _finder
    if sys.platform.startswith("linux") and hasattr(os, "getxattr"):
        return _xdg
    if sys.platform == "win32":
        return _ntfs
    return None


def read(path) -> list[Tag]:
    store = store_for(path)
    return store.read(path) if store else []


# --- editing ---------------------------------------------------------------------

def new_tag(name: str, store: TagStore, known: Iterable[Tag] = ()) -> Tag:
    """A tag named ``name`` for ``store``: the color it already has elsewhere
    (``known``), else the Finder color its name spells, else none."""
    if not store.has_colors:
        return Tag(name)
    for tag in known:
        if tag.name.casefold() == name.casefold():
            return Tag(name, tag.color)
    return Tag(name, _COLOR_BY_NAME.get(name.casefold(), 0))


def apply_change(current: list[Tag], add: Iterable[Tag] = (),
                 remove: Iterable[str] = ()) -> list[Tag]:
    """``current`` with ``remove`` taken out and ``add`` put in, order kept and
    names compared without case (Finder treats ``Work`` and ``work`` as one)."""
    gone = {n.casefold() for n in remove}
    out = [t for t in current if t.name.casefold() not in gone]
    have = {t.name.casefold() for t in out}
    for tag in add:
        if tag.name.casefold() not in have:
            out.append(tag)
            have.add(tag.name.casefold())
    return out


def parse_names(text: str) -> list[str]:
    """Comma-separated names as typed: trimmed, empties dropped, duplicates
    (ignoring case) dropped."""
    seen, out = set(), []
    for piece in text.split(","):
        name = piece.strip()
        if name and name.casefold() not in seen and "\n" not in name:
            seen.add(name.casefold())
            out.append(name)
    return out


def common(tag_lists: list[list[Tag]]) -> list[Tag]:
    """The tags every list has, in the first list's order."""
    if not tag_lists:
        return []
    rest = [{t.name.casefold() for t in tags} for tags in tag_lists[1:]]
    return [t for t in tag_lists[0] if all(t.name.casefold() in s for s in rest)]


def carry(src, dest) -> None:
    """Give ``dest`` the tags ``src`` has, after a copy, where both sides have
    a store. Best-effort: a copy never fails over its tags. A same-store local
    copy that already kept them (clonefile, Linux copystat) is rewritten with
    the same value, which is harmless."""
    src_store, dest_store = store_for(src), store_for(dest)
    if src_store is None or dest_store is None:
        return
    try:
        tags = src_store.read(src)
        if tags:
            dest_store.write(dest, [new_tag(t.name, dest_store, [t]) for t in tags])
    except (TagError, OSError) as exc:
        logger.warning(f"Tags not copied to {dest}: {exc}")


# --- the file list's view of tags ------------------------------------------------

class TagCache:
    """Tags for the rows a pane draws, read off the UI thread.

    :meth:`get` answers from the cache, or queues the entry for a worker and
    answers None until it lands — a network mount answers a ``getxattr`` with a
    round trip, and the draw must never wait on one. ``on_ready`` is called on
    the worker when new answers are in; the app turns that into a repaint.
    Only stores that are cheap per file (:attr:`TagStore.cheap`) are asked:
    S3 tags cost a request per object, so the list leaves them out.

    The cache follows the pane's listing: a new ``files`` list (a relist, a
    sort, a filter, a new directory) starts it afresh, since that is when a
    file's tags may have changed under it."""

    def __init__(self, on_ready=None):
        import queue
        import threading
        self._on_ready = on_ready
        self._lock = threading.Lock()
        self._tags: dict[str, list[Tag]] = {}
        self._pending: set[str] = set()
        self._queue: "queue.Queue" = queue.Queue()
        self._list_id = None
        self._generation = 0
        self._thread = None
        self._threading = threading
        #: Every tag seen so far this session, for the pickers.
        self.seen: dict[str, Tag] = {}

    def get(self, files, entry) -> Optional[list[Tag]]:
        key = str(entry)
        with self._lock:
            if id(files) != self._list_id:
                self._list_id = id(files)
                self._tags.clear()
                self._pending.clear()
                self._generation += 1
            if key in self._tags:
                return self._tags[key]
            if key in self._pending:
                return None
            store = store_for(entry)
            if store is None or not store.cheap:
                self._tags[key] = []
                return self._tags[key]
            self._pending.add(key)
            generation = self._generation
        self._queue.put((generation, key, entry))
        self._ensure_worker()
        return None

    def forget(self, paths: Iterable) -> None:
        """Drop cached answers — after XeFM itself changed those files' tags."""
        with self._lock:
            for path in paths:
                self._tags.pop(str(path), None)

    def _ensure_worker(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = self._threading.Thread(
                target=self._work, name="xefm-tags", daemon=True)
            self._thread.start()

    def _work(self) -> None:
        import queue
        while True:
            try:
                generation, key, entry = self._queue.get(timeout=5)
            except queue.Empty:
                return
            try:
                found = read(entry)
            except (TagError, OSError):
                found = []
            with self._lock:
                if generation != self._generation:
                    continue
                self._pending.discard(key)
                self._tags[key] = found
                for tag in found:
                    self.seen.setdefault(tag.name.casefold(), tag)
                more = not self._queue.empty()
            if not more and self._on_ready is not None:
                self._on_ready()
