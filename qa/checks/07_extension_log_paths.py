"""The extension half of the skill, end to end: scaffold, check, test, install."""

KIND = "extension"


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
    failures += _run_its_actions(manifest, o.installed[0])
    return failures


#: Runs each contributed action against a fake ctx shaped like the real API
#: (selected() a method, focused a property, a '..' entry in the listing) —
#: in a subprocess, so the package's imports cannot collide with this one's.
_PROBE = r"""
import importlib, json, pathlib, sys
root, refs = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, root)
class E:
    def __init__(self, name, is_dir=False):
        self.name, self.is_dir, self.is_file, self.is_link = name, is_dir, not is_dir, False
        self.path = pathlib.Path("/data/work") / name if name != ".." else pathlib.Path("/data")
        self.stem, self.suffix = self.path.stem, self.path.suffix
        self.size, self.mtime = 1, 0.0
class Pane:
    def __init__(self, chosen):
        self.entries = [E("..", True), E("a.txt"), E("b.txt")]
        self._chosen = chosen
        self.cursor = 1
        self.focused = self.entries[1]
        self.path = pathlib.Path("/data/work")
    def selected(self):
        return [e for e in self.entries if e.name in self._chosen]
class Settings: pass
class State:
    def get(self, key, default=None): return default
    def set(self, key, value): pass
class Ext:
    id, version, settings, state = "x", "0", Settings(), State()
    data_dir = pathlib.Path("/tmp")
results = {}
for ref in refs:
    module, name = ref.split(":")
    func = getattr(importlib.import_module(module), name)
    seen = {}
    for case, chosen in (("selected", ["b.txt"]), ("nothing selected", [])):
        lines = []
        ctx = type("Ctx", (), {})()
        ctx.pane = ctx.left = Pane(chosen)
        ctx.other = ctx.right = Pane([])
        ctx.message = lambda text, lines=lines: lines.extend(str(text).splitlines())
        ctx.extension = Ext()
        try:
            func(ctx)
            seen[case] = lines
        except Exception as exc:
            seen[case] = f"raised {type(exc).__name__}: {exc}"
    results[ref] = seen
print(json.dumps(results))
"""


def _run_its_actions(manifest, root):
    """Each action, run on a selection and on the cursor alone: the paths it
    logs must be the selected file's, then the focused file's."""
    import json
    import subprocess
    import sys
    actions = (manifest.data.get("contributes") or {}).get("actions") or {}
    refs = [v["entry"] if isinstance(v, dict) else v for v in actions.values()]
    done = subprocess.run([sys.executable, "-c", _PROBE, str(root), json.dumps(refs)],
                          capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        return [f"its actions could not be run: {done.stderr.strip()[-300:]}"]
    failures = []
    expected = {"selected": ["/data/work/b.txt"], "nothing selected": ["/data/work/a.txt"]}
    for ref, seen in json.loads(done.stdout.strip().splitlines()[-1]).items():
        for case, want in expected.items():
            if seen[case] != want:
                failures.append(f"{ref} with {case} logged {seen[case]!r}, not {want!r}")
    return failures


reference = None
