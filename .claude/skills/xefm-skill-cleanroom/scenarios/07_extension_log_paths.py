"""The extension half of the skill, end to end: scaffold, check, test, install."""

TITLE = "An extension that logs the selected paths"
KIND = "extension"
PROMPT = """\
Make me an XeFM extension with a command that writes the full paths of the
selected files into XeFM's log, one per line — or the path of the file under
the cursor when nothing is selected. Install it for me.
"""
MUST = """\
- Start from `xefm ext new`, keep logic in a plain module with a test, and
  run `xefm ext check` until it is clean, then the package's tests.
- Use only the public API: ctx.pane.selected / ctx.pane.focused,
  entry.path, ctx.message — no print(), nothing private.
- Install with `xefm ext install`, and tell the user to reload and how to
  put the command on a key (KEY_BINDINGS, or the command palette).
Must not: launch XeFM to try it; edit config.py unasked.
"""


def check(o):
    from xefm import extensions as ext
    failures = []
    if len(o.installed) != 1:
        return [f"expected one installed extension, found {len(o.installed)}"]
    try:
        manifest = ext.read_manifest(o.installed[0])
    except Exception as e:
        return [f"its manifest does not read: {e}"]
    if errors := ext.errors(ext.check_manifest(manifest, machine=False)):
        failures.append(f"`xefm ext check` errors: {[p.message for p in errors][:3]}")
    if not (manifest.data.get("contributes") or {}).get("actions"):
        failures.append("it contributes no action")
    if not any(c.startswith("ext check") for c in o.xefm_calls):
        failures.append("the room never ran `xefm ext check`")
    if o.changed:
        failures.append("config.py was edited, which nobody asked for")
    return failures


reference = None
