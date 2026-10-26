# Storage concurrency — how many requests at once

A remote storage answers each request a round trip later. Anything that asks
one thing, waits, then asks the next is bound by latency × requests, however
fast the link. XeFM hides that latency by keeping several requests in flight. It
decides how many from **what the storage declares**, never from its scheme
name: XeFM reads the declaration, and a backend an extension adds is treated the
same way as the built-in ones (#539, #540, #541).

## What a storage declares

On `PathImpl` (`xefm/path.py`), all Preview in `xefm.path_base`:

| attribute | meaning | default |
|---|---|---|
| `CONCURRENCY` | requests the storage serves at once, reads and writes together | 1 |
| `READ_CONCURRENCY` | how many of those may be reads (a listing is a read) | `None`: the total |
| `WRITE_CONCURRENCY` | how many of those may be writes | `None`: the total |

`xefm.path.concurrency(path)` reads them as `Concurrency(total, read, write)`.
Read and write are held to the total: declaring more than it has no effect. A
value that is not a count of at least 1 is logged and replaced with the default,
the same warn-and-ignore `CAPABILITIES` gets. A backend that declares nothing
serves one request at a time, because guessing upwards is the guess that hurts.

`LISTING_CONCURRENCY`, the Preview attribute this replaces, was the read side
alone. A backend that still sets it gets a warning and its number as
`CONCURRENCY`.

| backend | total | read | write | why |
|---|---|---|---|---|
| local (`file`) | 8 | 8 | 8 | see [Local disk](#local-disk) |
| SSH | 64 | 64 | 64 | one SFTP session serves requests side by side; 64 is what OpenSSH's `sftp -R` keeps in flight |
| S3 | 16 | 8 | 8 | 16 is the shared client's pool per host (`S3_MAX_POOL_CONNECTIONS`); 8 is unmeasured, carried over from the old table |
| archive, `UriPathImpl`, anything else | 1 | 1 | 1 | the default |

## The ceilings are per operation

Each operation (a copy, a search, a disk-usage scan, a flat view) sizes its own
pool from the declarations. Operations do not share a ceiling.

A shared ceiling (one budget per host, which every operation draws from) would
honour the declaration exactly. It would also make a task that stops while
holding requests block every other task on that storage:

- A background job **suspended** at a checkpoint waits for the queue's slot,
  which the running job holds; the running job would wait for the suspended
  one's requests. Neither can move.
- A background job **asking** (the conflict dialog, off screen until brought
  forward) would hold its requests until the user answers, while the
  foreground copy waits for them with nothing on screen saying why.
- The **UI thread** waiting for a request would stop the dialog that answers the
  question, and the Cancel button with it.
- A **cancelled** task whose request never comes back (a dead link) would hold
  its share until the request times out.

Per-operation ceilings have none of these, because no operation ever waits on
another's requests. The cost is that two operations on one storage together ask
more than it declared. How many operations run at once is already small: one
foreground task, the one background job holding the queue's slot, and read-only
tasks (`Task.exclusive = False`). So the overshoot is bounded at a few times the
declaration, which SFTP absorbs as a longer queue in one session and S3 is far
from throttling at.

Within one operation nothing holds a request while waiting for another: a pool
job is one listing, one file read, or one file transfer, and none of them waits
on another job. The thread consuming the results holds nothing while it waits
for one. That is all it takes to rule out a deadlock inside an operation.

## How each operation sizes itself

### Walking a tree — `xefm/tree_walk.py`

`walk()` keeps `parallel_reads(root)` listings in flight. That is the storage's
read concurrency **where the storage is remote** (`is_remote()`), and 1 where
it is not. Overlapping listings hides round trips, and a local listing has none
to hide: a 9,800-entry tree walked in 0.13 s one directory at a time and 0.42 s
four at once, the pool costing more than the listings. Local walks stay the
depth-first walk they always were.

`walk(pool=...)` uses a pool the operation already has, for an operation that
also reads files through it. `walk(on_error=...)` reports a directory that could
not be listed; disk usage counts those.

Every tree walk goes through it: the file-name and content searches, the flat
view, and disk usage (#541).

### A content search — `xefm/content_read.py`

- **One open per file.** `open_text()` sniffs the encoding from the first
  1 KiB and reads on from the same handle, instead of opening the file a
  second time as text.
- **Read-ahead on a remote storage.** The walk's listings and the file reads
  share one pool of `parallel_reads(root)` workers, so the search as a whole
  stays within the storage's read ceiling. `read_ahead()` reads small files
  (up to 1 MiB) whole on that pool and hands them over **in walk order**. A
  larger file, an empty one, or a PDF or Office file (searched through
  `document_text`) is left for the search to read when it gets there. At most
  16 MiB of read-ahead is requested and not yet searched. Stopping or
  cancelling drops reads not yet started.

### A copy or move — `transfer_workers()` in `xefm/file_operations.py`

Files in flight:

1. The smallest of every source's read ceiling and the destination's write
   ceiling: each file in flight is a read at one end and a write at the
   other. When a source is the same storage as the destination, each file is
   both of those requests against it, so the count is also held to half its
   total. A ceiling of 1 anywhere makes the copy sequential.
2. `TRANSFER_CONCURRENCY` overrides the number from step 1, unless that was 1.
3. An extraction has no source in it (the archive's reader is serialised
   whatever the count), so it is sized by the destination's write ceiling.

"Same storage" is the same scheme, so two SSH hosts count as one storage. That
can only lower the count, never raise it.

| copy | files in flight |
|---|---|
| local → local | 4 (half of 8) |
| local ⇄ S3, S3 → S3 | 8 |
| local ⇄ SSH | 8 (the disk's 8) |
| SSH → SSH | 32 (half of 64) |
| extraction to the local disk | 8 (measured the same as 4: 3,000 files, 0.37–0.41 s either way) |

The **conflict check** before a copy asks whether each destination exists. Into
a remote directory those checks run side by side on `parallel_reads(dest_dir)`
workers (`_existing()`). The check asks `exists()` rather than listing the
directory and matching names, because only the storage knows which names it
treats as the same file (case, Unicode normalisation).

A transfer has to hold only a window of the file, not the whole file, or
several large files in flight become a memory problem. Local ⇄ S3 always
streamed. Local ⇄ SSH streams now too (see
[SSH_SYSTEM.md](SSH_SYSTEM.md#the-protocol-client--sftpclient)). A download
lands in `.<name>.xefm-part` beside its destination and replaces it only once
whole, so a transfer that breaks off leaves neither a truncated file nor, when
overwriting, a lost original. Remote ⇄ remote across storage types
(S3 ⇄ SSH) still holds the whole file.

### Local disk

`8` comes from a copy between two local paths: four files in flight was the
best (~1.3–1.9x at 2–4 workers on an APFS SSD, *worse* beyond that, between the
GIL and filesystem metadata serialisation), and each of those files is a read
and a write on the disk. With the other end remote, the disk is not what the
copy waits on. A download from SSH through a 40 ms round trip kept gaining up
to 32 files at once:

| files in flight | 2 | 4 | 8 | 16 | 32 |
|---|---|---|---|---|---|
| 400 × 8 KiB, SSH → local | 40.8 s | 17.5 s | 8.9 s | 5.0 s | 2.4 s |

So a copy between the disk and SSH is capped at 8 by the disk's declaration,
not by anything SSH or the disk runs out of.

## Measurements

The Tart VM's real `sshd` (a clone of `xefm-demo`) was reached through a
userspace delay line adding 20 ms each way. The test data was 259 directories
with 864 files of ~2 KiB each, plus 400 files of 8 KiB.

| | before | after |
|---|---|---|
| disk usage | 22.4 s | 0.68 s |
| content search | 302 s | 3.2 s |
| copy 400 files SSH → local | 80.3 s | 8.9 s |
| copy 400 files local → SSH | 70.4 s | 7.5 s |

A 100 MiB file copied down and back up arrived byte-identical (SHA-256), with
no part file left behind.

## Known limits

- **Copies between the local disk and SSH stop at 8**, though 32 measured faster
  (2.4 s against 8.9 s). The disk's one total has to serve both cases: a
  local → local copy, where 4 files is best, and a remote copy, where the disk
  is not the bottleneck. Raising the remote case means telling those apart,
  which the three declarations cannot.
- **S3's numbers are unmeasured.** S3 now gets the parallel walk and the
  read-ahead too, at its read ceiling of 8. Nobody has timed that against a
  real bucket.
- **Same storage means same scheme**, which undercounts a copy between two SSH
  hosts or two buckets.
- `SEARCH_STRATEGY` is still declared and still read by nothing; the read-ahead
  is gated on `is_remote()` and the read ceiling instead.

## Tests

- `test/test_tree_walk.py`: overlap, order, cancel, `on_error`, a shared pool,
  and local walks staying sequential.
- `test/test_content_read.py`: one open giving the same text as a second open
  (BOMs, line endings), read-ahead order, overlap, byte budget, what is left to
  the caller, cancel, and a content search over a real `sftp-server` matching
  the local one.
- `test/test_disk_usage.py`: an SSH tree's totals match the same local tree's.
- `test/test_parallel_copy.py`: the worker count for each pair of storages, the
  override, and an undeclared backend.
- `test/test_path_capabilities.py`: validation, the total capping read and
  write, and the old `LISTING_CONCURRENCY`.
- `test/test_ssh_sftp_session.py`: streaming larger than the window, local ⇄ SSH
  copies, and a failed download keeping the file it would replace.
