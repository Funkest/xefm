# SSH/SFTP Subsystem

XeFM's remote browsing runs one `ssh <host> -s sftp` process per host and speaks
the SFTP protocol to the server at the other end of its stdin/stdout. This
document records why it is built that way and the behaviors that keep it
correct and fast, so they aren't accidentally undone.

Related code:
- `xefm/sftp_client.py` — `SFTPClient`, the SFTP v3 protocol over a pair of
  byte streams (no ssh, no processes, no XeFM paths)
- `xefm/ssh_connection.py` — `SSHConnection` (one session per host: the ssh
  process, login errors, caching, exceptions) and `SSHConnectionManager`
- `xefm/ssh.py` — `SSHPathImpl`, the `ssh://host/path` backend of `Path`
- `xefm/ssh_cache.py` — `SSHCache`, the TTL cache behind `list_directory`/`stat`
- `xefm/ssh_config.py` — `SSHConfigParser` (`~/.ssh/config`, `Include`, wildcards)
- `macos_app/src/XeFMAppDelegate.m` — packaged-app `PATH` fix

Related docs:
- `PATH_POLYMORPHISM_SYSTEM.md` — the polymorphic `Path` layer that exposes remote
  paths (`ssh://host/...`) to the rest of XeFM
- `../SFTP_SUPPORT_FEATURE.md` — user-facing SFTP feature docs

---

## Why one session, spoken to directly (#532)

XeFM used to run a fresh `sftp -b -` batch per operation and parse its text
output, which only performed because every one of those processes rode an
OpenSSH **ControlMaster** — a shared connection reached over a Unix socket. The
OpenSSH built into Windows has no ControlMaster (`ControlMaster=yes` fails with
`getsockname failed: Not a socket` before connecting), so SSH did not work with
it at all, and without sharing, each operation would pay a full login.

Every serious remote client avoids that the same way: hold **one** connection
and multiplex inside it yourself. VS Code Remote-SSH runs its own protocol over
one ssh; WinSCP and FileZilla embed SSH. XeFM's equivalent needs nothing on the
server: OpenSSH's `sftp-server` is already there, and `ssh -s <host> sftp` is
exactly how `sftp` itself reaches it. So:

- **Any OpenSSH client works**, Windows' own included. Nothing is looked for in
  particular places and nothing needs configuring.
- **`~/.ssh/config` applies unchanged** — `ProxyJump`, `ProxyCommand`, keys,
  ssh-agent — because ssh itself still does the login.
- **No text parsing.** Names with spaces or quotes, dates, sizes and types come
  back as protocol fields, not as `ls -l` columns.

The cost is the protocol client, `xefm/sftp_client.py`.

## The protocol client — `SFTPClient`

SFTP v3 (draft-ietf-secsh-filexfer-02, what OpenSSH implements). Each packet is
`uint32 length, byte type, payload`; every request carries an id that its reply
echoes.

- **A reader thread** reads replies and resolves the `Future` registered for
  that id. Callers on any thread `submit()` a request and `wait()` on its
  future; writes are serialized by a lock. So the session is shared between
  threads — a listing on the pane's worker and a parallel copy pool's transfers
  interleave on it — with no per-caller connection.
- **Transfers are pipelined.** `read_file` keeps `WINDOW` (32) reads of `CHUNK`
  (32 KiB) bytes in flight and consumes them in order; `write_file` does the
  same with writes. One round trip per MiB rather than per chunk.
  - A server may return a **short read** at any offset. The requests already in
    flight assumed a full chunk there, so they are dropped and reading resumes
    where the short reply ended.
  - Reading stops at EOF, not at the size `fstat` reported: a file that grows
    while it is read is read to its end. The size only bounds the window, so a
    tiny file does not get 32 requests.
  - **Streaming.** `read_file(..., sink=f)` writes each chunk into `f` as it
    lands instead of collecting the file, and `write_file` takes a readable
    stream as well as `bytes`, reading it `CHUNK` at a time (`size=` scales the
    progress). A transfer then holds one window — 1 MiB — rather than the whole
    file, which is what lets a copy run several large files at once (#540).
    `SSHPathImpl.download_to_stream` / `upload_from_stream` expose the pair
    under the names S3's backend uses, and the local ⇄ SSH legs of
    `_copy_file_cross_storage` go through them exactly as the local ⇄ S3 legs
    do.
- **Progress and cancel** come from the transfer loop itself: `progress(done,
  total)` is called as each chunk lands or is acknowledged — 0 first, the full
  size last — and whatever it raises leaves `read_file`/`write_file` unchanged
  (the handle is closed on the way out). That is the contract
  `FileOperationService._remote_progress()` relies on: its callback calls
  `task.checkpoint()`. Nothing samples a growing file any more, and there is no
  second connection to measure an upload with.
- **Errors**: a STATUS reply other than OK is `SFTPError(code, message)`; the
  stream ending fails every waiting request with `SFTPClosed`; a reply that does
  not arrive within `timeout` is `SFTPTimeout`.
- **Directories** are read with `READDIR_AHEAD` (4) READDIRs in flight on the
  handle, so a small directory's entries and its EOF arrive in one round trip;
  OpenSSH's server answers in order, and paramiko reads ahead the same way.
- **CLOSE is not waited for** after a read or a listing (`wait=False`):
  nothing its reply could say changes the outcome, and waiting cost a round trip
  per file and per directory. A completed write does wait, and checks the
  reply — a buffering server can still report the write failing there.
- **Rename** uses `posix-rename@openssh.com` when the server announces it, as
  `sftp`'s own `rename` does: plain SSH_FXP_RENAME refuses an existing target,
  POSIX rename replaces it.
- **Names are bytes** on the wire. They are decoded as UTF-8 with
  `surrogateescape`, so a name that is not valid UTF-8 encodes back to exactly
  the bytes it came from and can still be opened, renamed or deleted.

## The session — `SSHConnection`

`ssh_command()` builds the ssh command line. Its `-o` options are those `sftp`
passes to the ssh it starts — `ForwardX11=no`, `ForwardAgent=no`,
`PermitLocalCommand=no`, `ClearAllForwardings=yes` (a `LocalForward` in the
user's config that cannot bind must not become this session's problem) — plus
`BatchMode=yes` (there is no terminal to prompt on),
`StrictHostKeyChecking=accept-new`, and `ServerAliveInterval=15` /
`ServerAliveCountMax=4`, so a dead link ends the session within about a minute
instead of leaving requests waiting on it.

`_spawn_ssh()` starts it with binary pipes on all three streams; on Windows with
`CREATE_NO_WINDOW`, so the GUI app does not flash a console. A thread drains
stderr (so it can never fill and stall ssh) and keeps its last lines.

**Connecting.** `connect()` starts the process, then the INIT/VERSION handshake,
bounded by `CONNECT_TIMEOUT` (30 s, ProxyCommand and all). If the stream ends
before VERSION, the login failed, and what ssh printed is the only account of
why: `_login_failure()` maps "Permission denied" to `SSHAuthenticationError`,
"timed out" / "Connection refused" / "No route to host" to
`SSHConnectionTimeoutError`, and anything else (host key changed, unknown host,
…) to an `SSHError` carrying ssh's own words.

**Default directory.** `connect()` asks `REALPATH(".")` — where the server starts
a session, normally the home directory — and keeps it as `default_directory`
(falling back to `/` if the server will not say).

**Requests.** `_call()` runs one client operation and maps its failures:
`NO_SUCH_FILE` → `SSHPathNotFoundError` (logged at debug for `stat` /
`list_directory`, which are often plain existence checks), `PERMISSION_DENIED` →
`SSHPermissionDeniedError`, other statuses → `SSHError` with the server's
message, `SFTPClosed` → `SSHConnectionLostError`. A timeout drops the session —
its state is unknown once a reply has gone missing — and raises
`SSHConnectionTimeoutError`; the next use reconnects.

**Liveness** is free: `is_connected()` is "the client is alive and the ssh
process has not exited". The client notices on its own when the stream ends, so
there is no periodic check and nothing to cache.

`SSHConnectionManager` keeps one `SSHConnection` per host, replaces one that has
dropped on the next `get_connection()`, closes idle ones in
`cleanup_idle_connections()`, and closes them all at exit (registered with
`atexit` when the manager is first created). Even without that, closing XeFM
closes ssh's stdin, which ends the session on both sides.

### Packaged-app PATH (macOS DMG)

A DMG-mounted app does not inherit the user's shell `PATH`. SSH configs that use
a `ProxyCommand` shelling out to `aws`, `gcloud`, etc. therefore can't find those
tools, and the login fails.

`macos_app/src/XeFMAppDelegate.m` fixes this in `setupEnvironmentPath`, called
before the XeFM module is imported. It prepends the common tool locations —
`/usr/local/bin`, `/opt/homebrew/bin`, `/opt/local/bin`, `~/bin`, `~/.local/bin`,
and the `~/Library/Python/3.x/bin` dirs — to `PATH` via `setenv`, and mirrors the
result into Python's `os.environ` so the ssh process (and thus the
`ProxyCommand`) can resolve those tools.

---

## Paths and entries

**Normalization.** `list_directory()` and `stat()` run `remote_path` through
`posixpath.normpath()` before the cache lookup and the request. Search and
path-join operations can hand over runaway `./././…` or `..` segments;
normalizing collapses them and keeps equivalent paths on one cache key.

**`.` and `..`** are dropped by `SFTPClient.listdir()`. A surviving `.` would
re-enter the current directory, so a recursive walk would loop and a search
would return nonsense — the check is on the decoded name, never on text.

**Entry records** (`_entry()`): `name`, `size`, `mtime` (seconds, from the
server — not a minute-resolution `ls` date), `mode` (the full `st_mode`, so
`stat.filemode()` and `S_ISDIR` work on it), `is_dir`, `is_file`, `is_symlink`.

**Symlinks** are described as a local directory listing describes them: by what
they point to — a link to a directory is a directory to browse into — but still
flagged as a link. READDIR returns `lstat` attributes, so `_resolve_links()`
sends a `STAT` for every link in the listing, all in flight at once
(`stat_many`); a broken link keeps its own attributes. `stat()` is `LSTAT`, then
the same resolution if it is a link.

## Requests in flight — `CONCURRENCY`

The session serves requests side by side, so `SSHPathImpl` declares
`CONCURRENCY = 64` — what OpenSSH's own `sftp` keeps in flight by default
(`-R`). The model behind the number, and how each operation sizes itself from
it, is in [STORAGE_CONCURRENCY_SYSTEM.md](STORAGE_CONCURRENCY_SYSTEM.md). What
it changes here:

- **Walking a tree.** A walk that lists one directory, then the next, is bound
  by round trips × directories: on a deep tree over SFTP it spent nearly all
  its time waiting while the session sat idle. `xefm/tree_walk.py`'s `walk()`
  keeps up to 64 listings in flight instead, on a small thread pool; a
  directory is queued as soon as its parent's listing names it. Both search
  walks (`_iter_filename_matches`, `_iter_content_matches`), the flat view and
  disk usage (#541) go through it.
- **A content search** opens each file once and reads the next small files
  ahead on the same pool as the listings (#539, `xefm/content_read.py`).
  `SSHPathImpl.open` fetches the whole file, and the search used to open each
  file twice — once to sniff the encoding, once to read it.
- **A copy** to or from SSH has several files in flight (#540): as many as the
  other end's ceiling allows (8 against the local disk), half of the 64 between
  two SSH paths. Before the copy starts, the conflict check asks whether each
  destination exists; into an SSH directory those checks run side by side too,
  or a 400-file upload spent 17 of its 21 seconds asking.

Measured against the Tart VM's real `sshd` behind a 40 ms round-trip delay
line, 259 directories / 864 files of ~2 KiB, and 400 files of 8 KiB:

| | before | after |
|---|---|---|
| disk usage | 22.4 s | 0.68 s |
| content search | 302 s | 3.2 s |
| copy 400 files SSH → local | 80.3 s | 8.9 s |
| copy 400 files local → SSH | 70.4 s | 7.5 s |

Earlier, against a local `sftp-server` behind the same delay, the 259-directory
walk went from 53.4 s (one directory at a time, four round trips each) to 25.9 s
with the READDIR read-ahead and unwaited CLOSE, and 1.8 s with 16 listings in
flight (#538).

With several listings in flight, results arrive in the order the listings
complete rather than strictly depth-first; each directory's own entries still
come together and in order. A content search hands its results over in that
same walk order.

## Bulk stat caching during `list_directory`

A listing already carries every entry's attributes, so while building it
`list_directory()` also writes each entry into the cache under the key `stat()`
uses — `_cache.put(operation='stat', hostname=…, path=…, data=entry)` for
`posixpath.join(remote_path, name)`. A `stat()` of any listed file is then a pure
cache hit. `SSHPathImpl.listdir_attrs()` answers a pane's listing from the same
records without a request per entry.

- Entries are cached under the normal data TTL of `SSHCache` (default 30 s,
  configurable via `config.SSH_CACHE_TTL`).
- `SSHPathNotFoundError` / `SSHPermissionDeniedError` from a listing or a stat
  are cached too, under the longer `error_ttl` (default 300 s), so a path that
  is not there is not asked about again on every redraw.
- Every change invalidates what it touched: `write_file` (in a `finally`, since
  a cancelled upload has changed the file too), `delete_*`, `create_directory`,
  and both paths of a `rename`.

## Tests

- `test/test_ssh_sftp_session.py` runs `SSHConnection` against OpenSSH's real
  `sftp-server` over a pipe — the program sshd would run behind
  `ssh -s <host> sftp` — by passing a `spawn` that starts it instead of ssh
  (`test/sftp_server_helper.py` finds one: `/usr/lib/openssh`,
  `/usr/libexec`, or Git for Windows' `usr/lib/ssh`; the tests skip without
  one). Only the login is not exercised.
- `test/test_sftp_client.py` drives `SFTPClient` against a scripted in-process
  server for what a real one won't do on demand: short reads, no reply, no
  `posix-rename`, the stream ending mid-request.
