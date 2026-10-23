"""Which parts of XeFM's public API are Preview (#632).

Preview is a property of one API, not of the whole surface: a method, a class,
a ``config.py`` table or a manifest section is Preview — free to change in any
release — until it is declared stable, and the rest of the API need not wait
for it. ``API_VERSION`` promises only what is *not* Preview.

The mark lives on the definition, where whoever reads the code meets it:

- A function, method, property or class carries ``@preview``. That records it
  in :data:`PREVIEW_APIS` and opens its docstring with the word, so the source,
  ``help()`` and the registry all say the same thing. On a class it covers
  every member; a member of an unmarked class carries its own.
- A ``config.py`` table or a manifest section is not a Python object, so its
  name is listed here, below.

Stabilizing an API is deleting its mark. ``API_VERSION`` 1 was the first
release with a stable part (doc/dev/STABLE_API_PLAN.md §1 has the split).

Use is also told at run time (plan §4.1): the first time code outside XeFM
calls a Preview function or method, one line in the log names who — an
extension by its id, or ``config.py`` — and what. :func:`record_use` is that
line, and ``xefm.path_base`` calls it for a backend that subclasses a Preview
class or defines a Preview member.

This module is XeFM's own. Extensions read the result as
``xefm.user_api.PREVIEW_APIS``.
"""

from __future__ import annotations

import functools
import inspect
import sys
from typing import TypeVar

from xefm.log_manager import getLogger

T = TypeVar("T")

logger = getLogger("PreviewAPI")

#: ``(who, api)`` pairs already logged, so each is said once per session.
_recorded: set[tuple[str, str]] = set()

#: The module name ``config.py`` is executed under (:mod:`xefm.config`).
_CONFIG_MODULE = "user_config"

#: The note a Preview API's docstring opens with.
NOTE = "Preview — may change in any release."

#: Every Preview API by name: ``xefm.user_api.ActionContext.run_task`` for
#: code, ``config.MENU_ITEMS`` for a ``config.py`` table,
#: ``manifest.contributes.menus`` for a manifest section. An entry for a class
#: covers its members.
PREVIEW_APIS: set[str] = {
    # config.py tables. ACTIONS, SORT_KEYS, FILTERS and PATH_SCHEMES are
    # stable; replacing a built-in scheme is not.
    *(f"config.{table}" for table in (
        "EVENT_HOOKS", "IMAGE_DECODERS", "LEXERS", "MENU_ITEMS")),
    "config.PATH_SCHEMES.override",
    # xefm-extension.toml. actions, sort_keys, filters, path_schemes and
    # key_suggestions are stable.
    *(f"manifest.contributes.{kind}" for kind in (
        "event_hooks", "image_decoders", "lexers", "themes", "menus")),
    "manifest.extension.updates",
    "manifest.settings",
    "manifest.requires",
}


def preview(obj: T) -> T:
    """Mark a function, method, property getter or class as Preview. Put it
    under ``@property`` for a property, so the getter is what it marks.

    A function or method comes back wrapped, so that the first call from
    outside XeFM is recorded (:func:`record_use`). A class is not: the ones
    XeFM hands over (``TaskJob``, ``HookEvent``) are reached only through a
    Preview entry point that is already recorded, and subclassing one says so
    in its own ``__init_subclass__``."""
    name = f"{obj.__module__}.{obj.__qualname__}"
    PREVIEW_APIS.add(name)
    doc = obj.__doc__ or ""
    obj.__doc__ = f"{NOTE}\n\n{doc}" if doc else NOTE
    if inspect.isclass(obj) or not callable(obj):
        return obj
    api = obj.__qualname__

    @functools.wraps(obj)
    def recorded(*args, **kwargs):
        record_use(api, sys._getframe(1).f_globals.get("__name__", ""))
        return obj(*args, **kwargs)

    return recorded  # type: ignore[return-value]


def record_use(api: str, module: str) -> None:
    """Log, once per session, that ``module`` used the Preview API ``api``
    (``ActionContext.run_task``). XeFM's own modules are not reported: XeFM
    calls some Preview APIs itself."""
    if module == "xefm" or module.startswith("xefm."):
        return
    if module == _CONFIG_MODULE:
        who = "config.py"
    else:
        from xefm.extensions import handle_for_module
        handle = handle_for_module(module)
        who = f"Extension {handle.id}" if handle is not None else module
    if (who, api) in _recorded:
        return
    _recorded.add((who, api))
    logger.info(f"{who} uses Preview API {api} — it may change in any release")


def is_preview(name: str) -> bool:
    """Whether the API called ``name`` (as :data:`PREVIEW_APIS` spells names)
    is Preview, itself or through the class that holds it."""
    parts = name.split(".")
    return any(".".join(parts[:i]) in PREVIEW_APIS for i in range(1, len(parts) + 1))
