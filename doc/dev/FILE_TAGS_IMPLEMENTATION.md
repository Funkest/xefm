# File Tags — Implementation

Issue #585, from discussion #475 (part 2). Part 1, bookmarks, was #517. The
principle is that XeFM uses the OS's own tags where the OS has them, and has no
private tag database.

## `xefm/tags.py`

`Tag(name, color)`: `color` is Finder's index, 0–7. `store_for(path)` picks a
`TagStore` from the path string. It is a pure string check, so it is cheap
enough for every drawn row.

| Store | Paths | Medium | `cheap` | `has_colors` |
|---|---|---|---|---|
| `FinderTags` | local, darwin | `com.apple.metadata:_kMDItemUserTags` xattr (binary plist of `"Name\nN"`), via ctypes `getxattr`/`setxattr`/`removexattr` — `os.*xattr` does not exist on macOS | yes | yes |
| `XdgTags` | local, linux | `os.getxattr(..., "user.xdg.tags")`, comma-separated | yes | no |
| `NtfsStreamTags` | local, win32 | named stream `path:xefm.tags`, UTF-8 JSON `[{name, color}]` | yes | yes (round-trips Finder colors) |
| `S3Tags` | `s3://bucket/key` | `get/put/delete_object_tagging`; a tag = key with value `""`, valued keys preserved | no | no |
| `SshTags` | `ssh://` | a second `ssh` process (`SSHConnection.run_remote`, same BatchMode options as the SFTP session) running `getfattr`/`setfattr` (Linux) or `xattr -px/-wx` (macOS) | no | yes |
| none | archives, user schemes, other platforms | — | — | — |

The Windows choice (an NTFS stream, rather than `System.Keywords` or state.db)
was the user's answer to the discussion's open question 1.

Each store has:

- `read(path)` and `write(path, tags)`; writing `[]` removes the tags;
- `read_many(paths)` and `write_many([(path, tags)])`, so a store that pays per
  call can batch. `SshTags` sends one remote `sh -c` per host and batch: a
  NUL-separated `path\0value\0` stream for reads, and per-file commands with
  `|| printf path` for failures on writes;
- `find(root, name)`, which returns indexed results or `None`:
  - `FinderTags`: `mdfind -onlyin root "kMDItemUserTags == 'name'"`. An empty
    answer counts as `None`, because an unindexed volume and "no hits" look
    the same.
  - `SshTags`: `mdfind` on a macOS host, or `getfattr -R --absolute-names -n
    user.xdg.tags` on a Linux host, parsed with `_unescape_getfattr` (octal
    escapes).

`SshTags` probes each host once (`uname -s`, plus which tools exist) and
caches the answer. A missing tool raises a `TagError` that names the `attr`
package.

Helpers:

- `apply_change`: case-insensitive add/remove that keeps the existing order.
- `common`: the tags shared by every list.
- `parse_names`: splits the comma-separated text from the edit dialog.
- `new_tag`: reuses a known tag's color, else maps a Finder color name to its
  index, else uses no color.

## Copies

`tags.carry(src, dest)` is called by `FileOperationService` at two points:

- in `_copy_file`, after the streaming or `copy_to` paths;
- in `_copy_tree`, after creating a directory.

The `clonefile` path returns before it, because a clone carries every xattr.
The call is needed because `copystat` copies xattrs only on Linux, and nothing
carries tags across storages. It is best-effort: a failure logs a warning and
never fails the copy.

## The file list

`TagCache`, one per `FilePane` (`view.tag_cache`):

- `get(files, entry)` answers from a dict, or queues the entry for a daemon
  worker and returns `None`.
- The cache resets when the pane's `files` list identity changes, the same key
  as `_ext_cache`.
- Stores that aren't `cheap` answer `[]` immediately and are never queued.
- When the queue drains, the worker calls `on_ready`. That is
  `XeFMApp._on_tags_ready`, which sets `_tags_dirty` and calls `_wake_pump`;
  `_pump_monitoring` reports the flag as a change, so the frame repaints.
  Poll-loop backends drain on their animation tick in the same way.

`FilePane._draw_row` draws up to `_MAX_TAG_DOTS` `●` after the name, colored
from `tags.RGB` (or the muted column ink) and dimmed with the rest of an
inactive pane. The name's elide width shrinks by the width of the dots.

## B and J

- **B** (`add_favorite`): the choice values are now `(kind, value)`:
  - `fav` rows come first and are unchanged, so B Enter still adds this
    directory;
  - `_tag_rows` adds one `tag-toggle` row per known tag (up to `_TAG_ROWS`)
    and a `tag-edit` row.

  Targets are the selection, or the cursor item when nothing is selected. Rows
  appear only when every target shares one store. For a cheap store and up to
  `_TAG_MARK_LIMIT` targets, B reads the targets' tags inline to show the ✓
  marks. Otherwise the mark is left unknown, and `_toggle_tag` reads the tags
  in a task before deciding.
- **Writes** go through `_write_tags`: read, `compute(current)`, then
  `write_many`. This runs inline for a cheap store and as a `Task` otherwise.
  Afterwards it calls `tag_cache.forget(targets)` and logs.
- **Known tags**: `state.db` key `tags.known`, a list of `[name, color]`, most
  recent first, capped at `_KNOWN_TAGS_MAX`. They are merged with
  `TagCache.seen` (tags seen on files this session).
- **Search Tags** (`find_by_tag` action → `show_tag_search`, View → Search
  Tags…, no default key): a filter list of the known tags, with
  `on_accept_text` for a name not listed. It used to be `_TagJump` rows under
  **J**. #605 moved it out because J goes to places and this is a search.
  Accepting calls `find_by_tag(name)`, which runs a `Task`:
  1. Ask `store.find`.
  2. If that returns `None`, fall back to `_walk_for_tag`, which reads one
     directory's children per `read_many` call, so SSH costs one remote
     command per directory.
  3. Show the hits with `open_path_list(..., title="Tag: name")`.

  The remove key on a tag row forgets it from `tags.known`; files keep the tag.
- **Finder's format.** `format_finder` writes every tag as `"Name\nN"`,
  `"Work\n0"` for a tag without a color, which is what `NSURLTagNamesKey`
  writes (#605). Foundation reads a bare `"Work"` too. In the hand check
  Finder's list showed only the colored tags, and *Get Info* showed `Work`.
  That is how Finder treats colorless tags, and the bare form was a deviation
  worth removing anyway.

## Tests

`test/test_tags.py`:

- the helpers;
- Finder tags on macOS (including what `xattr -p` sees);
- XDG tags on Linux (skipped elsewhere);
- the NTFS-stream format, as an ordinary file off Windows;
- SSH: the macOS branch is run through a local `sh` and checked against
  `FinderTags`; the Linux branch is parsed from canned output;
- S3 with a stub client;
- `carry`;
- `TagCache`;
- app tests: B edit then toggle, B on a selection, Search Tags listing
  the tag (and J not), and `find_by_tag` through the walk.

## Hand checks owed

- **Windows:** the NTFS stream on real NTFS, and its loss to FAT/exFAT.
- **Linux:** the real `user.xdg.tags` round trip, which Docker could not run
  here, and Dolphin seeing the tags.
- **SSH:** against a real Linux host with and without the `attr` package.
- **S3:** against a real bucket.
- **macOS:** Finder showing the tags and colors written here. Spotlight
  indexing was confirmed during development in a non-temporary folder.
- **GUI and TUI:** the dots in both, including East Asian ambiguous-width
  terminals.
