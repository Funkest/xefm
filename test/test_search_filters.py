"""Search filter chips (#609): kind, modified date and size, in every mode of
the search dialog, and choice options in the option model behind them.

Run with: python -m pytest test/test_search_filters.py -v
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from puikit import Event, EventType  # noqa: E402

from xefm import search_filters as sf  # noqa: E402
from xefm.options import OptionSet  # noqa: E402


class Model(unittest.TestCase):

    def test_kind_by_extension(self):
        self.assertEqual(sf.kind_of("a.JPG", False), sf.IMAGE)
        self.assertEqual(sf.kind_of("a.mkv", False), sf.VIDEO)
        self.assertEqual(sf.kind_of("x", True), sf.FOLDER)
        self.assertIsNone(sf.kind_of("a.py", False))

    def test_predicate_ands_the_chips(self):
        now = time.time()
        keep = sf.predicate({sf.KIND: sf.IMAGE, sf.MODIFIED: sf.WEEK,
                             sf.SIZE: "1mb"}, now)
        big_new = {"is_dir": False, "size": 2 << 20, "mtime": now - 3600}
        self.assertTrue(keep("a.png", big_new))
        self.assertFalse(keep("a.txt", big_new))
        self.assertFalse(keep("a.png", dict(big_new, size=10)))
        self.assertFalse(keep("a.png", dict(big_new, mtime=now - 30 * 86400)))
        self.assertIsNone(sf.predicate({sf.KIND: sf.ANY}))

    def test_a_size_condition_admits_files_only(self):
        keep = sf.predicate({sf.SIZE: "1mb"})
        self.assertFalse(keep("dir", {"is_dir": True, "size": 1 << 30, "mtime": 0}))

    def test_today_starts_at_midnight(self):
        from datetime import datetime
        now = datetime(2026, 10, 14, 15, 30).timestamp()
        self.assertEqual(sf.since(sf.TODAY, now), datetime(2026, 10, 14).timestamp())
        self.assertEqual(sf.since(sf.YEAR, now), datetime(2026, 1, 1).timestamp())

    def test_describe(self):
        self.assertEqual(sf.describe({sf.KIND: sf.IMAGE, sf.MODIFIED: sf.WEEK}),
                         "Images · Past 7 days")
        self.assertEqual(sf.describe({}), "")

    def test_index_query_from_the_chips_alone(self):
        q = sf.index_query("Spotlight", {sf.KIND: sf.IMAGE, sf.SIZE: "1gb"})
        self.assertIn('kMDItemContentTypeTree == "public.image"', q)
        self.assertIn(f"kMDItemFSSize >= {1 << 30}", q)
        w = sf.index_query("Windows Search", {sf.KIND: sf.VIDEO})
        self.assertEqual(w, "where System.Kind = 'video'")
        self.assertEqual(sf.index_query("Spotlight", {}), "")


class ChoiceOptions(unittest.TestCase):

    def setUp(self):
        self.options = OptionSet(sf.SEARCH_FILTERS)

    def test_default_is_the_first_value(self):
        self.assertEqual(self.options[sf.KIND], sf.ANY)
        self.assertFalse(any(on for _o, on in self.options.chips()))

    def test_toggle_steps_through_the_values(self):
        self.assertEqual(self.options.toggle(sf.KIND), sf.FOLDER)
        self.assertEqual(self.options.toggle(sf.KIND, -1), sf.ANY)
        self.assertEqual(self.options.toggle(sf.KIND, -1), sf.ARCHIVE)

    def test_set_refuses_an_unknown_value(self):
        self.options.set(sf.KIND, "nonsense")
        self.assertEqual(self.options[sf.KIND], sf.ANY)

    def test_a_set_chip_reads_as_on(self):
        self.options.set(sf.SIZE, "1gb")
        on = dict((o.name, v) for o, v in self.options.chips())
        self.assertTrue(on[sf.SIZE])

    def test_they_reset_on_every_open(self):
        self.options.set(sf.KIND, sf.IMAGE)
        self.options.reset_transient()
        self.assertEqual(self.options[sf.KIND], sf.ANY)


def _key(name, char=None, mods=()):
    return Event(type=EventType.KEY, key=name, char=char, modifiers=frozenset(mods))


class InTheApp(unittest.TestCase):

    def setUp(self):
        from puikit.backends import create_backend
        from xefm import app as xefm_app
        from xefm.state_manager import XeFMStateManager
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.tmp, "sub"))
        for name in ("photo.png", "notes.txt", os.path.join("sub", "deep.jpg")):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write("hello")
        self.state = tempfile.mkdtemp()
        self.b = create_backend("memory")
        self.b.open()
        self.app = xefm_app.XeFMApp(
            self.b, self.tmp, self.tmp, left_provided=True, right_provided=True,
            state_manager=XeFMStateManager(db_path=os.path.join(self.state, "s.db")))
        self.app.file_monitor.stop_monitoring()
        self.app.file_monitor.enabled = False
        self.app._settle_listings()

    def tearDown(self):
        self.app.file_monitor.stop_monitoring()
        self.b.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.state, ignore_errors=True)

    def _dialog(self, mode="filename"):
        self.app._open_search(mode)
        return self.app.panel._layers[-1].widget

    def _wait(self, dialog):
        deadline = time.monotonic() + 5
        while dialog._searching and time.monotonic() < deadline:
            self.b.run_animation_ticks()
            time.sleep(0.01)
        self.b.run_animation_ticks()

    def test_the_chips_alone_search_filenames(self):
        dialog = self._dialog()
        self.app._search_options.set(sf.KIND, sf.IMAGE)
        self._wait(dialog)
        names = sorted(os.path.basename(str(p)) for p in dialog.results)
        self.assertEqual(names, ["deep.jpg", "photo.png"])

    def test_the_chips_narrow_content_search(self):
        dialog = self._dialog("content")
        self.app._search_options.set(sf.KIND, sf.DOCUMENT)
        dialog._use_query("hello")
        self._wait(dialog)
        self.assertEqual([os.path.basename(str(h["path"])) for h in dialog.results],
                         ["notes.txt"])

    def test_content_needs_words(self):
        dialog = self._dialog("content")
        self.app._search_options.set(sf.KIND, sf.DOCUMENT)
        self.assertEqual(dialog._status_text(), "Type to search")

    def test_tab_steps_through_every_mode(self):
        dialog = self._dialog()
        seen = [dialog.mode]
        for _ in range(len(dialog.modes)):
            dialog.handle_event(_key("tab"))
            seen.append(dialog.mode)
        self.assertEqual(seen[0], seen[-1])
        self.assertEqual(set(seen), set(dialog.modes))

    def _popup(self):
        from xefm.candidate_list import CandidateListOverlay
        return [slot for slot in self.app.panel._layers
                if isinstance(slot.widget, CandidateListOverlay)]

    def _click_chip(self, dialog, name):
        rect = next(r for n, r in dialog._chip_hits if n == name)
        dialog.handle_event(Event(type=EventType.MOUSE_CLICK, button="left",
                                  x=rect.x + 0.5, y=rect.y))

    def test_a_choice_chip_opens_its_values_in_the_completion_popup(self):
        """#609: the completion popup, above the dialog and taking no events
        of its own — the dialog drives it."""
        dialog = self._dialog()
        self.app.panel.render()
        self._click_chip(dialog, sf.KIND)
        slots = self._popup()
        self.assertEqual(len(slots), 1)
        self.assertGreater(slots[0].z, self.app.panel._layers[0].z)
        self.assertFalse(slots[0].interactive)
        popup = slots[0].widget
        self.assertIn("Images", popup.candidates)
        self.assertEqual(popup.focused_index, 0, "the current value")
        for _ in range(popup.candidates.index("Images")):
            dialog.handle_event(_key("down"))
        dialog.handle_event(_key("enter"))
        self.assertEqual(self.app._search_options[sf.KIND], sf.IMAGE)
        self.assertEqual(self._popup(), [])

    def test_clicking_the_chip_again_closes_it_without_stacking(self):
        dialog = self._dialog()
        self.app.panel.render()
        self._click_chip(dialog, sf.KIND)
        self.app.panel.render()
        self._click_chip(dialog, sf.KIND)
        self.assertEqual(self._popup(), [])
        self._click_chip(dialog, sf.KIND)
        self.app.panel.render()
        self._click_chip(dialog, sf.SIZE)
        self.assertEqual(len(self._popup()), 1, "one popup at a time")
        dialog.handle_event(_key("escape"))
        self.assertEqual(self._popup(), [])
        self.assertIs(self.app.panel._layers[-1].widget, dialog, "Esc closed the popup only")

    def test_a_click_on_a_value_picks_it(self):
        dialog = self._dialog()
        self.app.panel.render()
        self._click_chip(dialog, sf.SIZE)
        self.app.panel.render()
        slot = self._popup()[0]
        ox, oy = dialog._screen_origin
        row = slot.widget.candidates.index("1 GB or more")
        dialog.handle_event(Event(type=EventType.MOUSE_CLICK, button="left",
                                  x=slot.rect.x + 1 - ox,
                                  y=slot.rect.y + row * slot.widget._row_h - oy))
        self.assertEqual(self.app._search_options[sf.SIZE], "1gb")

    def test_history_hangs_from_the_field(self):
        key = self.app._SEARCH_HISTORY["filename"]
        self.app._record_history(key, "*.txt")
        self.app._record_history(key, "*.png")
        dialog = self._dialog()
        self.app.panel.render()
        dialog.handle_event(_key("down", mods=("alt",)))
        popup = self._popup()[0].widget
        self.assertEqual(popup.candidates, ["*.png", "*.txt"])
        dialog.handle_event(_key("enter"))
        self.assertEqual(dialog.query_edit.text, "*.png")
        self.assertEqual(self._popup(), [])

    def test_the_remove_key_forgets_a_recent_query(self):
        key = self.app._SEARCH_HISTORY["filename"]
        self.app._record_history(key, "*.txt")
        self.app._record_history(key, "*.png")
        dialog = self._dialog()
        self.app.panel.render()
        dialog.handle_event(_key("down", mods=("alt",)))
        dialog.handle_event(_key("delete", mods=("shift",)))
        self.assertEqual(self.app._query_history(key), ["*.txt"])
        self.assertEqual(self._popup()[0].widget.candidates, ["*.txt"])

    def test_typing_closes_the_history_and_types(self):
        self.app._record_history(self.app._SEARCH_HISTORY["filename"], "*.png")
        dialog = self._dialog()
        self.app.panel.render()
        dialog.handle_event(_key("down", mods=("alt",)))
        dialog.handle_event(_key("a", "a"))
        self.assertEqual(self._popup(), [])
        self.assertEqual(dialog.query_edit.text, "a")

    def test_accepting_records_the_query(self):
        dialog = self._dialog()
        dialog._use_query("*.png")
        self._wait(dialog)
        dialog.handle_event(_key("enter"))
        self.assertEqual(self.app._query_history(self.app._SEARCH_HISTORY["filename"]),
                         ["*.png"])


if __name__ == "__main__":
    unittest.main()
