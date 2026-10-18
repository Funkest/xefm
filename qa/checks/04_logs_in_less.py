"""A new FILE_ASSOCIATIONS rule, for one backend."""

from outcome import argv, association

KIND = "config"
#: The user's file has no FILE_ASSOCIATIONS. Writing one with just the new
#: rule replaces every default rule (PDFs, images, …); the default entries
#: have to be carried over.
FIXTURE = "bare"


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
    from outcome import template_source
    default = template_source("FILE_ASSOCIATIONS")
    rule = "        {'pattern': '*.log', 'view': ['less']},\n    ]"
    assert default.endswith("\n    ]")
    addition = default[:-len("\n    ]")] + "\n" + rule + "\n"
    anchor = "    CONFIRM_DELETE = False"
    return text.replace(anchor, addition + anchor, 1)
