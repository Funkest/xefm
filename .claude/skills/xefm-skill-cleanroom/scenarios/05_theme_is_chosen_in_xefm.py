"""The right answer is not an edit: THEMES defines themes, it does not pick one."""

TITLE = "Switch to Dracula (not a config edit)"
KIND = "config"
UNTOUCHED_PASSES = True
PROMPT = """\
Switch XeFM to the Dracula theme.
"""
MUST = """\
- Leave config.py unchanged: Dracula is built in, and the theme in use is
  chosen in XeFM (View ▸ Theme, or View ▸ Next Theme) and remembered there.
- Tell the user how to pick it.
Must not: add a 'Dracula' entry to THEMES, or invent a THEME = 'Dracula'
setting.
"""


def check(o):
    failures = []
    if o.changed:
        failures.append("config.py was edited; choosing a theme is done in XeFM")
    if o.reply and "theme" not in o.reply.lower():
        failures.append("the reply does not tell the user where to choose the theme")
    return failures


def reference(text):
    return text
