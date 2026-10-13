"""Keymap presets (#565): a second layout over the shipped key bindings.

The pure half lays a preset over a ``KEY_BINDINGS`` table and checks what
moved, what stayed the user's, and what was freed. The app half switches
presets from the View menu's entry point and presses keys on the memory
backend.

Run with: python -m pytest test/test_keymap_presets.py -v
"""

import copy
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from puikit import Event, EventType  # noqa: E402

from xefm import _config, keymap_presets  # noqa: E402
from xefm import app as xefm_app  # noqa: E402
from xefm.config import KeyBindings  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402

TEMPLATE = _config.Config.KEY_BINDINGS


def _config_with(**overrides):
    table = copy.deepcopy(TEMPLATE)
    table.update(overrides)
    return types.SimpleNamespace(KEY_BINDINGS=table, KEY_PRESET=None)


def _keys(config, action):
    value = config.KEY_BINDINGS.get(action)
    return value["keys"] if isinstance(value, dict) else value


class Apply(unittest.TestCase):

    def test_orthodox_lays_its_table_over_the_defaults(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        self.assertEqual(_keys(config, "copy_files"), ["F5"])
        self.assertEqual(_keys(config, "delete_files"), ["F8", "DELETE"])
        self.assertEqual(_keys(config, "redraw"), [])
        self.assertTrue(keymap_presets.type_ahead(config))

    def test_a_preset_key_has_no_selection_gate(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        # copy_files ships as {'keys': ['C'], 'selection': 'required'}.
        self.assertEqual(config.KEY_BINDINGS["copy_files"], ["F5"])

    def test_bare_letters_leave_the_file_list(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        for action, value in config.KEY_BINDINGS.items():
            if action in keymap_presets._typing_contexts():
                keys = value["keys"] if isinstance(value, dict) else value
                self.assertFalse([k for k in keys if keymap_presets.is_typing_key(k)],
                                 action)
        # A key that is not a letter stays: ';' is still the filter.
        self.assertEqual(_keys(config, "filter"), [";"])

    def test_a_viewer_keeps_its_letters(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        self.assertEqual(_keys(config, "toggle_wrap"), TEMPLATE["toggle_wrap"])

    def test_what_the_user_rebound_stays_theirs(self):
        config = _config_with(copy_files=["Ctrl-K"], view_file=["V", "Q"])
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        self.assertEqual(config.KEY_BINDINGS["copy_files"], ["Ctrl-K"])
        # Rebound, so not freed either: the user's letters are the user's.
        self.assertEqual(config.KEY_BINDINGS["view_file"], ["V", "Q"])

    def test_switching_back_and_forth_does_not_compound(self):
        config = _config_with()
        original = copy.deepcopy(config.KEY_BINDINGS)
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        self.assertEqual(_keys(config, "copy_files"), ["F5"])
        keymap_presets.apply(config, keymap_presets.DEFAULT, TEMPLATE)
        self.assertEqual(config.KEY_BINDINGS, original)
        self.assertFalse(keymap_presets.type_ahead(config))

    def test_no_two_actions_share_a_key_in_the_file_list(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX, TEMPLATE)
        filer = keymap_presets._typing_contexts()
        seen = {}
        for action, value in config.KEY_BINDINGS.items():
            if action not in filer:
                continue
            keys = value["keys"] if isinstance(value, dict) else value
            sel = value.get("selection", "any") if isinstance(value, dict) else "any"
            for k in keys:
                seen.setdefault((k, sel), []).append(action)
        clashes = {k: v for k, v in seen.items() if len(v) > 1}
        self.assertEqual(clashes, {})

    def test_typing_keys(self):
        for k in ("K", "k", "7", "Shift-K"):
            self.assertTrue(keymap_presets.is_typing_key(k), k)
        for k in ("F5", "Ctrl-K", ";", "Shift-F6", "DELETE", "+"):
            self.assertFalse(keymap_presets.is_typing_key(k), k)

    def test_resolve(self):
        config = types.SimpleNamespace(KEY_PRESET=None)
        self.assertEqual(keymap_presets.resolve(config, None), "afx")
        self.assertEqual(keymap_presets.resolve(config, "orthodox"), "orthodox")
        config.KEY_PRESET = "afx"
        self.assertEqual(keymap_presets.resolve(config, "orthodox"), "afx")
        config.KEY_PRESET = "nonsense"
        self.assertEqual(keymap_presets.resolve(config, None), "afx")

    def test_default_is_the_old_name_of_afx(self):
        config = types.SimpleNamespace(KEY_PRESET="default")
        self.assertEqual(keymap_presets.resolve(config, "orthodox"), "afx")
        config.KEY_PRESET = None
        self.assertEqual(keymap_presets.resolve(config, "default"), "afx",
                         "a menu choice saved under the old name")
        self.assertIsNone(keymap_presets.get("default"))
        self.assertEqual(keymap_presets.LABELS["afx"], "AFX style (letters)")


def _key(key, char=None, mods=()):
    return Event(type=EventType.KEY, key=key, char=char, modifiers=frozenset(mods))


class InTheApp(unittest.TestCase):

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        for name in ("alpha.txt", "beta.txt", "report.txt"):
            with open(os.path.join(self.tmp, name), "w") as fh:
                fh.write("x")
        self.state_dir = tempfile.mkdtemp()
        self.db = os.path.join(self.state_dir, "state.db")
        self.app = self._open()

    def _open(self):
        from puikit.backends import create_backend
        self.b = create_backend("memory")
        self.b.open()
        app = xefm_app.XeFMApp(self.b, self.tmp, self.tmp,
                               left_provided=True, right_provided=True,
                               state_manager=XeFMStateManager(db_path=self.db))
        app.file_monitor.stop_monitoring()
        app.file_monitor.enabled = False
        app._settle_listings()
        app.panel.render()
        return app

    def tearDown(self):
        # Leave the shared config as it was found for the next test file.
        self.app.set_keymap_preset("afx")
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state_dir, ignore_errors=True)

    def _action(self, event):
        return self.app.keys.find_action_for_event(event, False, "filer")

    def test_switching_relabels_the_keymap_at_once(self):
        self.assertEqual(self._action(_key("v", "v")), "view_file")
        self.app.set_keymap_preset("orthodox")
        self.assertEqual(self._action(_key("f5")), "copy_files")
        self.assertEqual(self._action(_key("f8")), "delete_files")
        self.assertEqual(self._action(_key("f3")), "view_file")
        self.assertIsNone(self._action(_key("v", "v")))
        self.assertIn("Orthodox", self.app.log.lines[-1][0])

    def test_a_typed_letter_starts_a_search_with_it(self):
        self.app.set_keymap_preset("orthodox")
        self.app.on_event(_key("r", "r"))
        self.assertTrue(self.app._isearch_active)
        self.assertEqual(self.app._isearch_bar.pattern, "r")
        pane = self.app.active_pane()
        self.assertEqual(pane["files"][pane["focused_index"]].name, "report.txt")

    # --- quick search: the classic behaviour (Total Commander's) ------------

    def _focused(self):
        pane = self.app.active_pane()
        return pane["files"][pane["focused_index"]].name

    def _quick(self, text):
        self.app.set_keymap_preset("orthodox")
        for ch in text:
            self.app.on_event(_key(ch, ch))

    def test_quick_search_matches_the_start_of_the_name(self):
        # "a" is in alpha and beta; only alpha *starts* with it.
        self._quick("a")
        self.assertEqual(self.app._isearch_bar.prompt, "Quick search:")
        self.assertEqual(self.app._isearch_matches,
                         [i for i, f in enumerate(self.app.active_pane()["files"])
                          if f.name == "alpha.txt"])

    def test_quick_search_anywhere_when_configured(self):
        self.app.config.QUICK_SEARCH_MATCH = "anywhere"
        try:
            self._quick("a")
            names = {self.app.active_pane()["files"][i].name
                     for i in self.app._isearch_matches}
            self.assertEqual(names, {"alpha.txt", "beta.txt"})
        finally:
            self.app.config.QUICK_SEARCH_MATCH = "start"

    def test_esc_closes_and_keeps_the_cursor_on_the_match(self):
        self._quick("r")
        self.app.on_event(_key("escape"))
        self.assertFalse(self.app._isearch_active)
        self.assertEqual(self._focused(), "report.txt")

    def test_another_key_closes_the_search_and_acts(self):
        self._quick("r")
        ran = []
        with patch.object(self.app, "dispatch",
                          lambda action: ran.append(action) or True):
            self.app.on_event(_key("f5"))
        self.assertFalse(self.app._isearch_active)
        self.assertEqual(ran, ["copy_files"])
        self.assertEqual(self._focused(), "report.txt")

    def test_enter_opens_the_match(self):
        os.mkdir(os.path.join(self.tmp, "reports"))
        self.app._relist(self.app.active_pane())
        self.app._settle_listings()
        self._quick("reports")
        self.app.on_event(_key("enter"))
        self.app._settle_listings()
        self.assertFalse(self.app._isearch_active)
        self.assertEqual(str(self.app.active_pane()["path"]),
                         os.path.join(self.tmp, "reports"))

    def test_backspace_still_edits(self):
        self._quick("re")
        self.app.on_event(_key("backspace"))
        self.assertTrue(self.app._isearch_active)
        self.assertEqual(self.app._isearch_bar.pattern, "r")

    def test_the_status_bar_says_other_keys_act(self):
        self._quick("r")
        self.assertIn("other keys act on the file", self.app.status._text())

    def test_the_isearch_key_keeps_its_own_behaviour(self):
        self.app.set_keymap_preset("orthodox")
        self.app.enter_isearch()
        self.assertEqual(self.app._isearch_bar.prompt, "I-Search:")
        self.app.on_event(_key("a", "a"))
        names = {self.app.active_pane()["files"][i].name
                 for i in self.app._isearch_matches}
        self.assertEqual(names, {"alpha.txt", "beta.txt"}, "contains, as before")

    def test_the_default_keymap_has_no_type_ahead(self):
        self.app.on_event(_key("z", "z"))
        self.assertFalse(self.app._isearch_active)

    def test_the_choice_is_remembered(self):
        self.app.set_keymap_preset("orthodox")
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        self.app = self._open()
        self.assertEqual(self.app._keymap_preset, "orthodox")
        self.assertEqual(self._action(_key("f5")), "copy_files")

    def test_key_preset_in_config_wins(self):
        self.app.config.KEY_PRESET = "default"
        try:
            self.app.set_keymap_preset("orthodox")
            self.assertEqual(self.app._keymap_preset, "afx")
            self.assertIn("KEY_PRESET", self.app.log.lines[-1][0])
        finally:
            self.app.config.KEY_PRESET = None


if __name__ == "__main__":
    unittest.main()
