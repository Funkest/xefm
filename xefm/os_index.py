"""Searching the index the OS keeps (#579, discussion #507): Spotlight on
macOS, Windows Search on Windows.

Each engine owns its query language end to end (#446 §5), so a query reads
the way it does in that OS:

- **Spotlight** runs ``mdfind``, which parses a query the way Spotlight's own
  search field does — words match names and contents, ``kind:pdf``,
  ``date:today``, ``name:report`` — and takes raw metadata predicates as well
  (``kMDItemPixelWidth > 4000``). A subprocess rather than ``NSMetadataQuery``:
  it is the same index and the same parser, it is cancelled by killing it,
  and it runs on the command source's tested machinery
  (:mod:`xefm.command_list`).
- **Windows Search** is queried through OLE DB (``Search.CollatorDSO``) with
  Windows Search SQL against ``SystemIndex``. Words match file names and
  contents; a query starting with ``where`` is a raw SQL condition. It needs
  ``comtypes`` (pure Python), an optional dependency.

Both search the given folder and everything below it, and return paths;
the app opens them as a list pane. Linux has no OS index here: the command
source covers its indexes (plocate, Baloo, Recoll).
"""

from __future__ import annotations

import os
import plistlib
import shlex
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

from xefm.log_manager import getLogger

logger = getLogger("OsIndex")

#: Most results asked of Windows Search; Spotlight's output is read whole.
MAX_RESULTS = 20000


@dataclass
class Result:
    paths: list = field(default_factory=list)
    #: Why nothing could be searched (not "nothing matched").
    error: str = ""
    cancelled: bool = False


def engine() -> Optional[str]:
    """The OS index on this platform: ``"Spotlight"``, ``"Windows Search"``,
    or None."""
    if sys.platform == "darwin":
        return "Spotlight"
    if sys.platform == "win32":
        return "Windows Search"
    return None


def unavailable() -> Optional[str]:
    """Why the OS index cannot be searched here, or None when it can."""
    name = engine()
    if name is None:
        return "There is no OS search index on this platform"
    if name == "Spotlight":
        if not os.path.exists("/usr/bin/mdfind"):
            return "mdfind is missing"
        return None
    try:
        import comtypes.client  # noqa: F401
    except ImportError:
        return "Searching Windows Search needs comtypes: pip install comtypes"
    return None


# --- Spotlight -----------------------------------------------------------------

#: Finder's scope names in a saved search, and what they mean for -onlyin.
_SCOPE_HOME = "kMDQueryScopeHome"
_SCOPE_EVERYWHERE = {"kMDQueryScopeComputer", "kMDQueryScopeComputerIndexed",
                     "kMDQueryScopeNetwork", "kMDQueryScopeNetworkIndexed",
                     "kMDQueryScopeAllIndexed"}


def spotlight_argv(query: str, scopes: list) -> list:
    """``mdfind`` for ``query`` in ``scopes`` (folders; none = everywhere)."""
    argv = ["/usr/bin/mdfind"]
    for scope in scopes:
        argv += ["-onlyin", str(scope)]
    argv.append(query)
    return argv


def _spotlight(argv: list, cancelled, on_count) -> Result:
    from xefm import command_list, path_list
    output = command_list.run(shlex.join(argv), cwd=os.path.expanduser("~"),
                              env=dict(os.environ), cancelled=cancelled,
                              on_count=on_count)
    if output.cancelled:
        return Result(cancelled=True)
    if output.code is None:
        return Result(error=f"mdfind could not run: {output.error}")
    paths = path_list.parse(output.stdout)
    if not paths and output.code:
        # mdfind chatters on stderr ("[UserQueryParser] Loading keywords…")
        # even when it works; only a failure with nothing found is worth a word.
        noise = ("[UserQueryParser]",)
        said = [line for line in output.stderr_tail if not any(n in line for n in noise)]
        return Result(error=said[-1] if said else f"mdfind exited with {output.code}")
    return Result(paths=paths)


def read_saved_search(data: bytes) -> tuple[str, list]:
    """``(query, scopes)`` from a Finder saved search (``.savedSearch``, a
    Smart Folder): its raw query, and the folders it searches — an empty list
    for "This Mac". Raises ``ValueError`` when the file holds no query."""
    try:
        plist = plistlib.loads(data)
    except Exception as e:  # noqa: BLE001 — plistlib raises several kinds
        raise ValueError(f"not a saved search: {e}") from None
    raw = plist.get("RawQueryDict") or {}
    query = raw.get("RawQuery") or plist.get("RawQuery")
    if not query:
        raise ValueError("this saved search holds no query")
    scopes_in = raw.get("SearchScopes") or \
        (plist.get("SearchCriteria") or {}).get("FXScopeArrayOfPaths") or []
    scopes = []
    for scope in scopes_in:
        if scope == _SCOPE_HOME:
            scopes.append(os.path.expanduser("~"))
        elif scope in _SCOPE_EVERYWHERE:
            return query, []
        elif isinstance(scope, str) and scope.startswith("/"):
            scopes.append(scope)
    return query, scopes


# --- Windows Search ------------------------------------------------------------

def _sql_text(s: str) -> str:
    return s.replace("'", "''")


def windows_sql(query: str, scope: str) -> str:
    """Windows Search SQL for ``query`` under ``scope``. Words must all match
    the file name or its contents; a query starting with ``where`` is used as
    the condition as it is."""
    scope_uri = "file:" + str(scope).replace("\\", "/")
    head = (f"SELECT TOP {MAX_RESULTS} System.ItemPathDisplay FROM SYSTEMINDEX "
            f"WHERE SCOPE='{_sql_text(scope_uri)}'")
    text = query.strip()
    if text.lower().startswith("where "):
        return f"{head} AND ({text[6:]})"
    conds = []
    for word in text.split():
        w = _sql_text(word.replace('"', ""))
        if not w:
            continue
        conds.append(f"(System.FileName LIKE '%{w}%' OR CONTAINS(*, '\"{w}*\"'))")
    return head + "".join(f" AND {c}" for c in conds)


def _windows(query: str, scope: str, cancelled, on_count) -> Result:
    try:
        import comtypes
        import comtypes.client
    except ImportError:
        return Result(error="Searching Windows Search needs comtypes: pip install comtypes")
    # COM is per thread, and this runs on a task's worker.
    comtypes.CoInitialize()
    conn = None
    try:
        conn = comtypes.client.CreateObject("ADODB.Connection")
        conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
        rs = comtypes.client.CreateObject("ADODB.Recordset")
        rs.Open(windows_sql(query, scope), conn)
        paths = []
        while not rs.EOF:
            if cancelled():
                return Result(cancelled=True)
            value = rs.Fields.Item("System.ItemPathDisplay").Value
            if value:
                paths.append(str(value))
                on_count(len(paths))
            rs.MoveNext()
        rs.Close()
        return Result(paths=paths)
    except Exception as e:  # noqa: BLE001 — COM raises COMError and friends
        logger.error(f"Windows Search query failed: {e}")
        return Result(error=f"Windows Search could not be queried: {e}")
    finally:
        try:
            if conn is not None:
                conn.Close()
        except Exception:  # noqa: BLE001
            pass
        comtypes.CoUninitialize()


# --- the door ----------------------------------------------------------------------

def search(query: str, scope: Optional[str], *,
           cancelled: Callable[[], bool] = lambda: False,
           on_count: Callable[[int], None] = lambda n: None) -> Result:
    """Run ``query`` against the OS index, under ``scope`` (a local folder;
    None = the whole index, Spotlight only). Blocking: call it on a worker."""
    why = unavailable()
    if why:
        return Result(error=why)
    if engine() == "Spotlight":
        return _spotlight(spotlight_argv(query, [scope] if scope else []), cancelled, on_count)
    return _windows(query, scope or os.path.expanduser("~"), cancelled, on_count)


def search_saved(query: str, scopes: list, *,
                 cancelled: Callable[[], bool] = lambda: False,
                 on_count: Callable[[int], None] = lambda n: None) -> Result:
    """Run a Finder saved search's raw query in its scopes (Spotlight)."""
    if engine() != "Spotlight":
        return Result(error="Finder saved searches are run by Spotlight, on macOS")
    return _spotlight(spotlight_argv(query, scopes), cancelled, on_count)
