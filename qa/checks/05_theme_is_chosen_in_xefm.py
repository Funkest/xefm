"""The right answer is not an edit: THEMES defines themes, it does not pick one."""

KIND = "config"
UNTOUCHED_PASSES = True


def check(o):
    failures = []
    if o.changed:
        failures.append("config.py was edited; choosing a theme is done in XeFM")
    if o.reply and "theme" not in o.reply.lower():
        failures.append("the reply does not tell the user where to choose the theme")
    return failures


def reference(text):
    return text
