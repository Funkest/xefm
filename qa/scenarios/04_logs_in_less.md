+++
title = "View .log files in less (terminal)"
+++

## Prompt

In XeFM's terminal mode, pressing V on a .log file should show it in less
instead of the built-in viewer.

## Screen

None. The room works on config.py (the "bare" fixture, which has no
FILE_ASSOCIATIONS).

## Must

- FILE_ASSOCIATIONS is added with XeFM's default rules carried over and one
  new rule: pattern '*.log', 'view': ['less'] (or 'less'). The file had none,
  so a list holding only the new rule would drop every default (V on a .jpg
  would change).
- It is said to apply in the terminal: in the desktop app less has no
  terminal to run in. A conditional on is_desktop_mode(), or a note in the
  reply, both do.

## Must not

- Mark the rule with a terminal option (associations have none).
