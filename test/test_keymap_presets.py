"""Keymap presets (#565, #597): whole keymaps, chosen as one.

The pure half builds a preset's table, lays a ``config.py``'s
``KEY_BINDINGS`` over it, and checks what moved, what stayed the user's, and
what was freed. The app half switches presets, answers the first launch's
question, and presses keys on the memory backend.

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

from xefm import keymap_afx, keymap_presets  # noqa: E402
from xefm import app as xefm_app  # noqa: E402
from xefm import config as xefm_config  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402

AFX_TABLE = keymap_afx.bindings()


def _config_with(**overrides):
    """A config whose ``config.py`` binds ``overrides`` and nothing else."""
    return types.SimpleNamespace(KEY_BINDINGS=dict(overrides), KEY_PRESET=None)


def _keys(config, action):
    value = config.KEY_BINDINGS.get(action)
    return value["keys"] if isinstance(value, dict) else value


class Apply(unittest.TestCase):

    def test_afx_is_its_whole_table(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.AFX)
        self.assertEqual(config.KEY_BINDINGS, AFX_TABLE)
        self.assertFalse(keymap_presets.type_ahead(config))

    def test_orthodox_is_its_whole_table(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        self.assertEqual(_keys(config, "copy_files"), ["F5"])
        self.assertEqual(_keys(config, "delete_files"), ["F8", "DELETE"])
        self.assertEqual(_keys(config, "redraw"), [])
        self.assertTrue(keymap_presets.type_ahead(config))

    def test_a_preset_key_has_no_selection_gate(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        # AFX's copy_files is {'keys': ['C'], 'selection': 'required'}.
        self.assertEqual(config.KEY_BINDINGS["copy_files"], ["F5"])

    def test_bare_letters_leave_the_file_list(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        for action, value in config.KEY_BINDINGS.items():
            if action in keymap_presets._typing_contexts():
                keys = value["keys"] if isinstance(value, dict) else value
                self.assertFalse([k for k in keys if keymap_presets.is_typing_key(k)],
                                 action)
        # A key that is not a letter stays where the preset says nothing:
        # '.' still shows hidden files.
        self.assertEqual(_keys(config, "toggle_hidden"), AFX_TABLE["toggle_hidden"])

    def test_orthodox_follows_total_commander(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        expected = {
            "help": ["F1"], "reread": ["F2", "Ctrl-R"], "view_file": ["F3"],
            "edit_file": ["F4"], "copy_files": ["F5"], "move_files": ["F6"],
            "create_directory": ["F7"], "delete_files": ["F8", "DELETE"],
            "quit": ["Alt-F4"], "rename": ["Shift-F6", "Ctrl-M"],
            "duplicate_files": ["Shift-F5"], "compare_selection": ["Shift-F2"],
            "find_files": ["Alt-F7"], "create_archive": ["Alt-F5"],
            "history": ["Alt-DOWN"], "favorites": ["Ctrl-D"],
            "filter": ["Ctrl-S"], "go_parent": ["BACKSPACE", "Ctrl-PAGE_UP"],
            "select_all": ["Ctrl-A"], "quick_sort_date": ["Ctrl-F5"],
        }
        for action, keys in expected.items():
            self.assertEqual(_keys(config, action), keys, action)

    def test_actions_this_xefm_lacks_are_skipped(self):
        """The table may name actions of features not merged yet; where the
        running XeFM lacks one, its keys stay free."""
        from xefm.actions import FILER, registry
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        for action in keymap_presets._ORTHODOX.bindings:
            if registry.resolve(FILER, action) is None:
                self.assertNotIn(action, config.KEY_BINDINGS, action)

    def test_a_viewer_keeps_its_letters(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        self.assertEqual(_keys(config, "toggle_wrap"), AFX_TABLE["toggle_wrap"])

    def test_config_py_overrides_every_preset(self):
        for name in keymap_presets.PRESETS:
            config = _config_with(copy_files=["Ctrl-K"], view_file=["V", "Q"])
            keymap_presets.apply(config, name)
            self.assertEqual(config.KEY_BINDINGS["copy_files"], ["Ctrl-K"], name)
            # Not freed either: the user's letters are the user's.
            self.assertEqual(config.KEY_BINDINGS["view_file"], ["V", "Q"], name)

    def test_an_entry_equal_to_afx_still_overrides(self):
        """No "untouched" test any more: an entry is an entry, whatever it
        happens to equal."""
        config = _config_with(copy_files=AFX_TABLE["copy_files"])
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        self.assertEqual(config.KEY_BINDINGS["copy_files"], AFX_TABLE["copy_files"])

    def test_an_old_name_overrides_the_action_it_names(self):
        config = _config_with(rename_file=["Ctrl-K"])
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        self.assertNotIn("rename", config.KEY_BINDINGS)
        self.assertEqual(config.KEY_BINDINGS["rename_file"], ["Ctrl-K"])

    def test_replaced_names_what_config_py_changes(self):
        config = _config_with(copy_files=AFX_TABLE["copy_files"],
                              help=["F1"])
        self.assertEqual(keymap_presets.replaced(config, keymap_presets.AFX), [])
        self.assertEqual(keymap_presets.replaced(config, keymap_presets.ORTHODOX),
                         ["copy_files"])

    def test_switching_back_and_forth_does_not_compound(self):
        config = _config_with(quit=[])
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
        self.assertEqual(_keys(config, "copy_files"), ["F5"])
        keymap_presets.apply(config, keymap_presets.AFX)
        self.assertEqual(config.KEY_BINDINGS, dict(AFX_TABLE, quit=[]))
        self.assertFalse(keymap_presets.type_ahead(config))

    def test_no_two_actions_share_a_key_in_the_file_list(self):
        config = _config_with()
        keymap_presets.apply(config, keymap_presets.ORTHODOX)
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
        self.assertIsNone(keymap_presets.resolve(config, None), "nothing chosen")
        self.assertEqual(keymap_presets.resolve(config, "orthodox"), "orthodox")
        config.KEY_PRESET = "afx"
        self.assertEqual(keymap_presets.resolve(config, "orthodox"), "afx")
        config.KEY_PRESET = "nonsense"
        self.assertEqual(keymap_presets.resolve(config, "orthodox"), "orthodox")
        self.assertIsNone(keymap_presets.resolve(config, None))

    def test_default_is_the_old_name_of_afx(self):
        config = types.SimpleNamespace(KEY_PRESET="default")
        self.assertEqual(keymap_presets.resolve(config, "orthodox"), "afx")
        config.KEY_PRESET = None
        self.assertEqual(keymap_presets.resolve(config, "default"), "afx",
                         "a menu choice saved under the old name")
        self.assertEqual(keymap_presets.get("default").name, "afx")
        self.assertEqual(keymap_presets.LABELS["afx"], "AFX style (letters)")

    def test_the_shipped_key_bindings_holds_examples_only(self):
        from xefm import _config
        self.assertEqual(_config.Config.KEY_BINDINGS, {})


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

    def _open(self, created=False):
        from puikit.backends import create_backend
        self.b = create_backend("memory")
        self.b.open()
        # The shared config is the developer's ~/.xefm/config.py; its own
        # KEY_BINDINGS would be laid over every preset here. Test the presets
        # as a config.py binding nothing would see them.
        shared = xefm_config.get_config()
        if not hasattr(self, "_saved_base"):
            self._saved_base = getattr(shared, "_KEY_BINDINGS_BASE", None)
            self._saved_created = xefm_config.config_manager.created_config
        shared._KEY_BINDINGS_BASE = {}
        xefm_config.config_manager.created_config = created
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
        xefm_config.config_manager.created_config = self._saved_created
        self.app.config._KEY_BINDINGS_BASE = self._saved_base
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

    def test_quick_search_is_the_i_search_with_its_matching(self):
        self._quick("a")
        self.assertEqual(self.app._isearch_bar.prompt, "I-Search:")
        names = {self.app.active_pane()["files"][i].name
                 for i in self.app._isearch_matches}
        self.assertEqual(names, {"alpha.txt", "beta.txt"}, "contains, as I-Search")

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

    def test_the_isearch_key_keeps_its_own_closing(self):
        self.app.set_keymap_preset("orthodox")
        self.app.enter_isearch()
        self.app.on_event(_key("r", "r"))
        self.app.on_event(_key("f5"))
        self.assertTrue(self.app._isearch_active, "F5 does not end an I-Search")

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

    # --- the first launch (#597) ---------------------------------------------

    def _reopen(self, created=False):
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        os.remove(self.db)
        self.app = self._open(created=created)

    def test_an_install_from_before_presets_keeps_afx(self):
        """config.py was already there and no preset was ever chosen: the
        keymap it has been running, without a question."""
        self._reopen(created=False)
        self.assertEqual(self.app._keymap_preset, "afx")
        self.assertEqual(self.app.state_manager.get_state("keymap.preset"), "afx")

    def test_a_first_launch_asks(self):
        self._reopen(created=True)
        self.assertIsNone(self.app._keymap_preset)
        asked = []
        with patch.object(xefm_app, "show_message_box",
                          lambda *a, **k: asked.append(k)):
            self.app._ask_keymap_preset()
        self.assertEqual(asked[0]["buttons"],
                         ("AFX style (letters)", "Orthodox (function keys)", "Later"))
        asked[0]["on_result"]("Orthodox (function keys)")
        self.assertEqual(self.app._keymap_preset, "orthodox")
        self.assertEqual(self._action(_key("f5")), "copy_files")

    def test_later_asks_again_at_the_next_launch(self):
        self._reopen(created=True)
        # Next launch: config.py exists now, but the question is still open.
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        self.app = self._open(created=False)
        self.assertIsNone(self.app._keymap_preset)
        self.app.set_keymap_preset("afx")
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        self.app = self._open(created=False)
        self.assertEqual(self.app._keymap_preset, "afx")

    def test_switching_says_what_config_py_replaces(self):
        self.app.config._KEY_BINDINGS_BASE = {"copy_files": ["C"]}
        self.app.set_keymap_preset("orthodox")
        self.assertIn("replaces this keymap's keys for 1 action(s): copy_files",
                      self.app.log.lines[-1][0])
        self.assertEqual(self._action(_key("c", "c")), "copy_files")


if __name__ == "__main__":
    unittest.main()
