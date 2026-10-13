"""Keymap presets — a second layout over the shipped key bindings (#565).

XeFM's default keymap runs commands on bare letters: ``C`` copies, ``K``
deletes. A preset swaps that layout for another one users already know,
without touching what they rebound themselves.

A preset is **a key table plus behavior flags**:

- ``bindings`` — action name → keys, replacing that action's keys;
- ``free_letters`` — take every bare letter and digit (``K``, ``Shift-K``,
  ``1``) off the file list's actions and the shared ones (``quit``,
  ``edit_file``), so typing a letter never runs anything;
- ``type_ahead`` — an unbound printable key in the file list starts
  incremental search with that character, the way typing in a file list does
  almost everywhere else.

:func:`apply` writes the result into ``config.KEY_BINDINGS`` itself, so every
reader — the app's keymap, the help dialog, the menus, the directory diff
viewer — sees one table. It changes an action **only where the config still
holds the shipped value**: an action the user rebound in ``config.py`` keeps
their keys under every preset. The table the config was loaded with is kept
on the config (``_KEY_BINDINGS_BASE``), so presets can be switched back and
forth at runtime without compounding.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from xefm.log_manager import getLogger

logger = getLogger("Keymap")

#: XeFM's own letter layout, named for its lineage: the single-key Japanese
#: filers — the X68000 ones, then AFX (あふ), then cfiler — rather than for
#: being the default, which says nothing about what it is. Not a replica of
#: AFX's table; the direction, not the details.
AFX = "afx"
ORTHODOX = "orthodox"
#: The preset that ships. Its name stays a name, not "default".
DEFAULT = AFX
#: Earlier spellings still accepted, so a config or a saved menu choice that
#: says ``'default'`` keeps meaning what it meant.
ALIASES = {"default": AFX}


def canonical(name: Optional[str]) -> Optional[str]:
    """``name`` with an old spelling (``'default'``) replaced by its preset."""
    return ALIASES.get(name, name) if name else name


@dataclass(frozen=True)
class Preset:
    name: str
    label: str
    description: str
    bindings: dict = field(default_factory=dict)
    free_letters: bool = False
    type_ahead: bool = False


#: The function-key layout shared by the "orthodox" two-pane file managers —
#: F3 view, F5 copy, F8 delete — and nothing on a bare letter.
_ORTHODOX = Preset(
    name=ORTHODOX,
    label="Orthodox (function keys)",
    description=("F3 view, F4 edit, F5 copy, F6 move, F7 new folder, F8 "
                 "delete; typing a letter searches."),
    free_letters=True,
    type_ahead=True,
    # Total Commander's default keys wherever XeFM has the action (its
    # keyboard map: Configuration > Keyboard, KEYBOARD.TXT). Where TC's key
    # does something XeFM has no action for, the key is simply not bound;
    # where XeFM has an action TC has no key for, the action keeps no key
    # here and is reached from the menus and the command palette. Actions
    # from features not merged yet are listed too: ``apply`` skips any the
    # running XeFM does not have.
    bindings={
        # Application
        "help": ["F1"],
        "reread": ["F2", "Ctrl-R"],
        "menu": ["F9", "F10", "ALT"],
        "quit": ["Alt-F4"],
        "redraw": [],
        "programs": [],
        "context_menu": ["Shift-F10", "APPS"],
        "command_palette": ["Ctrl-Shift-P"],   # TC has none; Ctrl-T is tabs
        # Files
        "view_file": ["F3"],
        "edit_file": ["F4"],
        "create_file": ["Shift-F4"],
        "copy_files": ["F5"],
        "duplicate_files": ["Shift-F5"],        # TC: copy with rename, same dir
        "move_files": ["F6"],
        "rename": ["Shift-F6", "Ctrl-M"],       # Ctrl-M: multi-rename
        "create_directory": ["F7"],
        "delete_files": ["F8", "DELETE"],
        "delete_permanently": ["Shift-F8", "Shift-DELETE"],
        "copy_files_to": [],
        "move_files_to": [],
        "file_details": ["Alt-ENTER"],          # TC: properties
        "create_archive": ["Alt-F5"],
        "extract_archive": ["Alt-F9", "Alt-F6"],
        "clipboard_copy": ["Ctrl-C"],
        "clipboard_cut": ["Ctrl-X"],
        "clipboard_paste": ["Ctrl-V"],
        "copy_names": [],
        "copy_paths": ["Ctrl-P"],
        # Search and filter
        "find_files": ["Alt-F7"],
        "find_in_files": [],
        "filter": ["Ctrl-S"],                   # TC: quick filter
        "clear_filter": ["Ctrl-F10"],           # TC: show all files
        "isearch": [],                          # typing a letter searches
        "index_search": [],
        # Places
        "open_item": ["ENTER", "Ctrl-PAGE_DOWN"],
        "go_parent": ["BACKSPACE", "Ctrl-PAGE_UP"],
        "go_root": ["Ctrl-BACKSLASH"],
        "drives": ["Alt-F1", "Alt-F2"],          # TC: left / right drive
        "history": ["Alt-DOWN"],
        "go_back": ["Alt-LEFT"],
        "go_forward": ["Alt-RIGHT"],
        "favorites": ["Ctrl-D"],                # TC: directory hotlist
        "connect_server": ["Ctrl-F", "Ctrl-N"],  # TC: FTP connect / new URL
        "compare_selection": ["Shift-F2"],      # TC: compare file lists
        "diff_directories": [],
        "flat_view": ["Ctrl-B"],                # TC: branch view
        "quick_view": ["Ctrl-Q"],
        # Tabs
        "new_tab": ["Ctrl-T"],
        "open_in_new_tab": ["Ctrl-UP"],
        "close_tab": ["Ctrl-W"],
        "next_tab": ["Ctrl-TAB"],
        "prev_tab": ["Ctrl-Shift-TAB"],
        # Selection and cursor
        "toggle_select_down": ["INSERT", "SPACE"],
        "select_by_pattern": ["+"],             # TC: Num +
        "unselect_by_pattern": ["-"],           # TC: Num -
        "toggle_select_files": ["*"],           # TC: Num * (invert)
        "select_all": ["Ctrl-A"],
        "unselect_all": ["Ctrl-MINUS"],         # TC: Ctrl-Num -
        "select_same_extension": ["Alt-+"],     # TC: Alt-Num +
        "cursor_top": ["HOME", "Ctrl-HOME"],
        "cursor_bottom": ["END", "Ctrl-END"],
        "cursor_next_selected": [],             # Ctrl-Up opens a tab here
        "cursor_prev_selected": [],
        "reveal_in_os": [],                     # Ctrl-R rereads here
        "reset_pane_boundary": [],              # '-' unselects here
        "reset_log_height": [],                 # '_' starts names (__init__.py)
        # Sorting
        "quick_sort_name": ["Ctrl-F3"],
        "quick_sort_ext": ["Ctrl-F4"],
        "quick_sort_date": ["Ctrl-F5"],
        "quick_sort_size": ["Ctrl-F6"],
    },
)

PRESETS: dict[str, Optional[Preset]] = {AFX: None, ORTHODOX: _ORTHODOX}

LABELS = {AFX: "AFX style (letters)", ORTHODOX: _ORTHODOX.label}


def get(name: Optional[str]) -> Optional[Preset]:
    """The preset called ``name``, or None for the default keymap (and for a
    name nothing answers to, which is logged)."""
    name = canonical(name)
    if not name or name == DEFAULT:
        return None
    preset = PRESETS.get(name)
    if preset is None:
        logger.warning(f"Unknown keymap preset {name!r}; using the default keymap")
    return preset


def resolve(config, chosen: Optional[str]) -> str:
    """The preset in force: ``KEY_PRESET`` from the config when it names one,
    else ``chosen`` (the View menu's choice), else the default."""
    configured = canonical(getattr(config, "KEY_PRESET", None))
    name = configured or canonical(chosen) or DEFAULT
    return name if name in PRESETS else DEFAULT


def _keys_of(value) -> list:
    if isinstance(value, dict):
        return list(value.get("keys", []))
    return list(value or [])


def is_typing_key(expr: str) -> bool:
    """A binding a user types as text: a bare letter or digit, or a Shift'ed
    letter (which is a capital)."""
    if len(expr) == 1:
        return expr.isalnum()
    if expr.startswith("Shift-") and len(expr) == len("Shift-") + 1:
        return expr[-1].isalpha()
    return False


def _typing_contexts() -> set:
    """The action names whose bare letters a preset frees: the file list's own
    and the shared ones. A viewer's own actions (``text_viewer.toggle_wrap``)
    keep their letters — nothing is typed into a viewer."""
    from xefm.actions import COMMON, FILER, registry
    return {a.name for a in registry.actions(FILER)} | \
        {a.name for a in registry.actions(COMMON)}


def apply(config, name: Optional[str], template: Optional[dict] = None) -> None:
    """Make ``config.KEY_BINDINGS`` the table for preset ``name`` (None or
    ``'afx'`` — or its old name ``'default'`` — for the shipped keymap), and set ``config._KEY_TYPE_AHEAD``.

    ``template`` is the shipped ``KEY_BINDINGS`` — what an action holds when
    the user has not touched it — read from :mod:`xefm._config` when omitted."""
    if template is None:
        from xefm._config import Config as _Template
        template = _Template.KEY_BINDINGS
    base = getattr(config, "_KEY_BINDINGS_BASE", None)
    if base is None:
        base = copy.deepcopy(config.KEY_BINDINGS)
        config._KEY_BINDINGS_BASE = base
    table = copy.deepcopy(base)
    preset = get(name)
    config._KEY_TYPE_AHEAD = bool(preset and preset.type_ahead)
    if preset is None:
        config.KEY_BINDINGS = table
        return

    def untouched(action: str) -> bool:
        return action not in base or base[action] == template.get(action)

    if preset.free_letters:
        typing = _typing_contexts()
        for action, value in list(table.items()):
            if action not in typing or not untouched(action):
                continue
            kept = [k for k in _keys_of(value) if not is_typing_key(k)]
            if len(kept) != len(_keys_of(value)):
                table[action] = (dict(value, keys=kept) if isinstance(value, dict)
                                 else kept)
    # A preset's keys are a plain list, dropping any selection gate: an
    # orthodox F5 copies the cursor item when nothing is marked.
    from xefm.actions import FILER, registry
    for action, keys in preset.bindings.items():
        # A preset may name actions of features this XeFM does not have yet;
        # binding them would only claim their keys for nothing.
        if registry.resolve(FILER, action) is None:
            continue
        if untouched(action):
            table[action] = list(keys)
    config.KEY_BINDINGS = table


def type_ahead(config) -> bool:
    """Whether the preset in force starts a search on an unbound typed key."""
    return bool(getattr(config, "_KEY_TYPE_AHEAD", False))
