"""A key the preset already uses: the room has to notice and resolve it."""

from outcome import actions_on, effective_keymap, keys_of, same_key, terminal_safe

TITLE = "Ctrl-T for hidden files (Ctrl-T is the command palette)"
KIND = "config"
PROMPT = """\
I want Ctrl-T to show and hide hidden files in XeFM.
"""
MUST = """\
- Bind toggle_hidden to Ctrl-T (keeping '.' is fine).
- Notice Ctrl-T is the command palette under the AFX preset, say so, and
  leave no key bound twice: give command_palette its other key(s) or [],
  explicitly, and tell the user where the palette went.
- The palette's new key works in a terminal too — not Ctrl-Shift-<letter>
  (Ctrl-Shift-P arrives as Ctrl-P, which is copy_paths) and not Cmd-….
"""


def check(o):
    failures = []
    keymap = effective_keymap(o.config())
    if not any(same_key(k, "Ctrl-T") for k in keys_of(keymap.get("toggle_hidden"))):
        failures.append(f"toggle_hidden has {keys_of(keymap.get('toggle_hidden'))}, not Ctrl-T")
    if (bound := actions_on(keymap, "Ctrl-T")) != ["toggle_hidden"]:
        failures.append(f"Ctrl-T is bound to {bound}")
    palette = keys_of(keymap.get("command_palette"))
    if palette and not any(terminal_safe(k) for k in palette):
        failures.append(f"command_palette moved to {palette}, which a terminal "
                        f"cannot send")
    if o.reply and "palette" not in o.reply.lower():
        failures.append("the reply does not mention the command palette losing Ctrl-T")
    return failures


def reference(text):
    return text.replace(
        "    KEY_BINDINGS = {\n",
        "    KEY_BINDINGS = {\n        'toggle_hidden': ['.', 'Ctrl-T'],\n"
        "        'command_palette': ['F2'],\n", 1)
