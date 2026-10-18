+++
title = "Ctrl-T for hidden files (Ctrl-T is the command palette)"
+++

## Prompt

I want Ctrl-T to show and hide hidden files in XeFM.

## Screen

None. The room works on config.py.

## Must

- toggle_hidden is bound to Ctrl-T (keeping '.' is fine).
- The room notices Ctrl-T is the command palette under the AFX preset and
  says so; no key is left bound twice: command_palette gets its other key(s)
  or [], explicitly, and the reply says where the palette went.
- The palette's new key works in a terminal too: not Ctrl-Shift-<letter>
  (Ctrl-Shift-P arrives as Ctrl-P, which is copy_paths) and not Cmd-….
