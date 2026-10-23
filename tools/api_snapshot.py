"""Write, check and compare the snapshot of XeFM's public API (#713, plan §7.1).

The snapshot, ``test/data/api_snapshot.txt``, is one line per item — every
public name in ``xefm.user_api`` and ``xefm.path_base`` with its signature, the
``Path`` members extensions are handed, the ``ReadOnlyPathImpl`` tiers, the
compatibility import paths, the keys each ``config.py`` table and manifest
section accepts, and the promised capabilities — each marked ``stable``,
``preview`` or ``deprecated``. ``test/test_api_snapshot.py`` regenerates it in memory and fails
on any difference, so every API change shows up as a diff of this file.

Regenerating is the deliberate step, and it is where a breaking change to the
stable part is caught: ``--write`` refuses one unless ``API_VERSION`` was
bumped in the same change. Deprecating a stable API is not breaking; removing
it is, and removing one that was never deprecated says so.

Usage (from the repo root):
    PYTHONPATH=. python tools/api_snapshot.py --check   # exit 1 on any difference
    PYTHONPATH=. python tools/api_snapshot.py --write   # regenerate the file
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path as FilePath

SNAPSHOT = FilePath(__file__).resolve().parent.parent / "test" / "data" / "api_snapshot.txt"

#: Constructors that are API, and which of their parameters are. Only XeFM
#: builds an ``ActionContext`` or a ``PaneApi``; extension tests build
#: ``EntryInfo`` fakes, and ``name=`` is the listing's own business.
CONSTRUCTORS = {
    "xefm.user_api.EntryInfo": ("path", "is_dir", "is_link"),
    "xefm.path_base.UriStatResult": None,          # every parameter
}

#: The import paths kept working for configs written before the names moved
#: to ``xefm.user_api`` (plan §2.5).
COMPAT_IMPORTS = {
    "xefm.external_programs.xefm_tool": "xefm_tool",
    "xefm.external_programs.xefm_python": "xefm_python",
    "xefm.backend_detector.is_desktop_mode": "is_desktop_mode",
}

_KIND = {
    inspect.Parameter.POSITIONAL_ONLY: "pos",
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "pk",
    inspect.Parameter.KEYWORD_ONLY: "kw",
    inspect.Parameter.VAR_POSITIONAL: "*",
    inspect.Parameter.VAR_KEYWORD: "**",
}


# --------------------------------------------------------------------------- #
# Building
# --------------------------------------------------------------------------- #

def _signature(func, keep=None) -> str:
    """``func``'s parameters as JSON — ``[name, kind, default-or-null]`` each.
    Annotations are left out: changing one breaks no caller."""
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return "?"
    out = []
    for p in params:
        if keep is not None and p.name not in keep and p.name != "self":
            continue
        default = None if p.default is inspect.Parameter.empty else repr(p.default)
        out.append([p.name, _KIND[p.kind], default])
    return json.dumps(out)


def _member(owner, name: str) -> tuple[str, str]:
    """``(kind, detail)`` for the attribute ``name`` of class ``owner``."""
    raw = inspect.getattr_static(owner, name)
    if isinstance(raw, property):
        return "property", "rw" if raw.fset else "ro"
    if isinstance(raw, classmethod):
        return "classmethod", _signature(getattr(owner, name))
    if isinstance(raw, staticmethod):
        return "staticmethod", _signature(getattr(owner, name))
    if inspect.isfunction(raw):
        return "method", _signature(raw)
    return "attribute", ""


def build() -> dict[str, tuple[str, str, str]]:
    """``{name: (status, kind, detail)}`` for the whole public surface."""
    import xefm.backend_detector as backend_detector
    import xefm.external_programs as external_programs
    import xefm.path as xpath
    import xefm.path_base as path_base
    import xefm.user_api as user_api
    from xefm import extensions as ext
    from xefm.preview import is_deprecated, is_preview

    items: dict[str, tuple[str, str, str]] = {}

    def put(name: str, kind: str, detail: str = "", *, status=None) -> None:
        if status is None:
            status = ("deprecated" if is_deprecated(name) is not None
                      else "preview" if is_preview(name) else "stable")
        items[name] = (status, kind, detail)

    put("xefm.user_api.API_VERSION", "version", str(user_api.API_VERSION),
        status="stable")

    for module in (user_api, path_base):
        for attr in module.__all__:
            name = f"{module.__name__}.{attr}"
            obj = getattr(module, attr)
            if name == "xefm.user_api.API_VERSION":
                continue
            if inspect.isclass(obj):
                put(name, "class")
                if name in CONSTRUCTORS:
                    put(f"{name}.__init__", "constructor",
                        _signature(obj.__init__, CONSTRUCTORS[name]),
                        status=items[name][0])
                if module is path_base:
                    continue        # its members are the tiers, below
                for member in sorted(dir(obj)):
                    if not member.startswith("_"):
                        put(f"{name}.{member}", *_member(obj, member))
            elif callable(obj):
                put(name, "function", _signature(obj))
            else:
                put(name, "data", type(obj).__name__)

    for tier, names in path_base.TIERS.items():
        for member in names:
            owner = path_base.ReadOnlyPathImpl
            kind, detail = _member(owner, member) if hasattr(owner, member) \
                else ("attribute", "")
            put(f"xefm.path_base.ReadOnlyPathImpl.{member}", f"tier:{tier}",
                f"{kind} {detail}".strip())

    for member in sorted(dir(xpath.Path)):
        if not member.startswith("_"):
            put(f"xefm.path.Path.{member}", *_member(xpath.Path, member),
                status="stable")
    for capability in sorted(xpath.STABLE_CAPABILITIES):
        put(f"capability.{capability}", "capability", status="stable")

    for path, attr in COMPAT_IMPORTS.items():
        module = external_programs if path.startswith("xefm.external_programs") \
            else backend_detector
        same = getattr(module, path.rsplit(".", 1)[1]) is getattr(user_api, attr)
        put(path, "compat", f"is xefm.user_api.{attr}" if same else "DIFFERENT",
            status="stable")

    for table in sorted(set(ext.CONTRIBUTION_TABLES.values()) - {"THEMES"}):
        put(f"config.{table}", "table",
            ",".join(sorted(user_api.TABLE_KEYS.get(table, ()))))
    put("config.PATH_SCHEMES.override", "table-key")
    put("config.EVENT_HOOKS.events", "names", ",".join(sorted(user_api.EVENTS)),
        status=items["config.EVENT_HOOKS"][0])

    put("manifest", "sections", ",".join(sorted(ext._KNOWN_SECTIONS)), status="stable")
    put("manifest.extension", "keys", ",".join(sorted(ext._KNOWN_EXTENSION_KEYS)),
        status="stable")
    put("manifest.extension.updates", "key")
    for kind in sorted(set(ext.CONTRIBUTION_TABLES) | {"key_suggestions"}):
        detail = ",".join(ext.ACTION_ENTRY_KEYS) if kind == "actions" else ""
        put(f"manifest.contributes.{kind}", "section", detail)
    put("manifest.settings", "keys", ",".join(sorted(ext.SETTINGS_KEYS)))
    put("manifest.requires", "keys", ",".join(sorted(ext.REQUIRES_KEYS)))
    return items


def render(items: dict[str, tuple[str, str, str]]) -> str:
    lines = [f"{status}\t{kind}\t{name}\t{detail}".rstrip("\t")
             for name, (status, kind, detail) in sorted(items.items())]
    return ("# XeFM public API snapshot — regenerate with "
            "`PYTHONPATH=. python tools/api_snapshot.py --write`.\n"
            "# status\tkind\tname\tdetail\n" + "\n".join(lines) + "\n")


def parse(text: str) -> dict[str, tuple[str, str, str]]:
    items = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        status, kind, name, *rest = line.split("\t")
        items[name] = (status, kind, rest[0] if rest else "")
    return items


# --------------------------------------------------------------------------- #
# Comparing
# --------------------------------------------------------------------------- #

def _signature_breaks(old: str, new: str) -> list[str]:
    """Why a caller written against ``old`` would break on ``new``."""
    try:
        before, after = json.loads(old), json.loads(new)
    except ValueError:
        return [f"signature changed from {old} to {new}"]
    reasons = []
    now = {p[0]: (i, p) for i, p in enumerate(after)}
    has_var_kw = any(p[1] == "**" for p in after)
    for i, (name, kind, default) in enumerate(before):
        if name not in now:
            if not (kind in ("kw", "pk") and has_var_kw):
                reasons.append(f"parameter '{name}' removed")
            continue
        j, (_, new_kind, new_default) = now[name]
        if kind in ("pos", "pk") and new_kind in ("pos", "pk") and i != j:
            reasons.append(f"parameter '{name}' moved from position {i} to {j}")
        if kind == "pk" and new_kind in ("pos", "kw"):
            reasons.append(f"parameter '{name}' is no longer positional-or-keyword")
        if kind == "kw" and new_kind == "pos":
            reasons.append(f"parameter '{name}' is no longer a keyword")
        if default is not None and new_default is None:
            reasons.append(f"parameter '{name}' lost its default")
        elif default is not None and new_default != default:
            reasons.append(f"parameter '{name}' default changed from {default} to {new_default}")
    old_names = {p[0] for p in before}
    for name, kind, default in after:
        if name not in old_names and default is None and kind in ("pos", "pk", "kw"):
            reasons.append(f"required parameter '{name}' added")
    return reasons


def _keys_break(old: str, new: str) -> list[str]:
    gone = set(filter(None, old.split(","))) - set(filter(None, new.split(",")))
    return [f"'{key}' removed" for key in sorted(gone)]


#: The statuses a caller may rely on: a deprecated API still works.
_PROMISED = ("stable", "deprecated")


def classify(old, new) -> list[tuple[str, str, str]]:
    """Every difference as ``(category, name, why)`` — category ``breaking``
    (to a promised API), ``addition`` (to a stable API), ``deprecation`` or
    ``preview``. Promised means stable or deprecated."""
    out = []
    for name in sorted(set(old) | set(new)):
        before, after = old.get(name), new.get(name)
        if before == after or (before and before[1] == "version"):
            continue
        if after is None:
            if before[0] == "stable":
                out.append(("breaking", name,
                            "removed without being deprecated first"))
            else:
                out.append(("breaking" if before[0] == "deprecated" else "preview",
                            name, "removed"))
        elif before is None:
            out.append(("addition" if after[0] in _PROMISED else "preview",
                        name, "added"))
        elif before[0] == "stable" and after[0] == "deprecated":
            out.append(("deprecation", name, "deprecated"))
        elif before[0] == "deprecated" and after[0] == "stable":
            out.append(("addition", name, "no longer deprecated"))
        elif before[0] in _PROMISED and after[0] == "preview":
            out.append(("breaking", name, f"demoted from {before[0]} to Preview"))
        elif before[0] == "preview" and after[0] in _PROMISED:
            out.append(("addition", name, f"promoted from Preview to {after[0]}"))
        elif before[0] == "preview":
            out.append(("preview", name, f"{before[1:]} → {after[1:]}"))
        else:
            reasons = _changes(before, after)
            out.append(("breaking", name, "; ".join(reasons)) if reasons
                       else ("addition", name, f"{before[2]} → {after[2]}"))
    return out


def _changes(before, after) -> list[str]:
    """Why a stable item's change breaks callers; empty when it only adds."""
    (_, kind, old), (_, new_kind, new) = before, after
    if kind != new_kind:
        return [f"changed from {kind} to {new_kind}"]
    if kind in ("function", "method", "classmethod", "staticmethod", "constructor"):
        return _signature_breaks(old, new)
    if kind.startswith("tier:"):
        old_kind, _, old_sig = old.partition(" ")
        new_kind2, _, new_sig = new.partition(" ")
        if old_kind != new_kind2:
            return [f"changed from {old_kind} to {new_kind2}"]
        return _signature_breaks(old_sig, new_sig) if old_sig.startswith("[") else []
    if kind == "property":
        return ["lost its setter"] if old == "rw" and new == "ro" else []
    if kind in ("table", "keys", "sections", "section", "names"):
        return _keys_break(old, new)
    return [f"changed from {old!r} to {new!r}"]


def version(items) -> int:
    return int(items["xefm.user_api.API_VERSION"][2])


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    current = build()
    stored = parse(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
    changes = classify(stored, current)
    for category, name, why in changes:
        print(f"{category}: {name}: {why}")
    breaking = [c for c in changes if c[0] == "breaking"]
    if "--write" in args:
        if breaking and stored and version(current) <= version(stored):
            print(f"refused: {len(breaking)} breaking change(s) to the stable API "
                  f"and API_VERSION is still {version(current)} — bump it in "
                  "xefm/user_api.py (and say so in the release notes), or undo "
                  "the change", file=sys.stderr)
            return 1
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(render(current), encoding="utf-8")
        print(f"wrote {SNAPSHOT}")
        return 0
    return 1 if changes else 0


if __name__ == "__main__":
    sys.exit(main())
