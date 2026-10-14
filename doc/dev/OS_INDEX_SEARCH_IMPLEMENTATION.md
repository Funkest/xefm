# OS Index Search — Implementation

[#579](https://github.com/crftwr/xefm/issues/579), from discussion
[#507](https://github.com/crftwr/xefm/discussions/507). User-facing behavior is
in [`doc/OS_INDEX_SEARCH_FEATURE.md`](../OS_INDEX_SEARCH_FEATURE.md).

## Shape: a narrow feature, not the engine registry

#507 asked whether the OS indexes should arrive as #446's engine registry
(Spotlight its first engine) or as narrower pieces. They are a narrow
feature: one action, `index_search`, plus Finder saved searches on `Enter`.
#446's registries stay on hold, because a registry with one built-in engine
per platform and no third-party engines would be an API without a second
user. Nothing here closes it off: `os_index.search()` is already the shape
an engine's `search` would take.

macOS and Windows ship together (#507 Q3). Linux is out of scope: its
indexes (plocate, Baloo, Recoll) have CLIs that Open List from Command
already runs.

## `xefm/os_index.py`

| | |
|---|---|
| `engine()` | `"Spotlight"` / `"Windows Search"` / None, by platform |
| `unavailable()` | why not: no index here, no `mdfind`, no `comtypes` |
| `search(query, scope, cancelled=, on_count=)` | → `Result(paths, error, cancelled)`. Blocking, run on a task. |
| `read_saved_search(data)` / `search_saved(query, scopes, …)` | Finder `.savedSearch` |

### Spotlight: `mdfind`, not `NSMetadataQuery`

`/usr/bin/mdfind [-onlyin DIR …] QUERY`, run through
`command_list.run`, the command source's subprocess runner. It gets its own
session, a tree kill on cancel, bytes read until exit, and decoding through
`path_list.decode` and `path_list.parse`. The choice over PyObjC's
`NSMetadataQuery` came down to four points:

- `mdfind`'s query **is** Spotlight's search-field language: words over
  names and contents, `kind:` / `date:` / `name:` keywords, and raw
  `kMDItem…` predicates, parsed by the same `UserQueryParser`. #446 §5 wants
  an engine to own its query language end to end, and this is the OS's own
  parser rather than one reimplemented over `NSPredicate`.
- `NSMetadataQuery` needs a run loop to deliver results. On a task's worker
  that means hosting one.
- Cancelling is killing a process. An in-process query would have to be
  stopped from the right thread.
- It is the same index. Live queries are the one thing given up (#507 §4.6),
  and they are not in this issue.

`mdfind` writes `[UserQueryParser] Loading keywords…` to stderr on success,
so stderr is only reported when the run failed and found nothing, with that
noise removed.

The macOS app runs under the Hardened Runtime without App Sandbox, so
`mdfind` as a subprocess is unrestricted. This is confirmed from the
development tree. A hand check in the signed app is owed.

### Windows Search: OLE DB over `comtypes`

`ADODB.Connection` to `Provider=Search.CollatorDSO;Extended
Properties='Application=Windows';`, and an `ADODB.Recordset` over
`windows_sql(query, scope)`:

```sql
SELECT TOP 20000 System.ItemPathDisplay FROM SYSTEMINDEX
WHERE SCOPE='file:C:/Users/me/Docs'
  AND (System.FileName LIKE '%word%' OR CONTAINS(*, '"word*"'))   -- per word
```

A query starting with `where ` is used as the condition verbatim, for the
property system (`System.Size`, `System.Kind`, `System.DateAccessed`).
Single quotes are doubled. `CoInitialize` / `CoUninitialize` wrap the run,
because COM is per thread and this runs on the task's worker. Rows are read
one by one, checking `cancelled()` and reporting `on_count`.

AQS (`kind:pdf size:>10MB`) would need `ISearchQueryHelper`, whose interface
is not in a registered type library, so it is left out. #507 Q4 (Windows'
counterpart of `kMDItemLastUsedDate`) is left open. `System.DateAccessed` is
the candidate.

`comtypes` is a requirement on Windows only (`sys_platform == "win32"`): pure
Python on ctypes, small, and without it the desktop build could not offer the
feature at all. `unavailable()` still names it when missing.

### Finder saved searches

A `.savedSearch` is a plist. The query is `RawQueryDict.RawQuery` (or
top-level `RawQuery`), and the scopes are `RawQueryDict.SearchScopes` (or
`SearchCriteria.FXScopeArrayOfPaths`): paths, `kMDQueryScopeHome`, or the
computer and network scopes, which mean everywhere (no `-onlyin`). Explorer's
`.search-ms` is not read yet.

## The app

- `index_search()`: refuses what `_index_scope` refuses (no index, a
  virtual or URI pane), and otherwise opens the search dialog in its `index`
  mode (#609; see [SEARCH_FILTERS_IMPLEMENTATION.md](SEARCH_FILTERS_IMPLEMENTATION.md)).
  `_iter_index_matches` runs `os_index.search` per query, as a keystroke
  re-runs any search, and yields its paths through the filter chips. A
  failure is raised as `SearchFailed`, which the dialog shows on its status
  line. Until #609 this was a `HistoryInputDialog` of past queries (state
  key `index_search.history`, still the index mode's history), so results
  were seen only after Enter, and the list showed input where output
  belongs.
- `_run_index_search(pane, query, scope, title=, run_search=)`, now used by
  saved searches only: a `Task`
  (`busy_label="Searching…"`, counting matches, Esc stops). On completion,
  errors and "nothing found" are logged and the pane is left alone. Matches
  go through `open_path_list` (#453's door), titled `Spotlight: query`, with
  the scope as the base for the list's root.
- `_enter_file`: a `.savedSearch` on macOS goes to `_open_saved_search`,
  which reads it and runs `search_saved` through the same task, titled with
  the file's stem.
- The history helpers `_query_history` / `_record_history` /
  `_forget_history` are key-generic. `_query_history` was `_history` until
  #607: the directory history's `self._history` list shadowed it. The
  list-command history keeps its own older copies.

## Not done

Explorer `.search-ms`, AQS, metadata as list columns
(#446 §3's `EntryInfo`), Migemo over the index (#507 §5), and an MCP tool
over this search.

## Tests

`test/test_os_index.py`. It covers the `mdfind` argv, Windows SQL (words,
escaping, raw `where`), saved-search parsing (scopes, home, everywhere,
refusals), and **one real Spotlight query** on macOS for a file of this
repository, skipped when the index has nothing for it. The app half stubs
the search and covers matches becoming a list, nothing found and errors
leaving the pane, `Enter` on a saved search running its query in its scopes,
and a remote pane being refused. Windows Search has no automated test here,
since it needs COM and a Windows index, and is owed a hand check.
