# XeFM Drives Dialog System

## Overview

The drives picker (the `drives` action, **Go ▸ Drives…**) is a searchable list
of storage locations — fixed locations, mounted volumes, network mounts, SSH
hosts and S3 buckets — that jumps the active pane to the one selected. It has
no module or dialog class of its own: it is a set of `XeFMApp` methods in
`xefm/app.py` that build `{name, path}` rows and hand them to the shared
searchable-list dialog, `show_filter_list()` in `xefm/filter_list_dialog.py`
(the same `FilterListDialog` that favorites and history use).

Related code:
- `xefm/app.py` — `show_drives`, `_local_drives`, `_network_mount_drives`,
  `_windows_drive_roots`, `_ssh_drives`, `_s3_scan_available`,
  `_s3_drives_iter`, `_drive_label`, `_go_to_drive`, `_drive_remove`
- `xefm/config.py` — `get_drive_locations`, `_default_drive_locations`
- `xefm/filter_list_dialog.py` — `FilterListDialog` / `show_filter_list`
  (filtering, the `load_more` background loader, the `on_remove` hook)
- `xefm/netmount.py` — `list_mounts`, `classify` (network / removable volumes)

User-facing docs: [Navigation Dialogs](../NAVIGATION_DIALOGS_FEATURE.md#drives-dialog).

## Rows

`show_drives()` assembles the rows in this order:

1. **Connect to Server…** — macOS and Windows only. An action row
   (`{"action": "connect_server", "path": ""}`), placed first because it is the
   one entry that is not already reachable. `_go_to_drive` opens
   `show_connect_server()` for it instead of moving the pane.
2. **`_local_drives()`** — the fixed locations from `get_drive_locations()`
   (see below), then the mounted volumes:
   - Windows: drive roots from `_windows_drive_roots()` (`os.listdrives()` on
     Python ≥ 3.12, the `GetLogicalDrives` bitmask below that — both only ask
     which letters exist, so an unready drive cannot stall the picker);
   - macOS: the children of `/Volumes`;
   - Linux: the children of `/media/$USER`, `/media` and `/mnt`;
   - plus `_network_mount_drives()`: live network mounts from
     `netmount.list_mounts()`. On macOS these dedupe against `/Volumes`; on
     Windows they are the only way a deviceless (no drive letter) connection
     shows up.

   Rows are de-duplicated by path.
3. **`_ssh_drives()`** — hosts from `~/.ssh/config` (`SSHConfigParser`) as
   `ssh://host/` rows, labelled `user@hostname`. Reads only the local file;
   any failure yields no rows.
4. **S3 buckets** — streamed in after the dialog is open (next section).

Each row is shown by `_drive_label()` as `name — path` (just the name for the
action row), elided in the middle (`elide_where="middle"`) so the path tail
stays visible.

## S3 buckets: the background loader

Listing buckets is a credentialed network call, so it never runs before the
dialog opens or on the UI thread (issue #274). `show_drives()` passes
`_s3_drives_iter` as the dialog's `load_more` loader — only when
`_s3_scan_available()` says boto3 is importable (`xefm.s3.HAS_BOTO3`) and AWS
credentials are plausibly present locally (`_aws_configured()`: an
`AWS_ACCESS_KEY_ID` / `AWS_PROFILE` env var or an `~/.aws/credentials` /
`~/.aws/config` file). Otherwise no loader is attached, so no thread starts and
no spinner shows. EC2 instance-role (IMDS-only) credentials are deliberately not
probed.

`_s3_drives_iter(cancel)` uses `xefm.s3.get_s3_probe_client()`, pages through
`ListBuckets` where the SDK supports a paginator (one call otherwise), checks
`cancel` between pages, records each bucket's region via `note_bucket_region()`
(issue #418), and yields `s3://bucket/` rows. Any AWS error simply ends the
scan with the rows yielded so far — there are no placeholder or error rows.

`FilterListDialog` runs the loader once on a daemon thread
(`_start_load_more`), queues the yielded values, and installs them on the UI
thread from the animation tick (`_drain`), re-applying the active filter and
showing a spinner after the title while the loader runs. Closing the dialog
sets the cancel event. On a backend without animation ticks (chiefly tests),
`_settle()` joins the worker with a bounded wait and drains in one shot.

## Selecting a row

`_go_to_drive()` sends the active pane to the row's path through
`_jump_pane_to()`, the move shared by favorites, history and drives. The
destination is not probed first: the move is provisional, the directory is read
on a worker thread, and if it cannot be read the pane returns to what it was
showing. `ssh://` and `s3://` rows connect on first listing.

## Disconnecting and ejecting

`show_drives()` passes `on_remove=_drive_remove` with
`remove_label="disconnect"`, so the picker's `remove_list_item` key is offered
in the hint band (issue #406). `_drive_remove()` classifies the row with
`netmount.classify()`; anything that is not a network or removable volume
(Home, a drive letter, an SSH host, an S3 bucket) is declined and stays in the
list. For a volume it closes the picker and calls `_release_volume()`, which
moves any pane inside the volume to its parent, re-points the file monitor, and
unmounts or ejects on a worker thread. It always returns False — the row is
never removed in place, because the outcome is not known yet when the hook
returns. See [Network Mount System](NETWORK_MOUNT_SYSTEM.md).

## Configuration

### Key bindings

The `drives` action (alias `drives_dialog`) is bound per keymap preset; see
[Keymap Presets](../KEYMAP_PRESETS_FEATURE.md).

### Fixed locations (`DRIVE_LOCATIONS`)

The rows above the mounted volumes are configurable (issue #356); everything
below them — Windows drive letters, `/Volumes`, `/media`, `/mnt`, the hosts in
`~/.ssh/config`, S3 buckets — is always discovered, never configured.

```python
DRIVE_LOCATIONS = None   # built-in set (default)
DRIVE_LOCATIONS = []     # no fixed rows at all — only what is discovered
DRIVE_LOCATIONS = [{'name': 'Work', 'path': '~/work'}]
```

`config.get_drive_locations()` resolves it, and `XeFMApp._local_drives()` starts
from what it returns. The resolution is deliberately a *replacement*, not a
filter: a user who wants `Documents` gone says what they do want, rather than
naming what to subtract.

Three rules live in `get_drive_locations()`:

- `None` means the built-in set (`_default_drive_locations()`): Home, Root on
  POSIX only — on Windows the drive letters already cover it — and whichever of
  Documents / Downloads / Desktop exist.
- A local path is dropped unless it exists and is a directory. Missing *default*
  folders are silent (no Desktop is normal); a missing *configured* one warns,
  because a hand-written path that isn't there is a typo.
- A path opening with a registered URI scheme (`path_schemes.is_uri()`:
  `ssh://`, `s3://`, …) is passed through unprobed. `Path.exists()` on one would open a connection on
  the UI thread while the picker is being built — the picker's job is to *offer*
  a connection, not to make one.

## Testing

- `test/test_xefm_app_drives.py` — `_local_drives` per platform,
  `_windows_drive_roots`, `_ssh_drives`, `_s3_drives_iter` (paging, cancel,
  region notes, errors), `_s3_scan_available`, network-mount rows, and the
  `show_drives` wiring (no S3 in the eager rows, the Connect to Server row, the
  remove key, the loader attached only with AWS).
- `test/test_drive_locations.py` — `get_drive_locations` and `DRIVE_LOCATIONS`.
- `test/test_filter_list_streaming.py` — the `load_more` background loader.
- `test/test_filter_list_remove.py` — the `on_remove` hook and its key routing.

## Related Documentation

- [S3 Support System](S3_SUPPORT_SYSTEM.md) - S3 integration details
- [Dialog System](DIALOG_SYSTEM.md) - General dialog framework
- [Network Mount System](NETWORK_MOUNT_SYSTEM.md) - disconnect / eject and Connect to Server
- [XeFM Application Overview](XEFM_APPLICATION_OVERVIEW.md) - Overall application architecture
