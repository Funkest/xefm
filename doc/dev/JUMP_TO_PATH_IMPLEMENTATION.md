# Jump to Path — Implementation

User-facing behaviour: [Navigation Dialogs → Jump to Path](../NAVIGATION_DIALOGS_FEATURE.md#jump-to-path).

## Overview

`jump_to_path` is a single-line prompt, not a list picker: `XeFMApp.jump_to_path`
(`xefm/app.py`) opens an `InputDialog` (`show_input`, see
[Dialog System](DIALOG_SYSTEM.md#inputdialog--show_input)) titled *Jump to Path*,
anchored to the active pane's region. Nothing is scanned; the only filesystem
calls are the ones the typed path itself needs.

(An earlier, TFM-era design scanned the current directory tree in the background
and listed every subdirectory. It no longer exists.)

## Flow

1. **Prefill.** The field starts with the pane's current path plus a trailing
   separator — `os.sep` for a local pane, `/` for a URI — so a child name can be
   typed at once. `select_all=False` keeps that text rather than selecting it.
2. **Completion.** Tab goes to a `FilepathCompleter`
   (`xefm/completion.py`) rooted at the current directory, with
   `directories_only=False` (a file is a valid target, #351) and the pane's
   `show_hidden`.
3. **Resolve.** `_resolve_jump_target(text, current)` turns the text into a
   `Path`:
   - a URI (`path_schemes.is_uri`: `s3://`, `ssh://`, any `PATH_SCHEMES` entry)
     is taken as written;
   - `~` (followed by `/` *or* `os.sep`) is joined to `Path.home()`;
   - a relative path is joined to `current`;
   - a local result is `os.path.normpath`-ed; a remote one is not, since
     normpath would collapse `scheme://` to `scheme:/` (#318).
4. **Validate** (Enter, before the dialog closes): empty text and a target whose
   `exists()` is false are rejected with a message in the dialog, which stays
   open.
5. **Accept.** One `is_dir()` call decides: a directory is the destination; a
   file sends the pane to its parent with the cursor on its name. Both go
   through `_go_to_dir`, which leaves virtual (search-results) mode, clears the
   selection, re-lists and lands the cursor.

## Error handling

`exists()` and `is_dir()` run inside a local `probe` helper. A path scheme is
user-supplied code, and this prompt is the first place a typed URI reaches it;
whatever it raises is reported through `report_user_failure` (log + traceback)
instead of escaping the key handler and leaving Enter silently dead. During
validation the exception's text also becomes the dialog's error; during accept
the pane simply stays where it was.

## Tests

`test/test_jump_to_path.py` — `_resolve_jump_target` for local, `~`, relative,
whitespace and remote input, and the dialog flow (file target focuses the file,
directory target navigates, missing and empty input rejected, completion offers
files).
