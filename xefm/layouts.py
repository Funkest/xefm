"""File list layouts — which attributes a row shows, and how (#756).

The display side of :mod:`xefm.attributes`. A **layout** is registered under a
name and says, for one *kind* of list (``details`` today; ``tree`` and
``thumbnails`` are for later), which **columns** a row has and which
**markers** decorate each column's text. A column is an attribute, a format,
a width, an alignment and a priority; a marker is an attribute and a format
drawn beside a column's text.

A **format** turns a value into what is drawn: a built-in one named by a
string (``'relative'``), or a function ``fn(value, entry)`` returning a ``str``,
a :class:`Cell` or a list of cells. Formats only choose text, a color role and
bold/italic; selection, the cursor and the resting pane's dimming are applied
by the pane on top, so nothing a format returns can make a row unreadable.

Which layout a pane uses is chosen by hand (``choose_layout``) or by
``LAYOUT_RULES`` — a list only ``config.py`` writes, so that installing an
extension never changes how a folder looks.
"""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Union

from xefm import attributes
from xefm.log_manager import getLogger
from xefm.str_format import format_size

logger = getLogger("Layouts")

#: The kinds of layout. Only ``details`` is drawn today.
KINDS = ("details",)
#: Where a marker sits relative to the text it decorates.
SIDES = ("after", "before")
ALIGNS = ("left", "right")
#: The name of the layout every pane falls back to.
DEFAULT = "default"
#: A marker's widest default extent, in cells (the old tag dots: three).
MARKER_MAX_WIDTH = 3
#: The keys a column / marker dict accepts.
COLUMN_KEYS = ("attr", "format", "width", "align", "priority", "refresh", "markers")
MARKER_KEYS = ("attr", "format", "side", "max_width")
LAYOUT_KEYS = ("label", "kind", "columns", "override")


@dataclass(frozen=True)
class Cell:
    """A piece of formatted text with its look.

    ``color`` is a role — ``'muted'``, ``'accent'``, ``'accent2'``, ``'text'``
    — a color name (``'red'``, ``'green'``, ``'yellow'``, ``'blue'``,
    ``'purple'``, ``'orange'``, ``'gray'``) or an ``(r, g, b)`` tuple. ``None``
    keeps the column's own ink."""
    text: str
    color: Union[str, tuple, None] = None
    bold: bool = False
    italic: bool = False


FormatResult = Union[str, Cell, list, None]


# --- built-in formats -------------------------------------------------------------

@dataclass(frozen=True)
class Row:
    """What a built-in format knows about the row it formats. A format of the
    user's own is handed the :class:`~xefm.user_api.EntryInfo` instead."""
    is_dir: bool = False
    ok: bool = True
    attr: Any = None


def _fmt_text(value, entry):
    return "" if value is None else str(value)


def _fmt_count(value, entry):
    return "" if value is None else f"{value:,}" if isinstance(value, int) else str(value)


def _size_placeholder(row) -> str:
    if not row.ok:
        return "---"
    return "<DIR>" if row.is_dir else ""


def _fmt_compact(value, entry):
    if value is None:
        return _size_placeholder(entry)
    return format_size(value, compact=True)


def _fmt_bytes(value, entry):
    if value is None:
        return _size_placeholder(entry)
    return f"{value:,}"


def _time_formatter(pattern: str):
    def fmt(value, entry):
        if value is None:
            return "" if entry.ok else "---"
        try:
            return datetime.fromtimestamp(value).strftime(pattern)
        except (OverflowError, OSError, ValueError):
            return "---"
    return fmt


def _fmt_relative(value, entry):
    if value is None:
        return ""
    seconds = time.time() - value
    if seconds < 60:
        return "just now"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)} min ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} h ago"
    days = hours / 24
    if days < 14:
        return f"{int(days)} days ago"
    if days < 60:
        return f"{int(days // 7)} wk ago"
    if days < 365:
        return f"{int(days // 30)} mo ago"
    return f"{int(days // 365)} yr ago"


def _fmt_recent(value, entry):
    """As short as the age allows: the time for today, the day for this year,
    the year before that — ``13:24``, ``10/21``, ``2024``."""
    if value is None:
        return "" if entry.ok else "---"
    try:
        when = datetime.fromtimestamp(value)
    except (OverflowError, OSError, ValueError):
        return "---"
    now = datetime.now()
    if when.date() == now.date():
        return when.strftime("%H:%M")
    if when.year == now.year:
        return when.strftime("%m/%d")
    return str(when.year)


def _enum_spec(row, value) -> dict:
    attr = row.attr
    return (attr.values.get(value) if attr is not None else None) or {}


def _fmt_letter(value, entry):
    if value is None or value == "":
        return ""
    return Cell(str(value), color=_enum_spec(entry, value).get("color"))


def _fmt_word(value, entry):
    if value is None or value == "":
        return ""
    spec = _enum_spec(entry, value)
    return Cell(str(spec.get("label", value)), color=spec.get("color"))


TAG_DOT = "●"


def _fmt_dots(value, entry):
    return [Cell(TAG_DOT, color=getattr(tag, "color_name", None)) for tag in value or []]


def _fmt_names(value, entry):
    return ", ".join(getattr(tag, "name", str(tag)) for tag in value or [])


@dataclass(frozen=True)
class Format:
    func: Callable
    width: int = 10
    align: str = "left"
    mono: bool = False
    refresh: Optional[float] = None


#: ``{type: {name: Format}}``, the first of each type its default.
FORMATS: dict[str, dict[str, Format]] = {
    "text": {"text": Format(_fmt_text, 12)},
    "count": {"number": Format(_fmt_count, 7, "right", True)},
    "size": {"compact": Format(_fmt_compact, 9, "right", True),
             "bytes": Format(_fmt_bytes, 15, "right", True)},
    "time": {"short": Format(_time_formatter("%y-%m-%d %H:%M"), 14, "right", True),
             "full": Format(_time_formatter("%Y-%m-%d %H:%M:%S"), 19, "right", True),
             "iso": Format(_time_formatter("%Y-%m-%d %H:%M"), 16, "right", True),
             "relative": Format(_fmt_relative, 10, "right", True, refresh=60.0),
             "recent": Format(_fmt_recent, 5, "right", True, refresh=60.0)},
    "enum": {"letter": Format(_fmt_letter, 1), "word": Format(_fmt_word, 10)},
    "tags": {"dots": Format(_fmt_dots, MARKER_MAX_WIDTH),
             "names": Format(_fmt_names, 16)},
}


def format_names(kind: str) -> list[str]:
    return list(FORMATS.get(kind, {}))


def default_format(kind: str, config=None) -> str:
    if kind == "time" and config is not None:
        if getattr(config, "DATE_FORMAT", "short") == "full":
            return "full"
        return "short"
    return next(iter(FORMATS.get(kind, FORMATS["text"])))


def enum_width(attr, fmt: str) -> int:
    if not attr.values:
        return 1 if fmt == "letter" else 10
    if fmt == "letter":
        return max(len(str(k)) for k in attr.values)
    return max(len(str(v.get("label", k))) for k, v in attr.values.items())


#: Value types drawn right-aligned in a fixed-advance face when the format
#: does not say otherwise.
NUMERIC = ("count", "size", "time")


@dataclass(frozen=True)
class Resolved:
    """A column's or marker's format, resolved against its attribute: the
    function to call, whether it is one of ours, and how it is laid out."""
    func: Callable
    builtin: bool
    width: int
    align: str
    mono: bool
    refresh: Optional[float]


def resolve_format(fmt, attr, config=None, *, width=None, align=None,
                   refresh=None) -> Resolved:
    kind = attr.type if attr is not None else "text"
    numeric = kind in NUMERIC
    if callable(fmt):
        return Resolved(fmt, False, width or 10, align or ("right" if numeric else "left"),
                        numeric, refresh)
    table = FORMATS.get(kind, FORMATS["text"])
    name = fmt if isinstance(fmt, str) and fmt in table else default_format(kind, config)
    spec = table[name]
    default_width = enum_width(attr, name) if kind == "enum" and attr is not None else spec.width
    return Resolved(spec.func, True, width or default_width, align or spec.align,
                    spec.mono, refresh if refresh is not None else spec.refresh)


_failed_formats: set = set()


def render(resolved: Resolved, value, row: Row, entry_factory) -> list[Cell]:
    """Run a format and normalize what it returned to a list of cells. A
    format of the user's own that raises draws nothing, logged once."""
    try:
        if resolved.builtin:
            out = resolved.func(value, row)
        else:
            out = resolved.func(value, entry_factory())
    except Exception as exc:  # noqa: BLE001 — a format's failure costs its cell
        key = getattr(resolved.func, "__qualname__", repr(resolved.func))
        if key not in _failed_formats:
            _failed_formats.add(key)
            logger.error(f"Format {key} failed: {exc}")
        return []
    if out is None or out == "":
        return []
    if isinstance(out, (str, Cell)):
        out = [out]
    cells = []
    for item in out:
        if isinstance(item, Cell):
            if item.text:
                cells.append(item)
        elif item is not None and str(item):
            cells.append(Cell(str(item)))
    return cells


# --- the model --------------------------------------------------------------------

@dataclass(frozen=True)
class Marker:
    attr: str
    format: Union[str, Callable, None] = None
    side: str = "after"
    max_width: int = MARKER_MAX_WIDTH


@dataclass(frozen=True)
class Column:
    attr: str
    format: Union[str, Callable, None] = None
    width: Optional[int] = None
    align: Optional[str] = None
    #: Columns with a priority are dropped, lowest first, when the pane is too
    #: narrow for the name; one without stays.
    priority: Optional[int] = None
    refresh: Optional[float] = None
    markers: tuple = ()


@dataclass(frozen=True)
class Layout:
    name: str
    label: str
    kind: str = "details"
    columns: tuple = ()
    source: str = "builtin"

    def attributes(self) -> set[str]:
        """Every attribute this layout draws — a column or a marker."""
        out = set()
        for col in self.columns:
            out.add(col.attr)
            out.update(m.attr for m in col.markers)
        return out


BUILTIN_DEFAULT = Layout(DEFAULT, "Default", "details", (
    Column("name", markers=(Marker("tags"),)),
    Column("ext"),
    Column("total_size"),
    Column("mtime", priority=1),
))

_user: dict[str, Layout] = {}


def register(layout: Layout) -> None:
    _user[layout.name] = layout


def clear() -> None:
    _user.clear()
    _rules.clear()


def get(name: Optional[str]) -> Optional[Layout]:
    if name is None:
        return None
    if name in _user:
        return _user[name]
    return BUILTIN_DEFAULT if name == DEFAULT else None


def all_layouts() -> list[Layout]:
    """Every layout, ``default`` first."""
    out = [get(DEFAULT)]
    out.extend(l for n, l in _user.items() if n != DEFAULT)
    return out


# --- building from config -----------------------------------------------------------

def _build_format(where: str, attr, fmt) -> Optional[str]:
    if fmt is None or callable(fmt):
        return None
    if not isinstance(fmt, str):
        return f"{where}: 'format' must be a format name or a function"
    if attr is not None and fmt not in FORMATS.get(attr.type, {}):
        known = ", ".join(format_names(attr.type))
        return f"{where}: '{fmt}' is not a format for a {attr.type} value — known: {known}"
    return None


def _build_marker(where: str, spec) -> tuple[Optional[Marker], Optional[str]]:
    if isinstance(spec, str):
        spec = {"attr": spec}
    if not isinstance(spec, dict):
        return None, f"{where} must be an attribute name or a dict"
    unknown = sorted(set(spec) - set(MARKER_KEYS))
    if unknown:
        return None, f"{where}: unknown keys {', '.join(unknown)} — known: {', '.join(MARKER_KEYS)}"
    name = spec.get("attr")
    attr = attributes.get(name) if isinstance(name, str) else None
    problem = _build_format(where, attr, spec.get("format"))
    if problem:
        return None, problem
    side = spec.get("side", "after")
    if side not in SIDES:
        return None, f"{where}: side '{side}' is not one of {', '.join(SIDES)}"
    max_width = spec.get("max_width", MARKER_MAX_WIDTH)
    if not isinstance(max_width, int) or max_width < 1:
        return None, f"{where}: 'max_width' must be a positive whole number of cells"
    if not isinstance(name, str):
        return None, f"{where} needs 'attr'"
    return Marker(name, spec.get("format"), side, max_width), None


def _build_column(where: str, spec) -> tuple[Optional[Column], Optional[str]]:
    if isinstance(spec, str):
        spec = {"attr": spec}
    if not isinstance(spec, dict):
        return None, f"{where} must be an attribute name or a dict"
    unknown = sorted(set(spec) - set(COLUMN_KEYS))
    if unknown:
        return None, f"{where}: unknown keys {', '.join(unknown)} — known: {', '.join(COLUMN_KEYS)}"
    name = spec.get("attr")
    if not isinstance(name, str):
        return None, f"{where} needs 'attr'"
    attr = attributes.get(name)
    problem = _build_format(where, attr, spec.get("format"))
    if problem:
        return None, problem
    width = spec.get("width")
    if width is not None and (not isinstance(width, int) or width < 1):
        return None, f"{where}: 'width' must be a positive whole number of cells"
    align = spec.get("align")
    if align is not None and align not in ALIGNS:
        return None, f"{where}: align '{align}' is not one of {', '.join(ALIGNS)}"
    priority = spec.get("priority")
    if priority is not None and not isinstance(priority, int):
        return None, f"{where}: 'priority' must be a whole number"
    refresh = spec.get("refresh")
    if refresh is not None and (not isinstance(refresh, (int, float)) or refresh <= 0):
        return None, f"{where}: 'refresh' must be a number of seconds"
    markers = []
    for i, m in enumerate(spec.get("markers") or ()):
        marker, problem = _build_marker(f"{where}['markers'][{i}]", m)
        if problem:
            return None, problem
        markers.append(marker)
    return Column(name, spec.get("format"), width, align, priority, refresh,
                  tuple(markers)), None


def build(name: str, spec) -> tuple[Optional[Layout], Optional[str]]:
    """Validate one ``LAYOUTS`` entry: a :class:`Layout`, or a problem."""
    where = f"LAYOUTS['{name}']"
    if not isinstance(name, str) or not name:
        return None, f"{where}: the name must be a non-empty string"
    if not isinstance(spec, dict):
        return None, f"{where} must be a dict with 'columns'"
    unknown = sorted(set(spec) - set(LAYOUT_KEYS))
    if unknown:
        return None, f"{where}: unknown keys {', '.join(unknown)} — known: {', '.join(LAYOUT_KEYS)}"
    if name == DEFAULT and not spec.get("override"):
        return None, (f"{where} would replace the built-in layout and was ignored — "
                      f"add 'override': True if that is intended")
    kind = spec.get("kind", "details")
    if kind not in KINDS:
        return None, f"{where}: kind '{kind}' is not one of {', '.join(KINDS)}"
    specs = spec.get("columns")
    if not isinstance(specs, (list, tuple)) or not specs:
        return None, f"{where} needs 'columns', a list"
    columns = []
    for i, c in enumerate(specs):
        column, problem = _build_column(f"{where}['columns'][{i}]", c)
        if problem:
            return None, problem
        columns.append(column)
    if not any(c.attr == "name" for c in columns):
        return None, f"{where} has no 'name' column — every layout shows the name"
    label = spec.get("label") or name
    return Layout(name, str(label), kind, tuple(columns), source="user"), None


def unknown_attributes(layout: Layout) -> list[str]:
    """Attributes a layout names that nothing registered (checked after every
    table has loaded, since an attribute may come from an extension)."""
    return sorted(n for n in layout.attributes() if not attributes.is_known(n))


# --- rules -----------------------------------------------------------------------------

#: ``[(predicate, layout name)]`` from ``LAYOUT_RULES``.
_rules: list[tuple[Union[str, Callable], str]] = []


def build_rule(i: int, spec) -> tuple[Optional[tuple], Optional[str]]:
    where = f"LAYOUT_RULES[{i}]"
    if not isinstance(spec, (list, tuple)) or len(spec) != 2:
        return None, f"{where} must be a pair: (pattern or function, layout name)"
    test, name = spec
    if not isinstance(name, str):
        return None, f"{where}: the layout name must be a string"
    if not (isinstance(test, str) or callable(test)):
        return None, f"{where}: the condition must be a path pattern or a function of the path"
    return (test, name), None


def set_rules(rules: list) -> None:
    _rules[:] = rules


def resolve(path) -> Optional[str]:
    """The layout ``LAYOUT_RULES`` picks for ``path``, or None. Called on the
    listing worker, so a rule may touch the filesystem."""
    for test, name in list(_rules):
        try:
            if isinstance(test, str):
                hit = fnmatch.fnmatch(str(path), test)
            else:
                hit = bool(test(path))
        except Exception as exc:  # noqa: BLE001 — a broken rule is skipped
            logger.error(f"Layout rule for '{name}' failed: {exc}")
            continue
        if hit:
            return name
    return None


def effective(pane: dict) -> Layout:
    """The layout ``pane`` draws with: the one chosen by hand, else the one the
    rules picked for its directory, else ``default``."""
    for name in (pane.get("layout"), pane.get("_layout_auto")):
        layout = get(name)
        if layout is not None:
            return layout
    return get(DEFAULT)
