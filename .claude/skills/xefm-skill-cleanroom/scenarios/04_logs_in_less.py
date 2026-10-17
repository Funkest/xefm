"""A new FILE_ASSOCIATIONS rule, for one backend."""

from outcome import argv, association

TITLE = "View .log files in less (terminal)"
KIND = "config"
PROMPT = """\
In XeFM's terminal mode, pressing V on a .log file should show it in less
instead of the built-in viewer.
"""
MUST = """\
- Add one FILE_ASSOCIATIONS rule: pattern '*.log', 'view': ['less'] (or
  'less'); leave the existing rules as they are.
- Say that it applies in the terminal; in the desktop app less has no
  terminal to run in (a conditional on is_desktop_mode(), or a note, both do).
Must not: mark it with a terminal option (associations have none).
"""


def check(o):
    failures = []
    found, value = association(o.config("tui"), "server.log", "view")
    if not found or argv(value)[:1] != ["less"]:
        failures.append(f"V on server.log runs {value!r}, not less")
    before = len(_rules(o.before))
    after = o.config("tui").get("FILE_ASSOCIATIONS") or []
    if len(after) < before:
        failures.append(f"FILE_ASSOCIATIONS lost rules ({before} -> {len(after)})")
    jpg = association(o.config("tui"), "photo.jpg", "view")
    if jpg != (True, None):
        failures.append(f"V on a .jpg changed to {jpg}")
    return failures


def _rules(text):
    from outcome import inspect_config
    return inspect_config(text)["values"].get("FILE_ASSOCIATIONS") or []


def reference(text):
    anchor = "        # Add your own file associations here:\n"
    rule = "        {'pattern': '*.log', 'view': ['less']},\n"
    return text.replace(anchor, rule + anchor, 1)
