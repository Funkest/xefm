"""A key for an action that has none: the plainest config edit there is."""

from outcome import actions_on, effective_keymap, keys_of, same_key

TITLE = "Put Reload Configuration on F12"
KIND = "config"
#: No template comments to copy from: no commented example of this very
#: entry, no "a key no preset uses" note. The name and the free key have to
#: come from the skill.
FIXTURE = "bare"
PROMPT = """\
I edit my XeFM config in another editor window all the time. Can you put
Reload Configuration on F12 so I don't have to go through the menu?
"""
MUST = """\
- Add 'reload_config': ['F12'] to the existing KEY_BINDINGS, not a second
  KEY_BINDINGS block.
- Leave every other line of config.py as it was.
- Tell the user to reload (or restart) once, since this edit is what makes
  the key exist.
Must not: guess the action name from the menu label (e.g. 'reload').
"""


def check(o):
    values = o.config()
    failures = []
    own = keys_of((values.get("KEY_BINDINGS") or {}).get("reload_config"))
    if not any(same_key(k, "F12") for k in own):
        failures.append(f"reload_config is not on F12 in KEY_BINDINGS (has {own})")
    others = [a for a in actions_on(effective_keymap(values), "F12") if a != "reload_config"]
    if others:
        failures.append(f"F12 is also bound to {others}")
    if o.after.count("KEY_BINDINGS = {") != 1:
        failures.append("KEY_BINDINGS is assigned more than once")
    return failures


def reference(text):
    return text.replace("    KEY_BINDINGS = {\n",
                        "    KEY_BINDINGS = {\n        'reload_config': ['F12'],\n", 1)
