"""An older config binds an action under its old name."""

from outcome import BARE, actions_on, effective_keymap, keys_of, same_key

KIND = "config"
#: The user's file still says `drives_dialog`, which is `drives` today.
FIXTURE = BARE.replace(
    "        'quit': ['Shift-Q'],  # keep: no accidental quits\n",
    "        'quit': ['Shift-Q'],  # keep: no accidental quits\n"
    "        'drives_dialog': ['D'],  # from my old config\n")


def check(o):
    failures = []
    own = o.config().get("KEY_BINDINGS") or {}
    names = [n for n in ("drives", "drives_dialog") if n in own]
    if len(names) != 1:
        return [f"KEY_BINDINGS has {names or 'no entry'} for the drives list"]
    keys = keys_of(own[names[0]])
    for wanted in ("F3", "D"):
        if not any(same_key(k, wanted) for k in keys):
            failures.append(f"{names[0]} lacks {wanted} (has {keys})")
    others = [a for a in actions_on(effective_keymap(o.config()), "F3")
              if a not in ("drives", "drives_dialog")]
    if others:
        failures.append(f"F3 is also bound to {others}")
    return failures


def reference(text):
    return text.replace("'drives_dialog': ['D'],", "'drives_dialog': ['D', 'F3'],", 1)
