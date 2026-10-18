+++
title = "Put Reload Configuration on F12"
+++

## Prompt

I edit my XeFM config in another editor window all the time. Can you put
Reload Configuration on F12 so I don't have to go through the menu?

## Screen

None. The room works on config.py (the "bare" fixture: no template comments).

## Must

- reload_config is on F12 in the existing KEY_BINDINGS, not in a second
  KEY_BINDINGS block, and nothing else is on F12.
- Every other line of config.py is as it was.
- The reply tells the user to reload (or restart) once, since this edit is
  what makes the key exist.

## Must not

- Guess the action name from the menu label (e.g. 'reload').
