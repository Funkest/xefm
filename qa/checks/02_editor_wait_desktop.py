"""An edit inside a conditional the user (or the template) wrote."""

from outcome import argv

KIND = "config"

#: Words a reply uses when it wrongly warns that XeFM itself will wait.
_WARNED = ("unresponsive", "freeze", "frozen", "won't respond", "will not respond")


def check(o):
    failures = []
    gui = argv(o.config("gui").get("TEXT_EDITOR"))
    tui = argv(o.config("tui").get("TEXT_EDITOR"))
    if gui[:1] != ["code"] or "--wait" not in gui:
        failures.append(f"desktop TEXT_EDITOR is {gui}, not code --wait")
    if tui != ["vim"]:
        failures.append(f"terminal TEXT_EDITOR became {tui}")
    warned = [w for w in _WARNED if w in (o.reply or "").lower()]
    if warned:
        failures.append(f"the reply warns the window will hang ({warned[0]!r}); "
                        "the desktop app does not wait for the editor")
    return failures


def reference(text):
    return text.replace("    TEXT_EDITOR = 'code' if is_desktop_mode() else 'vim'",
                        "    TEXT_EDITOR = ['code', '--wait'] if is_desktop_mode() else 'vim'", 1)
