"""Which Pygments lexer colors which file (:mod:`xefm.lexer_registry`).

A config's ``LEXERS`` maps a file-name pattern to a Pygments lexer class or the
alias of one (issue #529: AutoCAD's ``.dcl`` and ``.mnl``). These cover the
lookup order — the config's table, then Pygments, then XeFM's built-in suffixes,
then plain text — and the loader's reporting of entries it cannot use.

Run with: python -m pytest test/test_lexer_registry.py -v
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("pygments")

from pygments.lexer import RegexLexer  # noqa: E402
from pygments.lexers.clean import CleanLexer  # noqa: E402
from pygments.lexers.lisp import NewLispLexer  # noqa: E402
from pygments.token import Comment, Keyword, Text  # noqa: E402

from xefm import lexer_registry  # noqa: E402
from xefm import user_api  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.text_viewer import _highlight  # noqa: E402


class DclLexer(RegexLexer):
    """A cut-down DCL lexer, written the way Pygments documents it."""
    name = "DCL"
    aliases = ["dcl"]
    filenames = ["*.dcl"]
    tokens = {
        "root": [
            (r"//.*?$", Comment.Single),
            (r"\w+", Keyword),
            (r"\s+", Text),
            (r".", Text),
        ],
    }


@pytest.fixture(autouse=True)
def clean_registry():
    lexer_registry.clear()
    yield
    lexer_registry.clear()


def load(**table):
    cfg = types.SimpleNamespace(LEXERS=table)
    result = user_api.load_user_entries(cfg)
    return result.warnings, result.lexers


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #

def test_a_registered_class_colors_its_pattern():
    lexer_registry.register("*.dcl", DclLexer)
    assert isinstance(lexer_registry.lexer_for_filename("dialog.dcl"), DclLexer)


def test_the_config_wins_over_what_pygments_already_claims():
    # Pygments maps *.dcl to Clean; the config saying otherwise is the point.
    assert isinstance(lexer_registry.lexer_for_filename("a.dcl"), CleanLexer)
    lexer_registry.register("*.dcl", DclLexer)
    assert isinstance(lexer_registry.lexer_for_filename("a.dcl"), DclLexer)


def test_an_alias_adds_a_suffix_to_an_existing_lexer():
    assert type(lexer_registry.lexer_for_filename("acad.mnl")).__name__ == "TextLexer"
    lexer_registry.register("*.mnl", "newlisp")
    assert isinstance(lexer_registry.lexer_for_filename("acad.mnl"), NewLispLexer)


def test_a_bare_suffix_is_a_pattern():
    lexer_registry.register(".mnl", "newlisp")
    assert lexer_registry.registered()[0][0] == "*.mnl"
    assert isinstance(lexer_registry.lexer_for_filename("acad.mnl"), NewLispLexer)


def test_patterns_match_regardless_of_case():
    lexer_registry.register("*.dcl", DclLexer)
    assert isinstance(lexer_registry.lexer_for_filename("DIALOG.DCL"), DclLexer)


def test_an_exact_name_beats_a_wildcard():
    lexer_registry.register("Jenkinsfile", "groovy")
    lexer_registry.register("*file", "newlisp")
    assert type(lexer_registry.lexer_for_filename("Jenkinsfile")).__mro__[1].__name__ \
        == "GroovyLexer"


def test_the_later_of_two_wildcards_wins():
    lexer_registry.register("*.dcl", "newlisp")
    lexer_registry.register("*.dcl", DclLexer)
    assert isinstance(lexer_registry.lexer_for_filename("a.dcl"), DclLexer)


def test_an_alias_can_name_a_registered_class():
    lexer_registry.register("*.dcl", DclLexer)
    lexer_registry.register("*.dclx", "dcl")
    lexer = lexer_registry.lexer_for_filename("a.dclx")
    assert isinstance(lexer, DclLexer)
    assert lexer.filenames == ["*.dclx"]


def test_the_registered_class_is_left_alone():
    lexer_registry.register("*.foo", DclLexer)
    assert DclLexer.filenames == ["*.dcl"]
    assert lexer_registry.registered() == [("*.foo", DclLexer)]


def test_lexer_by_name_sees_registered_aliases_first():
    lexer_registry.register("*.dcl", DclLexer)
    assert isinstance(lexer_registry.lexer_by_name("dcl"), DclLexer)
    assert isinstance(lexer_registry.lexer_by_name("python"), RegexLexer)
    assert lexer_registry.lexer_by_name("no-such-language") is None


def test_unknown_names_fall_back_to_plain_text():
    assert type(lexer_registry.lexer_for_filename("notes.zzz")).__name__ == "TextLexer"


def test_options_reach_the_lexer():
    lexer_registry.register("*.dcl", DclLexer)
    lexer = lexer_registry.lexer_for_filename("a.dcl", stripnl=False)
    assert lexer.stripnl is False


# --------------------------------------------------------------------------- #
# The text viewer
# --------------------------------------------------------------------------- #

def test_the_viewer_colors_a_registered_file():
    lines = ["// a comment", "dialog"]
    plain = _highlight(lines, Path("/tmp/a.dcl"))
    lexer_registry.register("*.dcl", DclLexer)
    rows = _highlight(lines, Path("/tmp/a.dcl"))
    assert rows != plain
    assert ["".join(t for t, _ in row) for row in rows] == lines
    assert rows[0][0][1] != rows[1][0][1]   # comment and keyword differ


# --------------------------------------------------------------------------- #
# Loading LEXERS from a config
# --------------------------------------------------------------------------- #

def test_the_config_table_loads():
    warnings, count = load(**{"*.dcl": DclLexer, "*.mnl": "newlisp"})
    assert warnings == []
    assert count == 2
    assert isinstance(lexer_registry.lexer_for_filename("a.dcl"), DclLexer)


def test_an_alias_of_a_class_in_the_same_table_resolves_whatever_the_order():
    table = {"*.dclx": "dcl", "*.dcl": DclLexer}
    warnings, count = load(**table)
    assert (warnings, count) == ([], 2)
    assert isinstance(lexer_registry.lexer_for_filename("a.dclx"), DclLexer)
    # ...and validating without loading agrees.
    assert user_api.validate_user_entries(types.SimpleNamespace(LEXERS=table)) == []


@pytest.mark.parametrize("pattern, spec, says", [
    ("*.x", "no-such-language", "no lexer has the alias"),
    ("*.x", int, "is not a Pygments lexer class"),
    ("*.x", 42, "must be a Pygments lexer class or an alias"),
    ("", "python", "must be file-name patterns"),
])
def test_a_bad_entry_is_reported_and_skipped(pattern, spec, says):
    warnings, count = load(**{pattern: spec, "*.dcl": DclLexer})
    assert count == 1
    assert len(warnings) == 1 and says in warnings[0]


def test_lexers_must_be_a_dictionary():
    cfg = types.SimpleNamespace(LEXERS=[DclLexer])
    warnings = user_api.load_user_entries(cfg)[0]
    assert any("LEXERS must be a dictionary" in w for w in warnings)


def test_a_reload_drops_what_the_config_no_longer_has():
    load(**{"*.dcl": DclLexer})
    load()
    assert lexer_registry.registered() == []
    assert isinstance(lexer_registry.lexer_for_filename("a.dcl"), CleanLexer)


def test_without_pygments_the_table_is_reported_once(monkeypatch):
    monkeypatch.setattr(lexer_registry, "PYGMENTS", False)
    warnings, count = load(**{"*.dcl": DclLexer, "*.mnl": "newlisp"})
    assert count == 0
    assert len(warnings) == 1 and "Pygments is not installed" in warnings[0]
    assert lexer_registry.lexer_for_filename("a.dcl") is None


def test_the_preview_notice_counts_them():
    assert "lexer" not in (user_api.preview_notice(hooks=1) or "")
    assert "2 lexer(s)" in user_api.preview_notice(lexers=2)
