"""A key for an action that has none: the plainest config edit there is."""

from outcome import actions_on, effective_keymap, keys_of, same_key

KIND = "config"
#: No template comments to copy from: no commented example of this very
#: entry, no "a key no preset uses" note. The name and the free key have to
#: come from the skill.
FIXTURE = "bare"


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
