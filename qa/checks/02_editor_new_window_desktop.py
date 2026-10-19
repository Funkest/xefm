"""An edit inside a conditional the user (or the template) wrote.

This scenario used to ask for `code --wait` in the desktop app, which the
desktop app never waits for (#644): the edit changed nothing, and a room that
said so and left the config alone failed the check. The request is now one
that changes what the user sees."""

from outcome import argv

KIND = "config"

_NEW_WINDOW = ("--new-window", "-n")


def check(o):
    failures = []
    gui = argv(o.config("gui").get("TEXT_EDITOR"))
    tui = argv(o.config("tui").get("TEXT_EDITOR"))
    if gui[:1] != ["code"] or not any(flag in gui for flag in _NEW_WINDOW):
        failures.append(f"desktop TEXT_EDITOR is {gui}, not code --new-window")
    if tui != ["vim"]:
        failures.append(f"terminal TEXT_EDITOR became {tui}")
    return failures


def reference(text):
    return text.replace("    TEXT_EDITOR = 'code' if is_desktop_mode() else 'vim'",
                        "    TEXT_EDITOR = ['code', '--new-window'] if is_desktop_mode() else 'vim'", 1)
