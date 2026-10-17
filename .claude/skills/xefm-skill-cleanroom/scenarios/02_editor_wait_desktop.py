"""An edit inside a conditional the user (or the template) wrote."""

from outcome import argv

TITLE = "VS Code with --wait in the desktop app only"
KIND = "config"
PROMPT = """\
When I edit a file from the XeFM desktop app, open it in VS Code and wait
until I close the tab. In the terminal version I still want vim.
"""
MUST = """\
- Keep TEXT_EDITOR's `if is_desktop_mode() else` shape and change only the
  desktop branch, to ['code', '--wait'] (or 'code --wait').
- The terminal branch stays 'vim'.
- Warn that XeFM waits for the editor to exit, so with --wait the desktop
  app's window is unresponsive until the tab is closed.
- Say a reload applies it.
"""

#: Words a reply uses when it warns that XeFM itself will wait.
_WARNED = ("unresponsive", "freeze", "frozen", "block", "busy", "until you close",
           "until the tab", "won't respond", "will not respond", "can't use")


def check(o):
    failures = []
    gui = argv(o.config("gui").get("TEXT_EDITOR"))
    tui = argv(o.config("tui").get("TEXT_EDITOR"))
    if gui[:1] != ["code"] or "--wait" not in gui:
        failures.append(f"desktop TEXT_EDITOR is {gui}, not code --wait")
    if tui != ["vim"]:
        failures.append(f"terminal TEXT_EDITOR became {tui}")
    if o.reply and not any(w in o.reply.lower() for w in _WARNED):
        failures.append("the reply does not warn that XeFM waits while the tab is open")
    return failures


def reference(text):
    return text.replace("    TEXT_EDITOR = 'code' if is_desktop_mode() else 'vim'",
                        "    TEXT_EDITOR = ['code', '--wait'] if is_desktop_mode() else 'vim'", 1)
