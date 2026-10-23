"""The platform's own ways to quit go through the quit action.

The macOS application menu's Quit (⌘Q) and the Dock's, and the window's close
button, used to end XeFM at once: no confirm, background jobs killed
mid-write, no 'quit' hooks, pane state not saved. XeFM now takes those
requests (``Panel.set_quit_handler``) and answers them as the keymap's quit key
does. The menu's Quit item shows the keymap's key for quitting.
"""

import os
import sys
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))
sys.path.insert(0, _HERE)

from test_customization_api import app_with  # noqa: E402,F401
from xefm.config import KeyBindings  # noqa: E402


def _layers(app):
    return len(app.panel._layers)


def test_a_platform_quit_request_asks_first(app_with):
    app, _tmp = app_with()
    assert app.backend._quit_request() is True     # XeFM took it
    assert app.panel.has_layers                    # the confirm is up
    assert app._quit_confirming


def test_a_second_request_does_not_stack_a_second_confirm(app_with):
    app, _tmp = app_with()
    app.backend._quit_request()
    before = _layers(app)
    app.backend._quit_request()
    assert _layers(app) == before


def test_answering_quit_runs_the_whole_quit(app_with):
    app, _tmp = app_with()
    shown = []
    with patch("xefm.app.show_message_box", lambda *a, **k: shown.append(k)), \
            patch.object(app, "_quit") as quit_:
        app.backend._quit_request()
        shown[0]["on_result"]("Quit")
    assert quit_.called
    assert not app._quit_confirming


def test_cancel_leaves_xefm_running_and_ready_to_ask_again(app_with):
    app, _tmp = app_with()
    shown = []
    with patch("xefm.app.show_message_box", lambda *a, **k: shown.append(k)), \
            patch.object(app, "_quit") as quit_:
        app.backend._quit_request()
        shown[0]["on_result"]("Cancel")
        app.backend._quit_request()
    assert not quit_.called
    assert len(shown) == 2


def test_the_menu_shows_the_keymaps_key_for_quitting(app_with):
    app, _tmp = app_with()
    assert app.backend._quit_shortcut == app._quit_shortcut()
    app.keys = KeyBindings({"quit": ["Command-Q", "Ctrl-Q"]})
    assert app._quit_shortcut() == "Cmd-Q"
    app.keys = KeyBindings({"quit": []})
    assert app._quit_shortcut() is None


def test_a_keymap_rebuild_updates_the_menus_quit_key(app_with):
    app, _tmp = app_with()
    with patch.object(app, "_quit_shortcut", return_value="Cmd-Q"):
        app._rebuild_keymap()
    assert app.backend._quit_shortcut == "Cmd-Q"
