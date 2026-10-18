"""A request in Japanese, appending to a list the user has already extended."""

KIND = "config"

_BEFORE = ["Home", "Documents", "Downloads", "Desktop", "Notes"]


def check(o):
    failures = []
    favorites = [f for f in o.config().get("FAVORITES") or [] if isinstance(f, dict)]
    names = [f.get("name") for f in favorites]
    added = [f for f in favorites if f.get("name") == "Projects"]
    if not added:
        return [f"no 'Projects' favorite (FAVORITES names: {names})"]
    path = str(added[0].get("path", ""))
    if not path.rstrip("/").endswith("work/projects"):
        failures.append(f"'Projects' points at {path!r}")
    if [n for n in names if n in _BEFORE] != _BEFORE:
        failures.append(f"the existing favorites changed order: {names}")
    if len(added) != 1:
        failures.append("'Projects' was added more than once")
    return failures


def reference(text):
    anchor = "        {'name': 'Notes', 'path': '~/notes'},  # keep: my notes\n"
    return text.replace(anchor, anchor + "        {'name': 'Projects', 'path': '~/work/projects'},\n", 1)
