"""WIDE_CHARS (#611): East Asian Ambiguous symbols counted as two columns.

PuiKit does the counting (``puikit.text.set_wide_chars``); XeFM's part is
reading the advanced setting, validating it, and handing it over before the
first layout.

Run with: python -m pytest test/test_wide_chars.py -v
"""

import types

import pytest

from puikit.text import display_width, set_wide_chars

from xefm import config as xefm_config


@pytest.fixture(autouse=True)
def _restore():
    # Start clean too: any app test earlier on this worker applied the
    # developer's own ~/.xefm/config.py, WIDE_CHARS included, process-wide.
    set_wide_chars("")
    yield
    set_wide_chars("")


def _config(**fields):
    return types.SimpleNamespace(**fields)


def test_named_symbols_count_two_columns():
    assert display_width("★c") == 2
    xefm_config.apply_wide_chars(_config(WIDE_CHARS="○□★●"))
    assert display_width("★c") == 3
    assert display_width("□") == 2


def test_a_list_works_too():
    xefm_config.apply_wide_chars(_config(WIDE_CHARS=["★", "○"]))
    assert display_width("★○") == 4


def test_unset_or_empty_changes_nothing():
    for config in (_config(), _config(WIDE_CHARS=""), _config(WIDE_CHARS=None)):
        xefm_config.apply_wide_chars(config)
        assert display_width("★") == 1


def test_ascii_and_wide_are_left_and_said_so(caplog):
    caplog.set_level("WARNING")
    xefm_config.apply_wide_chars(_config(WIDE_CHARS="a★中"))
    assert display_width("a") == 1
    assert display_width("★") == 2
    assert "'a'" in caplog.text and "'中'" in caplog.text


def test_a_wrong_shape_is_a_config_warning_and_is_ignored():
    manager = xefm_config.ConfigManager.__new__(xefm_config.ConfigManager)
    for bad in (["ab"], 3, [1]):
        errors = xefm_config.ConfigManager.validate_config(manager, _config(WIDE_CHARS=bad))
        assert any("WIDE_CHARS" in e for e in errors), bad
        xefm_config.apply_wide_chars(_config(WIDE_CHARS=bad))
    assert display_width("★") == 1
    ok = xefm_config.ConfigManager.validate_config(manager, _config(WIDE_CHARS="★"))
    assert not any("WIDE_CHARS" in e for e in ok)


def test_the_template_does_not_carry_it():
    """An advanced setting: documented, not spelled out in every config.py."""
    from xefm import _config
    assert not hasattr(_config.Config, "WIDE_CHARS")
