"""Best match first in the filter lists (#742).

The lists still pass exactly the rows the shared query matches
(test_search_match.py); this covers the order they come in: ranked on the
label alone, by where each token starts — at the very start, at a word start,
or inside a word — with the list's own order kept between rows that rank
alike. Covers ``search_match.rank`` itself, FilterListDialog (including rows
streamed in by a background loader) and the path-input history.

Run with: python -m pytest test/test_filter_list_ranking.py -v
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from xefm import migemo_search, search_match
from xefm.filter_list_dialog import FilterListDialog
from xefm.history_input_dialog import HistoryInputDialog


@pytest.fixture(autouse=True)
def no_migemo(monkeypatch):
    """Ranking without Migemo's union, so every assertion is about positions in
    the typed text."""
    monkeypatch.setattr(migemo_search, "_config",
                        lambda: SimpleNamespace(MIGEMO_SEARCH=False))


def rank(query, text):
    return search_match.rank(search_match.compile_query(query), text)


def ordered(query, labels):
    d = FilterListDialog(labels)
    d.filter_edit.text = query
    d._refilter(query)
    return d.list.items


class TestRank:

    def test_label_start_beats_word_start_beats_inside(self):
        assert rank("doc", "Documents") < rank("doc", "my docs") < rank("doc", "undoc")

    def test_word_starts_after_any_non_word_character(self):
        for text in ("a/doc", "a_doc", "a-doc", "a.doc", "a — doc"):
            assert rank("doc", text)[0] == search_match.TIER_WORD_START

    def test_best_occurrence_counts(self):
        # Inside a word first, at a word start later: the later one grades it.
        assert rank("doc", "undoc doc")[0] == search_match.TIER_WORD_START

    def test_worst_token_decides_the_tier(self):
        assert rank("wo", "work src")[0] == search_match.TIER_LABEL_START
        assert rank("wo src", "work src")[0] == search_match.TIER_WORD_START
        assert rank("wo rc", "work src")[0] == search_match.TIER_INSIDE

    def test_earlier_match_wins_within_a_tier(self):
        assert rank("doc", "a doc") < rank("doc", "abc doc")

    def test_glob_ranks_where_its_core_starts(self):
        assert rank("*.py", "a.py")[1] == 1
        assert rank("d?c", "doc")[0] == search_match.TIER_LABEL_START

    def test_empty_query_ranks_everything_alike(self):
        assert rank("", "anything") == rank("", "else")

    def test_case_is_folded(self):
        assert rank("DOC", "documents")[0] == search_match.TIER_LABEL_START


class TestFilterListDialog:

    def test_favorites_name_beats_path_fragment(self):
        # The case in #742: "名前 — パス" labels, matched as one string.
        labels = ["Projects  —  /Users/me/work/docs",
                  "Downloads  —  /Users/me/Downloads",
                  "Documents  —  /Users/me/Documents"]
        assert ordered("doc", labels) == [
            "Documents  —  /Users/me/Documents",
            "Projects  —  /Users/me/work/docs",
        ]
        assert ordered("do", labels)[:2] == [
            "Downloads  —  /Users/me/Downloads",
            "Documents  —  /Users/me/Documents",
        ]

    def test_ties_keep_the_list_order(self):
        labels = ["beta app", "alpha app", "gamma app"]
        assert ordered("app", labels) == labels

    def test_empty_query_keeps_the_list_order(self):
        labels = ["c", "a", "b"]
        assert ordered("", labels) == labels

    def test_the_first_row_is_selected_after_a_new_query(self):
        d = FilterListDialog(["undoc", "doc"])
        d._refilter("doc")
        assert d.selected_value() == "doc"

    def test_streamed_rows_land_where_they_rank(self):
        d = FilterListDialog(["undoc", "my doc"],
                             load_more=lambda cancel: iter(["docs", "xyzdoc"]))
        d.filter_edit.text = "doc"
        d._refilter("doc")
        d._start_load_more()
        assert d.list.items == ["docs", "my doc", "undoc", "xyzdoc"]
        assert d.filtered == d.list.items

    def test_streamed_rows_append_under_an_empty_query(self):
        d = FilterListDialog(["b"], load_more=lambda cancel: iter(["a"]))
        d._start_load_more()
        assert d.list.items == ["b", "a"]

    def test_highlight_follows_its_row_when_a_better_one_streams_in(self):
        d = FilterListDialog(["my doc", "undoc"],
                             load_more=lambda cancel: iter(["docs"]))
        d.filter_edit.text = "doc"
        d._refilter("doc")
        d.list.selected = 1  # the user moved to "undoc"
        d._start_load_more()
        assert d.selected_value() == "undoc"

    def test_highlight_on_the_first_row_stays_on_the_best_match(self):
        d = FilterListDialog(["my doc"], load_more=lambda cancel: iter(["docs"]))
        d.filter_edit.text = "doc"
        d._refilter("doc")
        d._start_load_more()
        assert d.list.selected == 0
        assert d.selected_value() == "docs"

    def test_remove_keeps_ranks_in_step(self):
        d = FilterListDialog(["my doc", "undoc"], on_remove=lambda v: True,
                             load_more=lambda cancel: iter(["xdoc docs"]))
        d.filter_edit.text = "doc"
        d._refilter("doc")
        d.list.selected = 0
        d.remove_selected()  # drops "my doc"
        d._start_load_more()
        assert d.list.items == ["xdoc docs", "undoc"]


class TestHistoryInput:

    def test_history_candidates_best_match_first(self):
        d = HistoryInputDialog(["/tmp/undoc", "/home/me/docs", "docs"])
        d._typed("doc")
        assert d.filtered == ["docs", "/home/me/docs", "/tmp/undoc"]
