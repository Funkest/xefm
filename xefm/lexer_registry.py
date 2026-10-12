"""Which Pygments lexer colors which file (``LEXERS`` in the config).

Pygments already reads most languages, and it has its own extension point: a
package that declares a ``pygments.lexers`` entry point gets its lexer found by
``get_lexer_for_filename`` like a built-in one. That route stays open — a lexer
installed that way works in XeFM with nothing here — but it is closed to most
people who would want it. It sees only *installed distributions*, so a lexer
written in ``config.py`` cannot use it, and a packaged XeFM (the macOS DMG, the
Windows zip, the MSIX) has nowhere to ``pip install`` one into.

So the config names lexers itself, and the shape is chosen so that nothing about
it is XeFM's own invention:

```python
from autocad_lexers import DclLexer       # a plain Pygments RegexLexer

class Config:
    LEXERS = {
        '*.dcl': DclLexer,      # a lexer class
        '*.mnl': 'newlisp',     # or the alias of one Pygments already has
    }
```

* **The lexer is a Pygments lexer**, written the way Pygments documents ("Write
  your own lexer") — nothing to import from XeFM, nothing to learn that a
  Pygments tutorial would not teach.
* **Which files it colors is the key, and only the key.** A Pygments class also
  carries ``filenames``, but XeFM does not read it: a mapping split between the
  config and a class attribute in another file is one nobody can read off
  ``config.py``. Each entry becomes a one-line subclass whose ``filenames`` is
  that key, so a lookup is still Pygments' own idea — match a class's
  ``filenames`` against the name — run over a table the config wrote down.
* **A string value is an alias**, resolved the way ``get_lexer_by_name`` would,
  except that the aliases of the classes this table registers come first — so
  ``'*.dclx': 'dcl'`` reuses the ``DclLexer`` above.

Lookup order, in :func:`lexer_for_filename`: the config's table, then Pygments'
own (built-ins and installed plugins), then :data:`BUILTIN` — the suffixes
Pygments does not claim but XeFM has always colored — and finally plain text.
The config coming first is what lets ``*.dcl`` mean AutoCAD DCL although
Pygments maps it to Clean.

Patterns match case-insensitively — ``FOO.DCL`` is a ``*.dcl`` on Windows, and
should be one everywhere.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any

from xefm.log_manager import getLogger

logger = getLogger("Lexer")

try:
    from pygments.lexer import Lexer
    from pygments.lexers import (find_lexer_class_by_name,
                                 get_lexer_for_filename, TextLexer)
    from pygments.util import ClassNotFound
    PYGMENTS = True
except ImportError:
    PYGMENTS = False

#: Suffixes XeFM colors when Pygments' own lookup finds nothing for the name —
#: the floor under the config's table, never above it.
BUILTIN = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".json": "json",
    ".md": "markdown", ".yml": "yaml", ".yaml": "yaml", ".xml": "xml",
    ".html": "html", ".css": "css", ".sh": "bash", ".bash": "bash", ".c": "c",
    ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".java": "java", ".go": "go",
    ".rs": "rust", ".php": "php", ".rb": "ruby", ".sql": "sql", ".ini": "ini",
    ".cfg": "ini", ".conf": "ini", ".toml": "toml",
}

#: The config's entries, in registration order: one lexer subclass each, whose
#: ``filenames`` is the single pattern it was registered under.
_user: list[type] = []


def clear() -> None:
    """Drop every registration. A config reload rebuilds from scratch."""
    _user.clear()


def normalize_pattern(pattern: str) -> str:
    """``'*.mnl'`` from ``'.mnl'``, the suffix spelling the other config tables
    use; any other pattern — ``'*.dcl'``, ``'Jenkinsfile'`` — as written."""
    pattern = pattern.strip()
    return "*" + pattern if pattern.startswith(".") else pattern


def resolve(lexer: Any) -> type:
    """The lexer class a ``LEXERS`` value names: a Lexer subclass as is, or an
    alias — the aliases of classes already registered first, then Pygments'.

    Raises ``ValueError`` saying what is wrong, for the loader to report."""
    if not PYGMENTS:
        raise ValueError("Pygments is not installed")
    if isinstance(lexer, type):
        if not issubclass(lexer, Lexer):
            raise ValueError(f"{lexer.__name__} is not a Pygments lexer class")
        return lexer
    if isinstance(lexer, str) and lexer.strip():
        alias = lexer.strip().lower()
        cls = _user_class_by_alias(alias)
        if cls is not None:
            return cls.__mro__[1]
        try:
            return find_lexer_class_by_name(alias)
        except ClassNotFound:
            raise ValueError(f"no lexer has the alias '{alias}' "
                             f"(pygmentize -L lexers lists them)") from None
    raise ValueError(f"must be a Pygments lexer class or an alias name, "
                     f"not {type(lexer).__name__}")


def register(pattern: str, lexer: Any) -> None:
    """Color files matching ``pattern`` with ``lexer`` (a class or an alias).

    The class registered is a subclass of the resolved one carrying only this
    pattern, so the same lexer under two patterns is two entries and neither
    reaches into the other's ``filenames``. Later registration wins."""
    base = resolve(lexer)
    pattern = normalize_pattern(pattern)
    cls = type(base.__name__, (base,), {
        "filenames": [pattern],
        "__module__": base.__module__,
        "__qualname__": base.__qualname__,
    })
    _user.append(cls)


def registered() -> list[tuple[str, type]]:
    """``(pattern, lexer class)`` for every registration, oldest first."""
    return [(cls.filenames[0], cls.__mro__[1]) for cls in _user]


def lexer_for_filename(name: str, **options) -> Any:
    """A lexer instance for a file called ``name`` — never ``None`` while
    Pygments is installed, since plain text is the last answer — or ``None``
    without Pygments."""
    if not PYGMENTS:
        return None
    cls = _user_class_for_filename(name)
    if cls is not None:
        return cls(**options)
    try:
        return get_lexer_for_filename(name, **options)
    except ClassNotFound:
        pass
    dot = name.rfind(".")
    alias = BUILTIN.get(name[dot:].lower()) if dot > 0 else None
    if alias:
        try:
            return find_lexer_class_by_name(alias)(**options)
        except ClassNotFound:
            pass
    return TextLexer(**options)


def lexer_by_name(alias: str, **options) -> Any:
    """A lexer instance for ``alias`` — a registered class's aliases first, then
    Pygments' — or ``None`` when nothing has that alias or Pygments is absent."""
    try:
        return resolve(alias)(**options)
    except ValueError:
        return None


def _user_class_for_filename(name: str) -> type | None:
    """The newest registration whose pattern matches ``name``, preferring an
    exact name (``Jenkinsfile``) over a wildcard — the same bonus Pygments gives
    an explicit pattern in its own lookup."""
    folded = name.lower()
    best = None
    for cls in reversed(_user):
        pattern = cls.filenames[0]
        if fnmatchcase(folded, pattern.lower()):
            if not any(c in pattern for c in "*?["):
                return cls
            if best is None:
                best = cls
    return best


def _user_class_by_alias(alias: str) -> type | None:
    for cls in reversed(_user):
        if alias in (a.lower() for a in getattr(cls, "aliases", ())):
            return cls
    return None
