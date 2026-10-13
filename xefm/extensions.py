"""Extension packages — a manifest, a static check, an installed set (#583).

A hand-written module in ``~/.xefm/extensions/`` has always been importable
from ``config.py``, and the config then wired what it imported into its own
tables by hand. A *package* is the next step on that path: a directory in the
same place holding ``xefm-extension.toml`` beside its code. The manifest
declares what the package contributes to those same tables — ``ACTIONS``,
``EVENT_HOOKS``, ``THEMES`` and the rest — and names the code by reference
(``"hello_xefm.actions:greet"``), so XeFM does the wiring instead.

Declared, not executed, is the point. :func:`check_package` validates a
manifest without running any of the package's code: references are resolved
by reading the referenced module's syntax tree for a top-level binding of the
name, key suggestions are parsed the way ``KEY_BINDINGS`` entries are, and every
problem comes back as one :class:`Problem` naming the manifest field it is
about. That is the check ``xefm ext check`` runs, the one an install runs before
copying anything, and the one a load runs before importing anything — so an
assistant writing a package gets the same precise error the user would.

Precedence: **``config.py`` wins everything.** Where a package's contribution
and the user's own config name the same thing — an action, a scheme, a filter,
a theme — the package's entry is skipped with a warning. A package's keys are
only *suggestions*: one is applied only when the action has no binding of its
own and every key in it is free.

Three places on disk, all under ``~/.xefm/``:

- ``extensions/<dir>/`` — the packages themselves, next to the hand-written
  modules. Treated as a cache: they can be rebuilt from the installed set.
- ``extensions.toml`` — the installed set: which packages came from where, at
  which version, and whether they are enabled. A package directory the set does
  not list is a *local* package (one the user made by adding a manifest to their
  own code) and is enabled.
- ``extension-data/<id>/`` — a package's own files, out of reach of a
  reinstall.

Code-bearing contributions run against :data:`xefm.user_api.API_VERSION`,
which is still ``0`` (Preview): a package declares the ``api_version`` it was
written for, and one asking for a newer version than this XeFM has is not
loaded, with the reason given.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

from xefm import __version__ as _XEFM_VERSION
from xefm.log_manager import getLogger

logger = getLogger("Extensions")

MANIFEST = "xefm-extension.toml"
INSTALLED_SET = "extensions.toml"

#: Where packages may say they run. ``desktop`` is the native GUI, ``tui`` the
#: terminal (``web`` serves the TUI's widget model, so it counts as ``tui``).
BACKENDS = ("desktop", "tui")
PLATFORMS = ("macos", "windows", "linux")

#: ``[contributes.<kind>]`` → the ``Config`` table it feeds. ``key_suggestions``
#: is handled apart: it feeds ``KEY_BINDINGS``, but only where nothing else does.
CONTRIBUTION_TABLES = {
    "actions": "ACTIONS",
    "event_hooks": "EVENT_HOOKS",
    "sort_keys": "SORT_KEYS",
    "filters": "FILTERS",
    "image_decoders": "IMAGE_DECODERS",
    "path_schemes": "PATH_SCHEMES",
    "lexers": "LEXERS",
    "themes": "THEMES",
}
#: Kinds whose entries may be plain data rather than a code reference — the
#: tier that runs no code at all.
_DATA_KINDS = {"themes", "filters", "lexers"}

_KNOWN_SECTIONS = {"extension", "contributes", "requires", "settings"}
_KNOWN_EXTENSION_KEYS = {"id", "version", "api_version", "min_xefm", "name",
                         "description", "backends", "platforms", "homepage"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_REF_RE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")


# --- problems -----------------------------------------------------------------

@dataclass(frozen=True)
class Problem:
    """One finding of :func:`check_package`. ``where`` is the manifest field it
    is about (``contributes.actions."hello.greet".entry``), so the fix is never
    a search."""
    severity: str          # "error" | "warning"
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity}: {MANIFEST}: {self.where}: {self.message}"


def _quote(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else f'"{key}"'


# --- the manifest -------------------------------------------------------------

@dataclass
class Manifest:
    """A parsed ``xefm-extension.toml``. Only :func:`read_manifest` builds one;
    every field is as declared, unchecked — :func:`check_manifest` judges."""
    root: Path
    data: dict

    @property
    def id(self) -> str:
        return str(self.data.get("extension", {}).get("id", ""))

    @property
    def version(self) -> str:
        return str(self.data.get("extension", {}).get("version", ""))

    @property
    def name(self) -> str:
        ext = self.data.get("extension", {})
        return str(ext.get("name") or ext.get("id") or self.root.name)

    @property
    def api_version(self) -> Any:
        return self.data.get("extension", {}).get("api_version")

    @property
    def contributes(self) -> dict:
        value = self.data.get("contributes", {})
        return value if isinstance(value, dict) else {}

    @property
    def requires(self) -> dict:
        value = self.data.get("requires", {})
        return value if isinstance(value, dict) else {}

    def references(self) -> list[tuple[str, str]]:
        """Every ``module:name`` reference, as ``(where, reference)``."""
        out = []
        for kind, table in self.contributes.items():
            if kind == "key_suggestions" or not isinstance(table, dict):
                continue
            for key, value in table.items():
                where = f"contributes.{kind}.{_quote(key)}"
                for sub, ref in _refs_in(value):
                    out.append((where + sub, ref))
        settings = self.data.get("settings")
        if isinstance(settings, dict) and isinstance(settings.get("defaults"), str):
            out.append(("settings.defaults", settings["defaults"]))
        return out

    @property
    def runs_code(self) -> bool:
        """Whether anything here is a code reference — false for the data-only
        tier (themes, glob filters, lexer aliases, key suggestions)."""
        return bool(self.references())


def _refs_in(value) -> list[tuple[str, str]]:
    """The code references inside one contribution value: the value itself
    when it is a reference string, its ``entry`` when it is a table, each item
    when it is a list (an event's hooks)."""
    if isinstance(value, str):
        return [("", value)] if ":" in value else []
    if isinstance(value, dict):
        entry = value.get("entry")
        return [(".entry", entry)] if isinstance(entry, str) else []
    if isinstance(value, list):
        out = []
        for i, item in enumerate(value):
            out += [(f"[{i}]" + sub, ref) for sub, ref in _refs_in(item)]
        return out
    return []


class ManifestError(Exception):
    """No manifest, or one that is not TOML; carries the :class:`Problem`."""

    def __init__(self, problem: Problem):
        super().__init__(str(problem))
        self.problem = problem


def read_manifest(root: Path) -> Manifest:
    root = Path(root)
    path = root / MANIFEST
    if tomllib is None:
        raise ManifestError(Problem("error", "(file)",
                                    "reading a manifest needs Python 3.11 or later"))
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ManifestError(Problem("error", "(file)", f"no {MANIFEST} in {root}")) from None
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(Problem("error", "(file)", f"not valid TOML: {exc}")) from None
    return Manifest(root, data)


# --- the static check ---------------------------------------------------------

def _version_tuple(text: str) -> tuple[int, ...]:
    parts = []
    for piece in str(text).split("."):
        digits = re.match(r"\d+", piece)
        if not digits:
            break
        parts.append(int(digits.group()))
    return tuple(parts)


def _api_version() -> int:
    from xefm.user_api import API_VERSION
    return API_VERSION


def _module_file(root: Path, module: str) -> Optional[Path]:
    base = root.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _top_level_names(tree: ast.Module) -> set[str]:
    """Names a module binds at top level, read off its syntax tree."""
    names: set[str] = set()

    def targets(node):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                targets(elt)

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    targets(target)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                targets(node.target)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(node, (ast.If, ast.Try)):
                visit(node.body)
                visit(getattr(node, "orelse", []))
                for handler in getattr(node, "handlers", []):
                    visit(handler.body)
                visit(getattr(node, "finalbody", []))
    visit(tree.body)
    return names


def _check_reference(root: Path, ref: str) -> Optional[str]:
    """Why ``module:name`` does not resolve inside ``root``, or None — read
    from the module's source, never by importing it."""
    if not _REF_RE.match(ref):
        return f"{ref!r} is not a reference — write it as 'package.module:name'"
    module, name = ref.split(":")
    path = _module_file(root, module)
    if path is None:
        return (f"module {module} is not in the package — expected "
                f"{module.replace('.', '/')}.py or {module.replace('.', '/')}/__init__.py")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return f"{path.relative_to(root)}:{exc.lineno}: syntax error: {exc.msg}"
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot read {path.relative_to(root)}: {exc}"
    if name not in _top_level_names(tree):
        return f"module {module} has no top-level '{name}'"
    return None


def _check_key(expr) -> Optional[str]:
    from xefm.config import _MODIFIER_ALIASES, _NAMED_KEYS, _PUNCT_NAMES
    if not isinstance(expr, str) or not expr:
        return f"{expr!r} is not a key"
    if len(expr) == 1:
        return None
    parts = expr.split("-")
    if parts[-1] == "" and len(parts) > 1:  # "Ctrl--": the key is a minus
        parts = parts[:-2] + ["-"]
    for mod in parts[:-1]:
        if mod.upper() not in _MODIFIER_ALIASES:
            return f"{expr!r}: unknown modifier '{mod}'"
    key = parts[-1]
    if len(key) == 1 or key.upper() in _NAMED_KEYS or key.upper() in _PUNCT_NAMES:
        return None
    return f"{expr!r}: unknown key '{key}'"


def python_top_level(root: Path) -> set[str]:
    """The importable top-level names a package directory provides."""
    names = set()
    try:
        children = list(Path(root).iterdir())
    except OSError:
        return names
    for child in children:
        if child.name.startswith((".", "_")) and child.name != "__init__.py":
            continue
        if child.is_dir() and (child / "__init__.py").is_file():
            names.add(child.name)
        elif child.suffix == ".py" and child.is_file():
            names.add(child.stem)
    return names


def check_manifest(manifest: Manifest, *, others: Iterable[Manifest] = (),
                   machine: bool = True) -> list[Problem]:
    """Every problem with ``manifest``, without executing anything.

    ``others`` are the other packages installed beside it, for the checks that
    are about coexisting: the same id, and the same top-level module name —
    ``sys.modules`` is one per process, so two packages providing ``foo`` would
    otherwise collide silently, in load order. With ``machine`` the
    machine-dependent requirements (programs, host packages) are checked too,
    as warnings: a package is not wrong for needing ``ffmpeg``."""
    problems: list[Problem] = []
    err = lambda where, msg: problems.append(Problem("error", where, msg))  # noqa: E731
    warn = lambda where, msg: problems.append(Problem("warning", where, msg))  # noqa: E731
    data = manifest.data

    for section in data:
        if section not in _KNOWN_SECTIONS:
            err(section, f"unknown section — known: {', '.join(sorted(_KNOWN_SECTIONS))}")

    ext = data.get("extension")
    if not isinstance(ext, dict):
        err("extension", "missing — every manifest starts with an [extension] table")
        ext = {}
    for key in ext:
        if key not in _KNOWN_EXTENSION_KEYS:
            err(f"extension.{key}", "unknown key — known: "
                f"{', '.join(sorted(_KNOWN_EXTENSION_KEYS))}")
    ext_id = ext.get("id")
    if not isinstance(ext_id, str) or not _ID_RE.match(ext_id):
        err("extension.id", "required: lowercase letters, digits, '.', '_' or "
            "'-', starting with a letter or digit (e.g. 'hello-xefm')")
    version = ext.get("version")
    if not isinstance(version, str) or not _version_tuple(version):
        err("extension.version", "required: a version string such as '0.1.0'")
    api = ext.get("api_version")
    current = _api_version()
    if not isinstance(api, int) or isinstance(api, bool):
        err("extension.api_version", f"required: an integer — this XeFM's API "
            f"version is {current}")
    elif api > current:
        err("extension.api_version", f"asks for API version {api}; this XeFM "
            f"has {current}")
    elif api < current:
        warn("extension.api_version", f"written for API version {api}; this "
             f"XeFM has {current}")
    min_xefm = ext.get("min_xefm")
    if min_xefm is not None:
        if not isinstance(min_xefm, str) or not _version_tuple(min_xefm):
            err("extension.min_xefm", "must be a version string such as '1.8.0'")
        elif _version_tuple(min_xefm) > _version_tuple(_XEFM_VERSION):
            err("extension.min_xefm", f"needs XeFM {min_xefm}; this is {_XEFM_VERSION}")
    for key, allowed in (("backends", BACKENDS), ("platforms", PLATFORMS)):
        value = ext.get(key)
        if value is None:
            continue
        if not isinstance(value, list) or not value:
            err(f"extension.{key}", f"must be a non-empty list of {', '.join(allowed)}")
            continue
        for item in value:
            if item not in allowed:
                err(f"extension.{key}", f"{item!r} is not one of {', '.join(allowed)}")

    contributes = data.get("contributes", {})
    if not isinstance(contributes, dict):
        err("contributes", "must be a table")
        contributes = {}
    actions = contributes.get("actions", {})
    action_names = set(actions) if isinstance(actions, dict) else set()
    for kind, table in contributes.items():
        if kind != "key_suggestions" and kind not in CONTRIBUTION_TABLES:
            err(f"contributes.{kind}", "unknown contribution — known: "
                f"{', '.join(sorted(list(CONTRIBUTION_TABLES) + ['key_suggestions']))}")
            continue
        if not isinstance(table, dict):
            err(f"contributes.{kind}", "must be a table")
            continue
        for key, value in table.items():
            where = f"contributes.{kind}.{_quote(key)}"
            problem = _check_contribution(kind, key, value, action_names)
            if problem:
                err(where, problem)
    if action_names:
        from xefm import actions as _actions
        for name in sorted(action_names):
            where = f"contributes.actions.{_quote(name)}"
            builtin = _actions.registry.builtin(_actions.FILER, name)
            if builtin is not None:
                err(where, f"'{name}' is a built-in action — prefix it with the "
                    f"extension's own name, e.g. '{ext_id or 'myext'}.{name}'")
            elif "." not in name:
                warn(where, f"name it '<extension>.{name}' so it cannot collide "
                     "with another extension's or a future built-in action")

    for where, ref in manifest.references():
        problem = _check_reference(manifest.root, ref)
        if problem:
            err(where, problem)

    settings = data.get("settings")
    if settings is not None:
        if not isinstance(settings, dict):
            err("settings", "must be a table")
        else:
            for key in set(settings) - {"defaults", "config_class"}:
                err(f"settings.{key}", "unknown key — known: config_class, defaults")
            if not isinstance(settings.get("defaults"), str):
                err("settings.defaults", "required: the class holding the "
                    "defaults, as 'package.module:Settings'")
            name = settings.get("config_class")
            if name is not None and (not isinstance(name, str)
                                     or not name.isidentifier() or name == "Config"):
                err("settings.config_class", "must be a class name (not 'Config')")

    requires = data.get("requires", {})
    if not isinstance(requires, dict):
        err("requires", "must be a table")
        requires = {}
    for key in requires:
        if key not in ("programs", "host_packages"):
            err(f"requires.{key}", "unknown key — known: host_packages, programs")
    for key in ("programs", "host_packages"):
        value = requires.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            err(f"requires.{key}", "must be a list of strings")
    if machine:
        for program in requires.get("programs", []) or []:
            if isinstance(program, str) and shutil.which(program) is None:
                warn("requires.programs", f"'{program}' is not on PATH here — "
                     "the actions that need it will say so when run")
        for package in requires.get("host_packages", []) or []:
            if isinstance(package, str) and not _importable(package):
                warn("requires.host_packages", f"'{package}' is not importable "
                     "in this XeFM — the extension will not load here")

    own = python_top_level(manifest.root)
    if manifest.runs_code and not own:
        err("(layout)", "the manifest references code, but the package has no "
            "Python package or module beside it")
    reserved = set(sys.stdlib_module_names) | {"xefm", "puikit"}
    for name in sorted(own & reserved):
        err("(layout)", f"top-level module '{name}' would shadow "
            f"{'the standard library' if name in sys.stdlib_module_names else name}"
            " — rename it")
    for other in others:
        if other.root == manifest.root:
            continue
        if ext_id and other.id == ext_id:
            err("extension.id", f"'{ext_id}' is already used by {other.root}")
        if settings is not None and other.data.get("settings") is not None \
                and ext_id and config_class_name(manifest) == config_class_name(other):
            err("settings.config_class", f"both this and '{other.id}' read their "
                f"settings from class {config_class_name(manifest)} — name one "
                "explicitly with settings.config_class")
        for name in sorted(own & python_top_level(other.root)):
            err("(layout)", f"top-level module '{name}' is also provided by "
                f"'{other.id or other.root.name}' — one process has one "
                f"'{name}'; rename it (e.g. vendor it under your own package)")
    return problems


def _check_contribution(kind: str, key: str, value, action_names: set) -> Optional[str]:
    if not isinstance(key, str) or not key:
        return "names must be non-empty strings"
    if kind == "key_suggestions":
        if key not in action_names:
            return (f"suggests keys for '{key}', which this extension does not "
                    "contribute in [contributes.actions]")
        if not isinstance(value, list) or not value:
            return "must be a non-empty list of keys, e.g. [\"Ctrl-G\"]"
        for expr in value:
            problem = _check_key(expr)
            if problem:
                return problem
        return None
    if kind == "actions":
        if isinstance(value, str):
            return None if ":" in value else "must be 'module:function'"
        if isinstance(value, dict):
            extra = set(value) - {"entry", "description"}
            if "entry" not in value:
                return "needs entry = 'module:function'"
            if extra:
                return f"unknown keys {', '.join(sorted(extra))} — known: description, entry"
            return None
        return "must be 'module:function' or { entry = ..., description = ... }"
    if kind == "event_hooks":
        from xefm.user_api import EVENTS
        if key not in EVENTS:
            return f"'{key}' is not an event — known: {', '.join(sorted(EVENTS))}"
        items = value if isinstance(value, list) else [value]
        if not items or not all(isinstance(v, str) and ":" in v for v in items):
            return "must be 'module:function' or a list of them"
        return None
    if isinstance(value, str) and ":" in value:
        return None
    if isinstance(value, dict) and "entry" in value:
        if set(value) != {"entry"}:
            return "a table with 'entry' holds nothing else"
        return None
    if kind in _DATA_KINDS:
        if kind == "lexers" and not isinstance(value, str):
            return "must be a Pygments lexer alias or { entry = 'module:LexerClass' }"
        if kind in ("themes", "filters") and not isinstance(value, dict):
            return "must be a table (or 'module:name')"
        return None
    return "must be 'module:name'"


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def check_package(root: Path, *, others: Iterable[Manifest] = (),
                  machine: bool = True) -> tuple[Optional[Manifest], list[Problem]]:
    """Read and check the package at ``root``: ``(manifest, problems)``, the
    manifest None when it could not be read at all."""
    try:
        manifest = read_manifest(root)
    except ManifestError as exc:
        return None, [exc.problem]
    return manifest, check_manifest(manifest, others=others, machine=machine)


def errors(problems: Iterable[Problem]) -> list[Problem]:
    return [p for p in problems if p.severity == "error"]


# --- where things live --------------------------------------------------------

def default_home() -> Path:
    return Path.home() / ".xefm"


@dataclass
class Layout:
    """The three places under ``~/.xefm`` (or a test's stand-in for it)."""
    home: Path = field(default_factory=default_home)

    @property
    def packages(self) -> Path:
        return self.home / "extensions"

    @property
    def installed_file(self) -> Path:
        return self.home / INSTALLED_SET

    def data_dir(self, ext_id: str) -> Path:
        return self.home / "extension-data" / ext_id


def discover(layout: Layout) -> list[Manifest]:
    """Every readable package in ``extensions/``, in directory-name order.
    Unreadable manifests are skipped here; :func:`load` reports them."""
    out = []
    try:
        children = sorted(layout.packages.iterdir())
    except OSError:
        return out
    for child in children:
        if child.is_dir() and (child / MANIFEST).is_file():
            try:
                out.append(read_manifest(child))
            except ManifestError:
                continue
    return out


# --- the installed set ----------------------------------------------------------

@dataclass
class InstalledEntry:
    id: str
    version: str = ""
    source: str = ""
    directory: str = ""
    enabled: bool = True


def read_installed(layout: Layout) -> dict[str, InstalledEntry]:
    path = layout.installed_file
    if tomllib is None or not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning(f"Could not read {path}: {exc}")
        return {}
    out = {}
    for ext_id, entry in (data.get("extensions") or {}).items():
        if not isinstance(entry, dict):
            continue
        out[ext_id] = InstalledEntry(
            id=ext_id, version=str(entry.get("version", "")),
            source=str(entry.get("source", "")),
            directory=str(entry.get("directory", ext_id)),
            enabled=bool(entry.get("enabled", True)))
    return out


def _toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = "".join(c if c >= " " else f"\\u{ord(c):04x}" for c in escaped)
    return f'"{escaped}"'


def write_installed(layout: Layout, entries: dict[str, InstalledEntry]) -> None:
    lines = ["# The installed extensions — written by XeFM (`xefm ext ...`).",
             "# The package directories are rebuilt from this list by",
             "# `xefm ext sync`, so it is the part worth keeping.", ""]
    for ext_id in sorted(entries):
        e = entries[ext_id]
        lines += [f"[extensions.{_toml_str(ext_id)}]",
                  f"version = {_toml_str(e.version)}",
                  f"source = {_toml_str(e.source)}",
                  f"directory = {_toml_str(e.directory)}",
                  f"enabled = {'true' if e.enabled else 'false'}", ""]
    layout.home.mkdir(parents=True, exist_ok=True)
    tmp = layout.installed_file.with_suffix(".toml.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, layout.installed_file)


# --- install / uninstall ----------------------------------------------------------

class InstallError(Exception):
    """An install refused; ``problems`` holds the check's findings, if any."""

    def __init__(self, message: str, problems: Iterable[Problem] = ()):
        super().__init__(message)
        self.problems = list(problems)


def _github_zip_url(source: str) -> Optional[str]:
    """``github:owner/repo[@ref]`` or a github.com repository URL → its zip."""
    m = re.fullmatch(r"github:([\w.-]+)/([\w.-]+?)(?:@([\w./-]+))?", source)
    if not m:
        m = re.fullmatch(r"https://github\.com/([\w.-]+)/([\w.-]+?)(?:\.git)?/?"
                         r"(?:tree/([\w./-]+))?", source)
    if not m:
        return None
    owner, repo, ref = m.group(1), m.group(2), m.group(3) or "HEAD"
    return f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for info in archive.infolist():
        target = (dest / info.filename).resolve()
        if dest != target and dest not in target.parents:
            raise InstallError(f"the archive holds a path outside itself: {info.filename}")
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def _find_package_root(top: Path) -> Path:
    """The directory holding the manifest: ``top`` itself, or its only child
    directory (a GitHub zip wraps everything in ``repo-ref/``)."""
    if (top / MANIFEST).is_file():
        return top
    children = [c for c in top.iterdir() if not c.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir() and (children[0] / MANIFEST).is_file():
        return children[0]
    raise InstallError(f"no {MANIFEST} at the top of the package")


def fetch(source: str, workdir: Path,
          opener: Callable[[str], bytes] | None = None) -> Path:
    """Put the package named by ``source`` — a directory, a ``.zip``, an
    ``https://`` URL of a zip, or ``github:owner/repo[@ref]`` — under
    ``workdir`` and return the directory holding its manifest."""
    path = Path(source).expanduser()
    if path.is_dir():
        return _find_package_root(path)
    if path.is_file():
        try:
            with zipfile.ZipFile(path) as archive:
                _safe_extract(archive, workdir)
        except zipfile.BadZipFile:
            raise InstallError(f"{source} is not a zip file") from None
        return _find_package_root(workdir)
    url = _github_zip_url(source) or (source if source.startswith("https://") else None)
    if url is None:
        raise InstallError(f"{source} is not a directory, a zip, an https:// URL "
                           "or github:owner/repo")
    if opener is None:
        def opener(u: str) -> bytes:
            with urllib.request.urlopen(u, timeout=60) as response:
                return response.read()
    try:
        payload = opener(url)
    except OSError as exc:
        raise InstallError(f"could not download {url}: {exc}") from None
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            _safe_extract(archive, workdir)
    except zipfile.BadZipFile:
        raise InstallError(f"{url} did not return a zip file") from None
    return _find_package_root(workdir)


def summarize(manifest: Manifest) -> list[str]:
    """What a package would add, one line per contribution — shown before an
    install, since extensions run in-process with no sandbox."""
    lines = []
    for kind, table in manifest.contributes.items():
        if not isinstance(table, dict):
            continue
        for key, value in table.items():
            if kind == "key_suggestions":
                lines.append(f"key suggestion: {key} → {', '.join(map(str, value))}")
            else:
                refs = [ref for _, ref in _refs_in(value)]
                code = f"  (runs {', '.join(refs)})" if refs else ""
                lines.append(f"{kind[:-1] if kind.endswith('s') else kind}: {key}{code}")
    for key in ("programs", "host_packages"):
        for item in manifest.requires.get(key, []) or []:
            lines.append(f"requires {key[:-1].replace('_', ' ')}: {item}")
    return lines


def install(source: str, layout: Layout | None = None, *,
            opener: Callable[[str], bytes] | None = None) -> Manifest:
    """Check the package at ``source`` and copy it into ``extensions/``,
    recording it in the installed set. Nothing is copied when the check finds
    an error. Reinstalling an installed id replaces it (an upgrade); a *local*
    package of the same id — one the user made — is never overwritten."""
    layout = layout or Layout()
    installed = read_installed(layout)
    with tempfile.TemporaryDirectory(prefix="xefm-ext-") as tmp:
        root = fetch(source, Path(tmp), opener=opener)
        manifest = read_manifest(root)
        others = [m for m in discover(layout) if m.id != manifest.id]
        problems = check_manifest(manifest, others=others)
        if errors(problems):
            raise InstallError(f"{manifest.id or source} did not pass the check",
                               problems)
        target = layout.packages / manifest.id
        if target.exists() and manifest.id not in installed:
            raise InstallError(f"{target} already exists and was not installed "
                               "by XeFM — move it away first")
        layout.packages.mkdir(parents=True, exist_ok=True)
        staging = layout.packages / f".{manifest.id}.installing"
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(root, staging, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".git"))
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
    previous = installed.get(manifest.id)
    source_text = source if not Path(source).expanduser().exists() \
        else str(Path(source).expanduser().resolve())
    installed[manifest.id] = InstalledEntry(
        id=manifest.id, version=manifest.version, source=source_text,
        directory=manifest.id, enabled=previous.enabled if previous else True)
    write_installed(layout, installed)
    logger.info(f"Installed extension {manifest.id} {manifest.version} from {source}")
    return read_manifest(target)


def uninstall(ext_id: str, layout: Layout | None = None, *,
              delete_data: bool = False) -> None:
    """Remove an installed package and its entry. Its ``extension-data/``
    directory goes only with ``delete_data``. A settings class left in
    ``config.py`` stays harmless: nothing refers to it any more."""
    layout = layout or Layout()
    installed = read_installed(layout)
    entry = installed.pop(ext_id, None)
    if entry is None:
        raise InstallError(f"{ext_id} is not installed"
                           + (" (it is a local package: delete its directory)"
                              if (layout.packages / ext_id).exists() else ""))
    shutil.rmtree(layout.packages / entry.directory, ignore_errors=True)
    write_installed(layout, installed)
    if delete_data:
        shutil.rmtree(layout.data_dir(ext_id), ignore_errors=True)
    logger.info(f"Uninstalled extension {ext_id}")


def set_enabled(ext_id: str, enabled: bool, layout: Layout | None = None) -> None:
    layout = layout or Layout()
    installed = read_installed(layout)
    if ext_id not in installed:
        if any(m.id == ext_id for m in discover(layout)):
            installed[ext_id] = InstalledEntry(id=ext_id, source="(local)",
                                               directory=_dir_of(layout, ext_id))
        else:
            raise InstallError(f"{ext_id} is not installed")
    installed[ext_id].enabled = enabled
    write_installed(layout, installed)


def _dir_of(layout: Layout, ext_id: str) -> str:
    for m in discover(layout):
        if m.id == ext_id:
            return m.root.name
    return ext_id


def sync(layout: Layout | None = None, *,
         opener: Callable[[str], bytes] | None = None) -> list[str]:
    """Reinstall every listed package whose directory is missing — after a
    Python upgrade, or on another machine with the same ``extensions.toml``.
    Returns one line per package acted on."""
    layout = layout or Layout()
    report = []
    for ext_id, entry in read_installed(layout).items():
        if (layout.packages / entry.directory).is_dir() or entry.source in ("", "(local)"):
            continue
        try:
            install(entry.source, layout, opener=opener)
            report.append(f"{ext_id}: reinstalled from {entry.source}")
        except (InstallError, ManifestError, OSError) as exc:
            report.append(f"{ext_id}: could not reinstall from {entry.source}: {exc}")
    return report


# --- settings -----------------------------------------------------------------
#
# An extension's hand-written settings are a plain class in config.py, written
# the way ``class Config:`` is — no base class, no import:
#
#     class CommandPaletteConfig:
#         MAX_ITEMS = 30
#
# XeFM finds it by name after config.py has run. The name is derived from the
# id (:func:`config_class_name`) unless the manifest names one, and the
# package's own defaults class fills in whatever the user's class leaves out —
# the same merge ``_copy_missing_fields`` does for ``Config``. Nothing in
# config.py refers to the package, so uninstalling it leaves an unused class
# behind and never a config that fails to load.

#: ext id → that extension's merged settings, rebuilt on every config load.
_settings: dict[str, Any] = {}


def config_class_name(manifest: Manifest) -> str:
    """The ``config.py`` class holding ``manifest``'s settings: the manifest's
    ``settings.config_class`` when it names one, else the id in PascalCase plus
    ``Config`` — ``command-palette`` → ``CommandPaletteConfig``."""
    settings = manifest.data.get("settings")
    if isinstance(settings, dict) and isinstance(settings.get("config_class"), str):
        return settings["config_class"]
    words = [w for w in re.split(r"[-._]+", manifest.id) if w]
    return "".join(w[:1].upper() + w[1:] for w in words) + "Config"


def _defaults_ref(manifest: Manifest) -> Optional[str]:
    settings = manifest.data.get("settings")
    if isinstance(settings, dict) and isinstance(settings.get("defaults"), str):
        return settings["defaults"]
    return None


def _import_ref(root: Path, ref: str):
    module, name = ref.split(":")
    entry = str(root.resolve())
    if entry not in sys.path:
        sys.path.append(entry)
    return getattr(importlib.import_module(module), name)


def _settings_names(cls) -> dict[str, Any]:
    """A settings class's settings: its upper-case attributes, inherited ones
    included, so a defaults class may itself be built by inheritance."""
    return {n: getattr(cls, n) for n in dir(cls) if n.isupper()}


def _merge_settings(manifest: Manifest, defaults: type, user: Optional[type],
                    warnings: list[str]) -> Any:
    """The extension's defaults overlaid with what the user's class sets. A
    name the extension does not have is skipped with a warning naming the
    ones it does — a typo must not pass silently."""
    merged = type(f"{config_class_name(manifest)}Settings", (), {})()
    known = _settings_names(defaults)
    for name, value in known.items():
        setattr(merged, name, value)
    if user is not None:
        for name, value in vars(user).items():
            if not name.isupper():
                continue
            if name not in known:
                warnings.append(
                    f"{user.__name__}.{name}: '{manifest.id}' has no setting "
                    f"'{name}' — ignored (known: {', '.join(sorted(known)) or 'none'})")
                continue
            setattr(merged, name, value)
    return merged


def _load_settings(manifests: list[Manifest], loaded: list[Manifest],
                   namespace: dict, warnings: list[str]) -> None:
    """Build every loaded extension's settings from ``config.py``'s
    ``namespace``, and warn about a ``…Config`` class nothing claims — the
    one way a misspelt class name would otherwise go unnoticed."""
    _settings.clear()
    for manifest in loaded:
        ref = _defaults_ref(manifest)
        if ref is None:
            continue
        user = namespace.get(config_class_name(manifest))
        if user is not None and not isinstance(user, type):
            warnings.append(f"{config_class_name(manifest)} in config.py is not "
                            f"a class — '{manifest.id}' keeps its defaults")
            user = None
        try:
            defaults = _import_ref(manifest.root, ref)
        except Exception as exc:
            warnings.append(f"{manifest.id}: could not import its settings "
                            f"defaults {ref}: {exc}")
            continue
        _settings[manifest.id] = _merge_settings(manifest, defaults, user, warnings)

    claimed = {config_class_name(m) for m in manifests}
    module = namespace.get("__name__")
    for name, value in namespace.items():
        if (isinstance(value, type) and name.endswith("Config") and name != "Config"
                and name not in claimed
                and getattr(value, "__module__", module) == module):
            warnings.append(f"config.py class {name} matches no installed "
                            "extension's settings — check the name with "
                            "`xefm ext list`")


def settings_for(ext_id: str) -> Any:
    """``ext_id``'s settings as of the last config load — its defaults overlaid
    with the user's class — or None when it declares no settings."""
    return _settings.get(ext_id)


def settings_template(manifest: Manifest) -> str:
    """A class definition to paste into ``config.py``: every setting with its
    default, commented out. Imports the package's defaults class."""
    ref = _defaults_ref(manifest)
    if ref is None:
        return f"# {manifest.id} has no settings"
    defaults = _import_ref(manifest.root, ref)
    lines = [f"class {config_class_name(manifest)}:",
             f"    # Settings of {manifest.id} {manifest.version}; uncomment to change."]
    names = _settings_names(defaults)
    for name, value in names.items():
        lines.append(f"    # {name} = {value!r}")
    if not names:
        lines.append("    pass")
    return "\n".join(lines)


# --- what an extension's code is handed ---------------------------------------

class ExtensionState:
    """An extension's runtime state: a key–value view of ``state.db`` under
    ``ext:<id>:``. Values are anything JSON can hold. No SQL, no schema."""

    def __init__(self, state_manager, ext_id: str):
        self._sm = state_manager
        self._prefix = f"ext:{ext_id}:"

    def get(self, key: str, default: Any = None) -> Any:
        return self._sm.get_state(self._prefix + key, default) if self._sm else default

    def set(self, key: str, value: Any) -> None:
        if self._sm:
            self._sm.set_state(self._prefix + key, value)

    def delete(self, key: str) -> None:
        if self._sm:
            self._sm.delete_state(self._prefix + key)

    def keys(self) -> list[str]:
        if not self._sm:
            return []
        return [k[len(self._prefix):] for k in self._sm.get_all_states(self._prefix)]


class ExtensionHandle:
    """``ctx.extension`` while an extension's action or hook runs."""

    def __init__(self, manifest: Manifest, layout: Layout, state_manager=None):
        self.id = manifest.id
        self.version = manifest.version
        self._layout = layout
        self._sm = state_manager

    @property
    def settings(self) -> Any:
        return settings_for(self.id)

    @property
    def state(self) -> ExtensionState:
        return ExtensionState(self._sm, self.id)

    @property
    def data_dir(self) -> Path:
        path = self._layout.data_dir(self.id)
        path.mkdir(parents=True, exist_ok=True)
        return path


#: The state manager handles are given; the app sets it once it has one.
state_manager_for_handles = None


def _in_extension(handle: ExtensionHandle, func: Callable, *,
                  missing: list[str] = ()) -> Callable:
    """``func`` run with ``ctx.extension`` set to ``handle``; refused, with
    the install hint, while a program it requires is missing."""
    import functools

    @functools.wraps(func)
    def run(ctx, *args):
        absent = [p for p in missing if shutil.which(p) is None]
        if absent:
            logger.warning(f"{handle.id}: needs {', '.join(absent)} on PATH — "
                           "install it to use this")
            return None
        handle._sm = handle._sm or state_manager_for_handles
        previous = getattr(ctx, "_extension", None)
        ctx._extension = handle
        try:
            return func(ctx, *args)
        finally:
            ctx._extension = previous
    return run


# --- loading into a config ------------------------------------------------------

@dataclass
class LoadReport:
    loaded: list[Manifest] = field(default_factory=list)
    #: ``(id or directory, reason)`` for each package not loaded.
    skipped: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _current_backend() -> str:
    from xefm.backend_detector import is_desktop_mode
    return "desktop" if is_desktop_mode() else "tui"


def _current_platform() -> str:
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def _bound_keys(config) -> set:
    """Every key the config and the built-in defaults already use in the file
    list, parsed, so a suggestion can be tested for being free."""
    from xefm import actions as _actions
    from xefm.config import KeyBindings
    parser = KeyBindings({})
    bindings = getattr(config, "KEY_BINDINGS", None) or {}
    used = set()
    for name, binding in bindings.items():
        keys, _ = KeyBindings._binding_parts(binding)
        for key in keys:
            used.add(parser._parse_key_expression(key))
    for action in _actions.registry.actions(_actions.FILER):
        if action.name in bindings:
            continue
        for key in action.resolved_default_keys():
            used.add(parser._parse_key_expression(key))
    return used


def _value_for(kind: str, value, manifest: Manifest, handle: ExtensionHandle,
               missing: list[str]):
    """The ``Config`` table value a manifest entry stands for, importing what
    it references."""
    root = manifest.root
    if kind == "actions":
        if isinstance(value, str):
            value = {"entry": value}
        func = _in_extension(handle, _import_ref(root, value["entry"]), missing=missing)
        spec = {"func": func}
        if "description" in value:
            spec["description"] = value["description"]
        return spec
    if kind == "event_hooks":
        items = value if isinstance(value, list) else [value]
        return [_in_extension(handle, _import_ref(root, ref), missing=missing)
                for ref in items]
    if isinstance(value, dict) and "entry" in value:
        return _import_ref(root, value["entry"])
    if isinstance(value, str) and ":" in value and kind != "lexers":
        return _import_ref(root, value)
    if kind == "lexers" and isinstance(value, str) and _REF_RE.match(value):
        return _import_ref(root, value)
    return value


def load(config, layout: Layout | None = None, *,
         namespace: Optional[dict] = None) -> LoadReport:
    """Fold every enabled, passing package into ``config``'s tables, under the
    rule that ``config.py`` wins. Called by the config loader after
    ``config.py`` has run and the template has filled what it left out;
    ``namespace`` is that module's globals, where settings classes are found."""
    layout = layout or Layout()
    report = LoadReport()
    installed = read_installed(layout)
    manifests = []
    try:
        children = sorted(layout.packages.iterdir())
    except OSError:
        children = []
    for child in children:
        if not child.is_dir() or not (child / MANIFEST).is_file() \
                or child.name.startswith("."):
            continue
        try:
            manifests.append(read_manifest(child))
        except ManifestError as exc:
            report.skipped.append((child.name, str(exc.problem)))

    backend, platform = _current_backend(), _current_platform()
    for manifest in manifests:
        label = manifest.id or manifest.root.name
        entry = installed.get(manifest.id)
        if entry is not None and not entry.enabled:
            report.skipped.append((label, "disabled"))
            continue
        problems = check_manifest(manifest, others=manifests, machine=False)
        bad = errors(problems)
        if bad:
            report.skipped.append((label, str(bad[0]) + (
                f" (and {len(bad) - 1} more — run `xefm ext check {manifest.root}`)"
                if len(bad) > 1 else "")))
            continue
        ext = manifest.data.get("extension", {})
        if backend not in ext.get("backends", BACKENDS):
            report.skipped.append((label, f"not made for the {backend} backend"))
            continue
        if platform not in ext.get("platforms", PLATFORMS):
            report.skipped.append((label, f"not made for {platform}"))
            continue
        absent_hosts = [p for p in manifest.requires.get("host_packages", [])
                        if not _importable(p)]
        if absent_hosts:
            report.skipped.append((label, "this XeFM build has no "
                                   + ", ".join(absent_hosts)))
            continue
        try:
            _apply(config, manifest, layout, report)
        except Exception as exc:
            report.skipped.append((label, f"failed to load: {exc}"))
            logger.error(f"Extension {label} failed to load: {exc}")
            continue
        report.loaded.append(manifest)
    _load_settings(manifests, report.loaded, namespace or {}, report.warnings)
    return report


def _apply(config, manifest: Manifest, layout: Layout, report: LoadReport) -> None:
    """Fold one package in. Everything is resolved first and the config is
    touched only after, so a reference that fails to import leaves no half of
    the package behind."""
    handle = ExtensionHandle(manifest, layout, state_manager_for_handles)
    missing = list(manifest.requires.get("programs", []) or [])
    staged: dict[str, dict] = {}
    for kind, table in manifest.contributes.items():
        if kind == "key_suggestions":
            continue
        for key, value in table.items():
            staged.setdefault(CONTRIBUTION_TABLES[kind], {})[key] = \
                _value_for(kind, value, manifest, handle, missing)

    for attr, entries in staged.items():
        current = dict(getattr(config, attr, None) or {})
        for key, value in entries.items():
            if key in current:
                report.warnings.append(
                    f"{manifest.id}: {attr}['{key}'] is also in config.py — "
                    "config.py wins, the extension's entry is skipped")
                continue
            current[key] = value
        setattr(config, attr, current)

    suggestions = manifest.contributes.get("key_suggestions", {}) or {}
    if suggestions:
        from xefm.config import KeyBindings
        bindings = dict(getattr(config, "KEY_BINDINGS", None) or {})
        used = _bound_keys(config)
        parser = KeyBindings({})
        for action, keys in suggestions.items():
            if action in bindings:
                continue  # the user bound (or unbound) it: theirs
            parsed = [parser._parse_key_expression(k) for k in keys]
            taken = [k for k, p in zip(keys, parsed) if p in used]
            if taken:
                report.warnings.append(
                    f"{manifest.id}: suggested key {', '.join(taken)} for "
                    f"'{action}' is already in use — bind it in KEY_BINDINGS "
                    "to use it")
                continue
            bindings[action] = list(keys)
            used.update(parsed)
        config.KEY_BINDINGS = bindings
