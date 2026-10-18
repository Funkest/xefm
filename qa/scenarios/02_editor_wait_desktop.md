+++
title = "VS Code with --wait in the desktop app only"
+++

## Prompt

When I edit a file from the XeFM desktop app, open it in VS Code and wait
until I close the tab. In the terminal version I still want vim.

## Screen

None. The room works on config.py.

## Must

- TEXT_EDITOR keeps its `if is_desktop_mode() else` shape, with only the
  desktop branch changed, to ['code', '--wait'] (or 'code --wait').
- The terminal branch stays 'vim'.
- The reply says a reload applies it.

## Must not

- Warn that XeFM's window freezes or stops responding while the tab is
  open. The desktop app detaches the editor and never waits for it (#644);
  saying --wait is not needed there is fine.
