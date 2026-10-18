+++
title = "One more key for an action bound under its old name"
+++

## Prompt

In XeFM I'd like F3 to open the drives list too, not just D.

## Screen

None. The room works on config.py (a fixture that binds the drives list
under its old name, "drives_dialog").

## Must

- `drives_dialog` is recognised as the old name of `drives`, and F3 is added
  to that entry (renaming it to `drives` is fine), keeping D.
- There is one entry for the action, not `drives_dialog` and `drives` both.

## Must not

- Delete the old-name entry as unknown.
