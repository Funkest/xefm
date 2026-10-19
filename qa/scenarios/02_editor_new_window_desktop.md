+++
title = "VS Code in a new window, in the desktop app only"
+++

## Prompt

When I edit a file from the XeFM desktop app, open it in a new VS Code
window instead of a tab in the one I already have. In the terminal version
I still want vim.

## Screen

None. The room works on config.py.

## Must

- TEXT_EDITOR keeps its `if is_desktop_mode() else` shape, with only the
  desktop branch changed, to ['code', '--new-window'] (or 'code -n' and the
  like).
- The terminal branch stays 'vim'.
- The reply says a reload applies it.
