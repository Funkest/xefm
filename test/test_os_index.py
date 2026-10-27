"""Searching the OS index (#579): Spotlight and Windows Search.

The query builders and the saved-search reader are tested everywhere. One
test asks the real Spotlight index for a file of this repository, on macOS
only, and skips when the index has nothing for it (a fresh checkout, a
volume Spotlight does not index). Windows Search is reached through COM and
is checked by hand. The app half replaces the search itself, so it runs on
any platform.

Run with: python -m pytest test/test_os_index.py -v
"""

import os
import plistlib
import shutil
import sys
import tempfile
import time
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from xefm import app as xefm_app  # noqa: E402
from xefm import os_index  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402


class Builders(unittest.TestCase):

    def test_spotlight_argv(self):
        self.assertEqual(os_index.spotlight_argv("kind:pdf report", ["/Users/me/Docs"]),
                         ["/usr/bin/mdfind", "-onlyin", "/Users/me/Docs", "kind:pdf report"])
        self.assertEqual(os_index.spotlight_argv("x", []), ["/usr/bin/mdfind", "x"])

    def test_windows_sql_words_match_names_or_contents(self):
        sql = os_index.windows_sql("quarterly report", "C:\\Users\\me\\Docs")
        self.assertTrue(sql.startswith(
            "SELECT TOP 20000 System.ItemPathDisplay FROM SYSTEMINDEX "
            "WHERE SCOPE='file:C:/Users/me/Docs'"))
        self.assertIn("(System.FileName LIKE '%quarterly%' OR CONTAINS(*, '\"quarterly*\"'))", sql)
        self.assertIn(" AND (System.FileName LIKE '%report%'", sql)

    def test_windows_sql_escapes_and_raw_conditions(self):
        sql = os_index.windows_sql("o'brien", "C:\\it's")
        self.assertIn("SCOPE='file:C:/it''s'", sql)
        self.assertIn("LIKE '%o''brien%'", sql)
        raw = os_index.windows_sql("where System.Size > 1000000", "C:\\x")
        self.assertTrue(raw.endswith("AND (System.Size > 1000000)"))


class SavedSearch(unittest.TestCase):

    def _plist(self, **top):
        return plistlib.dumps(top)

    def test_query_and_scopes(self):
        data = self._plist(RawQueryDict={
            "RawQuery": '(kMDItemContentTypeTree = "com.adobe.pdf")',
            "SearchScopes": ["kMDQueryScopeHome", "/Volumes/Archive", 42]})
        query, scopes = os_index.read_saved_search(data)
        self.assertEqual(query, '(kMDItemContentTypeTree = "com.adobe.pdf")')
        self.assertEqual(scopes, [os.path.expanduser("~"), "/Volumes/Archive"])

    def test_this_mac_means_everywhere(self):
        data = self._plist(RawQuery="x", SearchCriteria={
            "FXScopeArrayOfPaths": ["kMDQueryScopeComputer"]})
        self.assertEqual(os_index.read_saved_search(data), ("x", []))

    def test_not_a_saved_search(self):
        with self.assertRaises(ValueError):
            os_index.read_saved_search(self._plist(Other=1))
        with self.assertRaises(ValueError):
            os_index.read_saved_search(b"not a plist")


@unittest.skipUnless(sys.platform == "darwin", "Spotlight is macOS")
class RealSpotlight(unittest.TestCase):

    def test_finds_a_file_of_this_repository(self):
        doc = os.path.join(_HERE, "..", "doc")
        result = os_index.search('kMDItemFSName == "XEFM_USER_GUIDE.md"', os.path.realpath(doc))
        self.assertEqual(result.error, "")
        if not result.paths:
            self.skipTest("Spotlight has not indexed this checkout")
        self.assertTrue(any(p.endswith("XEFM_USER_GUIDE.md") for p in result.paths))


class InTheApp(unittest.TestCase):

    def setUp(self):
        from puikit.backends import create_backend
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        for name in ("a.pdf", "b.pdf"):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write("x")
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

    def _wait(self):
        deadline = time.monotonic() + 10
        while self.app.tasks.has_active() and time.monotonic() < deadline:
            self.b.run_animation_ticks()
            time.sleep(0.01)
        self.b.run_animation_ticks()
        self.app._settle_listings()

    def _last_log(self):
        return self.app.log.lines[-1][0]

    def test_matches_become_a_list(self):
        found = [os.path.join(self.tmp, "a.pdf"), os.path.join(self.tmp, "b.pdf")]
        self.app._run_index_search("left", "kind:pdf", self.tmp,
                                   run_search=lambda t: os_index.Result(paths=found))
        self._wait()
        pane = self.app.pm.left_pane
        self.assertEqual(pane["virtual"]["kind"], "list")
        self.assertTrue(pane["virtual"]["title"].endswith(": kind:pdf"))
        self.assertEqual(sorted(str(f) for f in pane["files"]), found)

    def test_nothing_and_errors_leave_the_pane(self):
        self.app._run_index_search("left", "zzz", self.tmp,
                                   run_search=lambda t: os_index.Result())
        self._wait()
        self.assertIn("nothing found", self._last_log())
        self.app._run_index_search("left", "zzz", self.tmp,
                                   run_search=lambda t: os_index.Result(error="index off"))
        self._wait()
        self.assertIn("index off", self._last_log())
        self.assertIsNone(self.app.pm.left_pane.get("virtual"))

    def test_enter_on_a_saved_search_runs_it(self):
        saved = os.path.join(self.tmp, "Recent PDFs.savedSearch")
        with open(saved, "wb") as f:
            # A Finder scope is a POSIX path, whatever this test runs on.
            f.write(plistlib.dumps({"RawQueryDict": {"RawQuery": "kind:pdf",
                                                     "SearchScopes": ["/Volumes/Work"]}}))
        self.app._relist(self.app.pm.left_pane)
        self.app._settle_listings()
        seen = []

        def fake(query, scopes, **_kw):
            seen.append((query, scopes))
            return os_index.Result(paths=[os.path.join(self.tmp, "a.pdf")])

        original_engine, original_saved = os_index.engine, os_index.search_saved
        os_index.engine = lambda: "Spotlight"
        os_index.search_saved = fake
        try:
            pane = self.app.active_pane()
            pane["focused_index"] = [f.name for f in pane["files"]].index("Recent PDFs.savedSearch")
            self.app.dispatch("open_item")
            self._wait()
        finally:
            os_index.engine, os_index.search_saved = original_engine, original_saved
        self.assertEqual(seen, [("kind:pdf", ["/Volumes/Work"])])
        self.assertEqual(self.app.active_pane()["virtual"]["title"], "Recent PDFs")

    def test_a_remote_pane_is_refused(self):
        if os_index.unavailable():
            self.skipTest("no OS index here")
        from xefm.path import Path
        self.app.active_pane()["path"] = Path("s3://bucket/x")
        self.app.dispatch("index_search")
        self.assertIn("searches local folders", self._last_log())

    def test_the_index_is_a_mode_of_the_search_dialog(self):
        """#609: the index search is the search dialog in its index mode, its
        history on the query field rather than in the result list."""
        if os_index.unavailable():
            self.skipTest("no OS index here")
        from xefm.progressive_search_dialog import ProgressiveSearchDialog
        self.app._record_history(self.app._INDEX_STATE, "kind:pdf")
        self.app.dispatch("index_search")
        dialog = self.app.panel._layers[-1].widget
        self.assertIsInstance(dialog, ProgressiveSearchDialog)
        self.assertEqual(dialog.mode, "index")
        self.assertEqual(dialog.modes, ("filename", "content", "index"))
        self.assertEqual(dialog._history("index"), ["kind:pdf"])
        self.assertEqual(dialog.list.items, [], "no history in the result list")

    def test_index_results_stream_in_and_honour_the_chips(self):
        """The index's paths are checked against the filter chips, and with an
        empty field the chips alone are the query."""
        import threading
        from xefm import search_filters
        pdf = os.path.join(self.tmp, "a.pdf")
        img = os.path.join(self.tmp, "c.png")
        with open(img, "w") as f:
            f.write("x")
        asked = []

        def fake(query, scope, **_kw):
            asked.append(query)
            return os_index.Result(paths=[pdf, img])

        original = os_index.search
        os_index.search = fake
        try:
            values = {search_filters.KIND: search_filters.IMAGE}
            hits = list(self.app._iter_index_matches(self.tmp, "", threading.Event(),
                                                     values))
        finally:
            os_index.search = original
        self.assertEqual([str(h) for h in hits], [img])
        self.assertTrue(asked[0], "the chips became the query")

if __name__ == "__main__":
    unittest.main()
