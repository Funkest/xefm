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

This module is XeFM's own. Extensions read the result as
``xefm.user_api.PREVIEW_APIS``.
"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")

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
    under ``@property`` for a property, so the getter is what it marks."""
    PREVIEW_APIS.add(f"{obj.__module__}.{obj.__qualname__}")
    doc = obj.__doc__ or ""
    obj.__doc__ = f"{NOTE}\n\n{doc}" if doc else NOTE
    return obj


def is_preview(name: str) -> bool:
    """Whether the API called ``name`` (as :data:`PREVIEW_APIS` spells names)
    is Preview, itself or through the class that holds it."""
    parts = name.split(".")
    return any(".".join(parts[:i]) in PREVIEW_APIS for i in range(1, len(parts) + 1))
