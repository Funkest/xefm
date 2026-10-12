"""Opening an action's page from the Help dialog.

A Help row whose action has details links to that action's page
(``xefm-action:<name>``); following the link — Tab to it and Enter, or a click —
opens the page over the help, the same page the command palette shows on F1,
and Esc returns to the help where it was. Other links are declined, so PuiKit
opens them as usual.

Run with: python -m pytest test/test_help_action_links.py -v
"""

import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from puikit.backends.memory_backend import MemoryBackend  # noqa: E402
from puikit.event import Event, EventType  # noqa: E402

from xefm import actions as xa  # noqa: E402
from xefm import app as xefm_app  # noqa: E402
from xefm import user_api  # noqa: E402
from xefm._config import Config as DefaultConfig  # noqa: E402
from xefm.config import config_manager  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402
from xefm.text_dialog import MarkdownDialog  # noqa: E402


def key(name, mods=()):
    return Event(type=EventType.KEY, key=name, modifiers=frozenset(mods))


@pytest.fixture
def app():
    tmp, cfgdir = tempfile.mkdtemp(), tempfile.mkdtemp()
    saved = (config_manager.config, config_manager._key_bindings)
    config_manager.config = DefaultConfig()
    config_manager._key_bindings = None
    sm = XeFMStateManager(db_path=os.path.join(cfgdir, "state.db"))
    backend = MemoryBackend(width=120, height=40)
    backend.open()
    a = xefm_app.XeFMApp(backend, tmp, tmp, left_provided=True,
                         right_provided=True, state_manager=sm)
    a._settle_listings()
    yield a
    try:
        a._restore_streams()
        a.file_monitor.stop_monitoring()
        backend.close()
        sm.close()
    except Exception:
        pass
    config_manager.config, config_manager._key_bindings = saved
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(cfgdir, ignore_errors=True)
    xa.registry.unregister_source("user")
    user_api.hooks.clear()


def _top(app):
    return app.panel._layers[-1].widget


def _help(app):
    app.show_help()
    dialog = _top(app)
    assert isinstance(dialog, MarkdownDialog)
    app.panel.render()          # lay the document out, so its links exist
    return dialog


def test_a_row_with_details_links_to_its_page(app):
    assert "](xefm-action:copy_files)" in app._help_markdown()


def test_a_row_without_details_stays_plain(app):
    assert xa.registry.resolve(xa.FILER, "cursor_up").details == ""
    assert "xefm-action:cursor_up)" not in app._help_markdown()


def test_a_viewer_row_stays_plain(app):
    """The isearch section lists the search bar's own actions; they have no
    page, so they must not look like links."""
    assert "xefm-action:isearch.next_match" not in app._help_markdown()


def test_tab_then_enter_opens_the_page_over_the_help(app):
    help_dialog = _help(app)
    help_dialog.handle_event(key("tab"))
    first = help_dialog.md.focused_link
    assert first is not None and first.startswith("xefm-action:")
    help_dialog.handle_event(key("enter"))
    page = _top(app)
    assert isinstance(page, MarkdownDialog) and page is not help_dialog
    assert page.title == first[len("xefm-action:"):]
    # Esc closes the page and leaves the help, still on the same link.
    page.handle_event(key("escape"))
    assert _top(app) is help_dialog
    assert help_dialog.md.focused_link == first


def test_enter_without_a_focused_link_still_closes_the_help(app):
    help_dialog = _help(app)
    help_dialog.handle_event(key("enter"))
    assert help_dialog not in [slot.widget for slot in app.panel._layers]


def test_shift_tab_steps_backwards_and_tab_cycles(app):
    help_dialog = _help(app)
    help_dialog.handle_event(key("tab", {"shift"}))
    last = help_dialog.md.focused_link
    assert last is not None
    help_dialog.handle_event(key("tab"))        # off the end ...
    help_dialog.handle_event(key("tab", {"shift"}))
    assert help_dialog.md.focused_link == last  # ... and back


def test_the_page_is_the_palette_page(app):
    action = xa.registry.resolve(xa.FILER, "copy_files")
    assert app._follow_action_link("xefm-action:copy_files")
    page = _top(app)
    assert page.md is not None
    assert app._action_page(action).startswith(action.description)


def test_other_links_are_declined(app):
    assert app._follow_action_link("https://example.com") is False


def test_an_unknown_action_link_is_taken_but_opens_nothing(app):
    before = len(app.panel._layers)
    assert app._follow_action_link("xefm-action:no_such_action")
    assert len(app.panel._layers) == before


def test_a_user_action_with_a_docstring_body_is_linked(app):
    def tidy(ctx):
        """Tidy the pane.

        Longer explanation.
        """
    from xefm.user_api import load_user_entries
    cfg = DefaultConfig()
    cfg.ACTIONS = {"tidy up": tidy}
    load_user_entries(cfg)
    md = app._help_markdown()
    assert "[Tidy the pane.](xefm-action:tidy%20up)" in md
    assert app._follow_action_link("xefm-action:tidy%20up")
    assert _top(app).title == "tidy up"


def _slot(app, widget):
    return next(s for s in app.panel._layers if s.widget is widget)


def test_the_page_sits_inside_the_help_and_dims_it(app):
    """Same chrome on the same surface, one covering the other, read as one
    box: the page is inset within the help on every side and dims it."""
    help_dialog = _help(app)
    app._follow_action_link("xefm-action:copy_files")
    page = _top(app)
    outer, inner = _slot(app, help_dialog).rect, _slot(app, page).rect
    assert inner.x > outer.x and inner.x + inner.w < outer.x + outer.w
    assert inner.y > outer.y and inner.y + inner.h < outer.y + outer.h
    assert _slot(app, page).hints.get("dim_below")
    assert _slot(app, page).z > _slot(app, help_dialog).z


def test_the_palette_page_sits_inside_the_palette(app):
    app.show_command_palette()
    palette = _top(app)
    palette.handle_event(key("f1"))
    page = _top(app)
    assert page is not palette
    outer, inner = _slot(app, palette).rect, _slot(app, page).rect
    assert inner.x > outer.x and inner.x + inner.w < outer.x + outer.w
    assert _slot(app, page).hints.get("dim_below")
