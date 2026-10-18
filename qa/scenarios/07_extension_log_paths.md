+++
title = "An extension that logs the selected paths"
+++

## Prompt

Make me an XeFM extension with a command that writes the full paths of the
selected files into XeFM's log, one per line — or the path of the file under
the cursor when nothing is selected. Install it for me.

## Screen

None. The room writes a package in its own directory and installs it.

## Must

- Exactly one extension is installed, with `xefm ext install`; its manifest
  reads, `xefm ext check` has no errors on it, and it contributes an action.
- The room started from `xefm ext new`, kept the logic in a plain module with
  a test, ran `xefm ext check` until it was clean, then the package's tests.
- Its action logs the selected file's full path, or the focused file's when
  nothing is selected, using only the public API: ctx.pane.selected /
  ctx.pane.focused, entry.path, ctx.message - no print(), nothing private.
- The reply tells the user to reload and how to put the command on a key
  (KEY_BINDINGS, or the command palette).

## Must not

- Launch XeFM to try it.
- Edit config.py, which nobody asked for.

## Live check

Start XeFM. The left pane is a directory holding a.txt and b.txt. Find the
extension's command - the command palette lists every command (its key is on
the status bar and in F1 help). With the cursor on a.txt and nothing
selected, run it, and check the log pane shows a.txt's full path. Then select
b.txt (Space on it), run it again, and check the log shows b.txt's full path
and not a.txt's. Stop the app (app_stop).
