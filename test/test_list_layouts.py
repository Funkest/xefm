"""Attributes and file list layouts (#633, #756).

The attribute layer (``xefm.attributes``): what ``ATTRIBUTES`` accepts, how a
pane's store computes values off the UI thread and keeps them across a re-read,
and the on-request ``total_size``. The display layer (``xefm.layouts``): what
``LAYOUTS`` and ``LAYOUT_RULES`` accept, the built-in formats, and a pane drawn
with a layout of its own. And where they meet the rest: an attribute sort over
one directory, ``EntryInfo.attr``, and the config loader.

Run with: python -m pytest test/test_list_layouts.py -v
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from puikit import Panel  # noqa: E402
from puikit.backends.memory_backend import MemoryBackend  # noqa: E402

from xefm import attributes, layouts  # noqa: E402
from xefm.file_list_manager import FileListManager  # noqa: E402
from xefm.file_pane import FilePane  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.user_api import Cell, EntryInfo, load_user_entries  # noqa: E402


class _Config:
    SHOW_HIDDEN_FILES = True
    DATE_FORMAT = "short"
    SEPARATE_EXTENSIONS = True
    MAX_EXTENSION_LENGTH = 5
    DEFAULT_SORT_MODE = "filename"


def _load(**tables):
    config = types.SimpleNamespace(**tables)
    return load_user_entries(config)


class _Clean(unittest.TestCase):
    def tearDown(self):
        load_user_entries(types.SimpleNamespace())


class _Tree(_Clean):
    """A small real directory, listed the way a pane lists it."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        for name in ("a.txt", "b.md", "c.py"):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write("x" * 10)
        os.mkdir(os.path.join(self.tmp, "sub"))
        with open(os.path.join(self.tmp, "sub", "inner.bin"), "wb") as f:
            f.write(b"\0" * 1000)
        self.flm = FileListManager(_Config())

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pane(self, **extra):
        pane = {"path": Path(self.tmp), "focused_index": 0, "selected_files": set(),
                "filter_pattern": "", "sort_mode": "filename", "sort_reverse": False,
                "layout": None}
        pane.update(extra)
        self.flm.apply_listing(pane, self.flm.compute_listing(Path(self.tmp)))
        return pane

    @staticmethod
    def records(pane):
        return {str(p): a for p, a in pane["_listing_entries"]}

    def render(self, pane, width=60):
        backend = MemoryBackend(width=width, height=8)
        panel = Panel(backend)
        view = FilePane(pane, config=_Config())
        view.active = True
        panel.add(view, x=0, y=0, w=width, h=8, hints={"surface": "content"})
        panel.render()
        for wid in list(panel._text_anims):
            panel._text_anims[wid] -= 99.0
        panel.render()
        return ["".join(row) for row in backend.snapshot()]


def _wait(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --- the tables -------------------------------------------------------------------

class AttributesTable(_Clean):

    def test_a_good_entry_registers(self):
        loaded = _load(ATTRIBUTES={"lines": {"type": "count",
                                             "read": lambda d, es: [1] * len(es)}})
        self.assertEqual(loaded.warnings, [])
        self.assertEqual(loaded.attributes, 1)
        self.assertEqual(attributes.get("lines").label, "lines")

    def test_problems_are_named(self):
        cases = {
            "noread": {"type": "text"},
            "oldkey": {"entry": lambda e: 1},
            "badtype": {"type": "colour", "read": lambda d, es: []},
            "arity": {"read": lambda es: []},
            "badwhen": {"compute": "later", "read": lambda d, es: []},
        }
        loaded = _load(ATTRIBUTES=cases)
        self.assertEqual(loaded.attributes, 0)
        self.assertEqual(len(loaded.warnings), len(cases))
        self.assertIsNone(attributes.get("noread"))

    def test_a_built_in_cannot_be_replaced(self):
        loaded = _load(ATTRIBUTES={"size": {"read": lambda d, es: []}})
        self.assertIn("built-in", loaded.warnings[0])


class LayoutsTable(_Clean):

    def test_a_good_layout_registers_and_needs_a_name_column(self):
        loaded = _load(LAYOUTS={"slim": {"columns": ["name", "size"]},
                                "noname": {"columns": ["size"]}})
        self.assertEqual(loaded.layouts, 1)
        self.assertIn("no 'name' column", loaded.warnings[0])
        self.assertEqual([c.attr for c in layouts.get("slim").columns], ["name", "size"])

    def test_a_format_must_suit_its_type(self):
        loaded = _load(LAYOUTS={"x": {"columns": ["name", {"attr": "size", "format": "relative"}]}})
        self.assertIn("not a format for a size value", loaded.warnings[0])

    def test_default_is_replaced_only_on_purpose(self):
        loaded = _load(LAYOUTS={"default": {"columns": ["name"]}})
        self.assertIn("'override': True", loaded.warnings[0])
        self.assertEqual(layouts.get("default"), layouts.BUILTIN_DEFAULT)
        _load(LAYOUTS={"default": {"columns": ["name"], "override": True}})
        self.assertEqual([c.attr for c in layouts.get("default").columns], ["name"])

    def test_an_unknown_attribute_is_reported_but_the_layout_loads(self):
        loaded = _load(LAYOUTS={"g": {"columns": ["name", "git"]}})
        self.assertEqual(loaded.layouts, 1)
        self.assertIn("git", loaded.warnings[0])

    def test_markers_take_side_and_max_width(self):
        _load(LAYOUTS={"m": {"columns": [{"attr": "name", "markers": [
            "tags", {"attr": "size", "side": "before", "max_width": 2}]}]}})
        (name,) = layouts.get("m").columns
        self.assertEqual([(m.attr, m.side, m.max_width) for m in name.markers],
                         [("tags", "after", 3), ("size", "before", 2)])
        loaded = _load(LAYOUTS={"m": {"columns": [{"attr": "name", "markers": [
            {"attr": "tags", "side": "under"}]}]}})
        self.assertIn("side", loaded.warnings[0])


class Rules(_Clean):

    def test_first_match_wins_and_a_broken_rule_is_skipped(self):
        def boom(path):
            raise RuntimeError("no")

        _load(LAYOUTS={"a": {"columns": ["name"]}, "b": {"columns": ["name"]}},
              LAYOUT_RULES=[(boom, "a"), ("/data/*", "a"),
                            (lambda p: str(p).startswith("/data"), "b")])
        self.assertEqual(layouts.resolve("/data/x"), "a")
        self.assertIsNone(layouts.resolve("/elsewhere"))

    def test_a_rule_for_a_layout_nobody_defined_is_dropped(self):
        loaded = _load(LAYOUT_RULES=[("*", "nowhere")])
        self.assertIn("nowhere", loaded.warnings[0])
        self.assertIsNone(layouts.resolve("/x"))

    def test_hand_beats_rule_beats_default(self):
        _load(LAYOUTS={"a": {"columns": ["name"]}, "b": {"columns": ["name"]}})
        self.assertEqual(layouts.effective({}).name, "default")
        self.assertEqual(layouts.effective({"_layout_auto": "a"}).name, "a")
        self.assertEqual(layouts.effective({"_layout_auto": "a", "layout": "b"}).name, "b")
        self.assertEqual(layouts.effective({"layout": "gone"}).name, "default")


# --- formats -----------------------------------------------------------------------

class Formats(unittest.TestCase):

    def render(self, kind, fmt, value, **row):
        attr = attributes.Attribute("x", "X", kind, values=row.pop("values", {}))
        resolved = layouts.resolve_format(fmt, attr)
        return layouts.render(resolved, value, layouts.Row(attr=attr, **row), lambda: None)

    def test_sizes(self):
        self.assertEqual(self.render("size", "bytes", 1234567)[0].text, "1,234,567")
        self.assertEqual(self.render("size", None, None, is_dir=True)[0].text, "<DIR>")
        self.assertEqual(self.render("size", None, None, ok=False)[0].text, "---")

    def test_relative_time(self):
        now = time.time()
        self.assertEqual(self.render("time", "relative", now - 5)[0].text, "just now")
        self.assertEqual(self.render("time", "relative", now - 3 * 86400)[0].text,
                         "3 days ago")

    def test_recent_time_is_as_short_as_its_age_allows(self):
        from datetime import datetime
        now = datetime.now()
        self.assertEqual(self.render("time", "recent", now.timestamp())[0].text,
                         now.strftime("%H:%M"))
        old = datetime(2019, 3, 4, 5, 6).timestamp()
        self.assertEqual(self.render("time", "recent", old)[0].text, "2019")

    def test_enum_values_give_letter_and_word_their_color(self):
        values = {"M": {"label": "Modified", "color": "yellow"}}
        (cell,) = self.render("enum", "word", "M", values=values)
        self.assertEqual((cell.text, cell.color), ("Modified", "yellow"))
        self.assertEqual(self.render("enum", "letter", "M", values=values)[0].text, "M")

    def test_a_user_format_may_return_text_a_cell_or_cells(self):
        attr = attributes.Attribute("x", "X", "text")
        for out, expect in (("hi", ["hi"]), (Cell("a", color="red"), ["a"]),
                            ([Cell("a"), "b"], ["a", "b"]), (None, [])):
            resolved = layouts.resolve_format(lambda v, e, out=out: out, attr)
            cells = layouts.render(resolved, 1, layouts.Row(), lambda: None)
            self.assertEqual([c.text for c in cells], expect)

    def test_a_failing_user_format_draws_nothing(self):
        def broken(value, entry):
            raise ValueError("no")
        resolved = layouts.resolve_format(broken, attributes.Attribute("x", "X"))
        self.assertEqual(layouts.render(resolved, 1, layouts.Row(), lambda: None), [])


# --- the store ---------------------------------------------------------------------

class Store(_Tree):

    def test_an_automatic_attribute_is_read_once_for_the_whole_folder(self):
        calls = []

        def upper(directory, entries):
            calls.append((str(directory), len(entries)))
            return [e.name.upper() for e in entries]

        _load(ATTRIBUTES={"up": {"read": upper}})
        pane = self.pane()
        store = attributes.store_of(pane)
        files, records = pane["files"], self.records(pane)
        store.sync(files, records, pane["path"], {"up"})
        self.assertTrue(_wait(lambda: store.ready("up", files, records)))
        self.assertEqual(calls, [(self.tmp, len(files))])
        a = next(p for p in files if p.name == "a.txt")
        self.assertEqual(store.get(a, records[str(a)], "up"), "A.TXT")

    def test_a_re_read_asks_again_for_the_whole_folder(self):
        """A Git status changes without the file it is about changing, so a
        re-read cannot keep the values of the rows that look the same."""
        calls = []

        def names(directory, entries):
            calls.append(len(entries))
            return [e.name for e in entries]

        _load(ATTRIBUTES={"n": {"read": names}})
        pane = self.pane()
        store = attributes.store_of(pane)
        store.sync(pane["files"], self.records(pane), pane["path"], {"n"})
        self.assertTrue(_wait(lambda: len(calls) == 1))
        self.flm.apply_listing(pane, self.flm.compute_listing(Path(self.tmp)))
        store.sync(pane["files"], self.records(pane), pane["path"], {"n"})
        self.assertTrue(_wait(lambda: len(calls) == 2))
        self.assertEqual(calls, [len(pane["files"])] * 2)

    def test_a_provider_answering_the_wrong_count_costs_its_values(self):
        _load(ATTRIBUTES={"bad": {"read": lambda d, es: ["x"]}})
        pane = self.pane()
        store = attributes.store_of(pane)
        files, records = pane["files"], self.records(pane)
        store.sync(files, records, pane["path"], {"bad"})
        self.assertTrue(_wait(lambda: store.ready("bad", files, records)))
        self.assertEqual({store.get(p, records[str(p)], "bad") for p in files}, {None})

    def test_an_on_request_attribute_is_read_one_entry_at_a_time(self):
        calls = []

        def size_of(directory, entries):
            calls.append([e.name for e in entries])
            return [e.size for e in entries]

        _load(ATTRIBUTES={"sz": {"type": "size", "compute": "on_request", "read": size_of}})
        pane = self.pane()
        store = attributes.store_of(pane)
        records = self.records(pane)
        targets = [p for p in pane["files"] if p.name in ("a.txt", "b.md")]
        done = threading.Event()
        store.request("sz", targets, records, on_done=lambda n, c: done.set())
        self.assertTrue(done.wait(3))
        self.assertEqual(calls, [["a.txt"], ["b.md"]])
        self.assertEqual(store.get(targets[0], records[str(targets[0])], "sz"), 10)

    def test_another_directory_starts_afresh(self):
        _load(ATTRIBUTES={"n": {"read": lambda d, es: [e.name for e in es]}})
        pane = self.pane()
        store = attributes.store_of(pane)
        store.sync(pane["files"], self.records(pane), pane["path"], {"n"})
        self.assertTrue(_wait(lambda: store.ready("n", pane["files"], self.records(pane))))
        store.sync([], {}, "/elsewhere", {"n"})
        self.assertEqual(store.value(str(pane["files"][0]), "n"), (False, None))

    def test_total_size_is_computed_only_on_request(self):
        pane = self.pane()
        store = attributes.store_of(pane)
        records = self.records(pane)
        sub = next(p for p in pane["files"] if p.name == "sub")
        self.assertIsNone(store.get(sub, records[str(sub)], "total_size"))
        a = next(p for p in pane["files"] if p.name == "a.txt")
        self.assertEqual(store.get(a, records[str(a)], "total_size"), 10)
        done = threading.Event()
        store.request("total_size", [sub], records, on_done=lambda n, c: done.set())
        self.assertTrue(done.wait(3))
        self.assertEqual(store.get(sub, records[str(sub)], "total_size"), 1000)
        self.assertEqual(EntryInfo(sub, is_dir=True).attr("total_size"), 1000)

    def test_entry_attr_never_computes(self):
        _load(ATTRIBUTES={"n": {"read": lambda d, es: ["computed"] * len(es)}})
        self.assertIsNone(EntryInfo(Path(self.tmp) / "a.txt").attr("n"))
        self.assertEqual(EntryInfo(Path(self.tmp) / "a.txt").attr("ext"), ".txt")


# --- drawing -----------------------------------------------------------------------

class Drawing(_Tree):

    def test_a_layout_of_its_own(self):
        _load(ATTRIBUTES={"kind": {"type": "enum", "read": lambda d, es: ["F"] * len(es),
                                   "values": {"F": {"label": "File"}}}},
              LAYOUTS={"mine": {"columns": [
                  {"attr": "name", "markers": [{"attr": "kind", "side": "before",
                                                "max_width": 1}]},
                  {"attr": "kind", "format": "word"},
                  {"attr": "size", "format": "bytes", "width": 6}]}})
        pane = self.pane(layout="mine")
        lines = self.render(pane)
        store = attributes.store_of(pane)
        self.assertTrue(_wait(lambda: store.ready("kind", pane["files"], self.records(pane))))
        lines = self.render(pane)
        row = next(line for line in lines if "a.txt" in line)
        self.assertIn("F a.txt", row)          # the marker, before the name
        self.assertIn("File", row)             # the enum's word
        self.assertTrue(row.rstrip().endswith("10"))
        self.assertNotIn(".txt ", row.replace("a.txt", ""))   # no ext column

    def test_a_one_cell_marker_survives_a_glyph_wider_than_one_cell(self):
        """A proportional ● measures a little over a cell on a GUI; elided to
        fit, it vanished and left only its space (hand check, 2026-10-28)."""
        view = FilePane({"files": []}, config=_Config())
        marker = layouts.Marker("x", side="before", max_width=1)
        resolved = layouts.resolve_format(lambda v, e: Cell("●", color="yellow"),
                                          attributes.Attribute("x", "X"))
        wide = lambda s: 1.15 * len(s)   # noqa: E731
        (group,) = view._marker_groups([(marker, None, resolved)], "before",
                                       lambda n: "M", lambda a: layouts.Row(),
                                       lambda: None, wide)
        self.assertEqual([c.text for c in group[0]], ["●"])
        dots = layouts.Marker("tags", max_width=3)
        three = layouts.resolve_format(lambda v, e: [Cell("●")] * 5,
                                       attributes.Attribute("tags", "T"))
        (group,) = view._marker_groups([(dots, None, three)], "after",
                                       lambda n: 1, lambda a: layouts.Row(),
                                       lambda: None, wide)
        self.assertEqual(len(group[0]), 3)   # by count, as the tag dots were

    def test_a_column_with_a_priority_goes_first_on_a_narrow_pane(self):
        _load(LAYOUTS={"two": {"columns": ["name", {"attr": "mtime", "priority": 1},
                                           "size"]}})
        pane = self.pane(layout="two")
        wide = next(line for line in self.render(pane, 60) if "a.txt" in line)
        narrow = next(line for line in self.render(pane, 26) if "a" in line[:3])
        self.assertRegex(wide, r"\d\d-\d\d-\d\d")
        self.assertNotRegex(narrow, r"\d\d-\d\d-\d\d")
        self.assertIn("10B", narrow)


# --- sorting -----------------------------------------------------------------------

class AttributeSort(_Tree):

    def test_rows_with_a_value_come_in_its_order_the_rest_last(self):
        pane = self.pane()
        entries = pane["_listing_entries"]
        by_name = {p.name: str(p) for p, _a in entries}
        values = {by_name["a.txt"]: 3, by_name["b.md"]: 1, by_name["sub"]: 9}
        for reverse, expect in ((False, ["sub", "b.md", "a.txt", "c.py"]),
                                (True, ["sub", "a.txt", "b.md", "c.py"])):
            result = self.flm.recompute_from_snapshot(
                entries, overlay=("x", values, reverse))
            self.assertEqual([p.name for p in result["files"]], expect)


# --- the app -----------------------------------------------------------------------

class App(_Tree):
    """The per-tab choice, folder sizes, and the one-folder attribute sort, run
    through the app as a key would run them."""

    def setUp(self):
        super().setUp()
        from puikit.backends import create_backend
        from xefm import app as xefm_app
        from xefm.state_manager import XeFMStateManager
        self.state_dir = tempfile.mkdtemp()
        sm = XeFMStateManager(db_path=os.path.join(self.state_dir, "state.db"))
        self.b = create_backend("memory")
        self.b.open()
        self.app = xefm_app.XeFMApp(self.b, self.tmp, self.tmp, left_provided=True,
                                    right_provided=True, state_manager=sm)
        self.app.file_monitor.stop_monitoring()
        self.app.file_monitor.enabled = False
        self.app._settle_listings()

    def tearDown(self):
        try:
            self.b.close()
        except Exception:
            pass
        shutil.rmtree(self.state_dir, ignore_errors=True)
        super().tearDown()

    def focus(self, name):
        pane = self.app.active_pane()
        pane["focused_index"] = [f.name for f in pane["files"]].index(name)

    def test_the_layout_is_the_tab_s_and_rules_pick_it_on_automatic(self):
        _load(LAYOUTS={"slim": {"columns": ["name", "size"]}},
              LAYOUT_RULES=[(self.tmp, "slim")])
        pane = self.app.active_pane()
        self.app._relist(pane)
        self.app._settle_listings()
        self.assertEqual(layouts.effective(pane).name, "slim")
        self.app._set_layout(pane, "default")
        self.assertEqual(layouts.effective(pane).name, "default")
        self.app._set_layout(pane, None)
        self.assertEqual(layouts.effective(pane).name, "slim")

    def test_folder_sizes_then_a_sort_by_them_for_this_folder_only(self):
        with open(os.path.join(self.tmp, "big"), "wb") as f:
            f.write(b"\0" * 5)
        os.mkdir(os.path.join(self.tmp, "empty"))
        pane = self.app.active_pane()
        self.app._relist(pane)
        self.app._settle_listings()
        self.focus("a.txt")                       # on a file: every folder
        self.app.dispatch("calculate_folder_sizes")
        store = attributes.store_of(pane)
        records = self.records(pane)
        sub = next(p for p in pane["files"] if p.name == "sub")
        self.assertTrue(_wait(lambda: store.value(str(sub), "total_size")[0]))
        self.assertTrue(_wait(lambda: not store.busy()))

        pane["sort_overlay"] = {"attr": "total_size", "reverse": True,
                                "path": str(pane["path"])}
        self.app._resort(pane)
        self.app._settle_listings()
        self.assertEqual([p.name for p in pane["files"]][:2], ["sub", "empty"])
        self.assertIn("(this folder)", self.app.flm.get_sort_description(pane))
        names = [p.name for p in pane["files"] if not records.get(str(p), {}).get("is_dir")]
        self.assertEqual(names, ["a.txt", "b.md", "c.py", "big"])   # ties keep name order
        pane["path"] = Path(os.path.join(self.tmp, "sub"))
        self.assertIsNone(self.app._sort_overlay(pane))
        self.assertIsNone(pane["sort_overlay"])


if __name__ == "__main__":
    unittest.main()
