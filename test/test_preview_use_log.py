"""The run-time half of telling an author which Preview APIs they use (#713,
plan §4.1): the first call from outside XeFM logs one line naming who used
what; later calls, and XeFM's own, log nothing."""

import os
import sys
import types
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from xefm import extensions, preview  # noqa: E402
from xefm.user_api import md_escape  # noqa: E402


@pytest.fixture
def lines():
    """What the Preview logger says, with a clean record of what was said."""
    said = []
    with patch.object(preview, "_recorded", set()), \
            patch.object(preview.logger, "info", said.append):
        yield said


def _call_from(module: str, source: str):
    """Run ``source`` as code of the module named ``module``, the way a
    config or an extension's code would run."""
    namespace = {"__name__": module, "md_escape": md_escape}
    exec(source, namespace)


def test_config_py_is_named_once_per_api(lines):
    for _ in range(3):
        _call_from("user_config", "md_escape('a_b')")
    assert lines == ["config.py uses Preview API md_escape — "
                     "it may change in any release"]


def test_an_extension_is_named_by_its_id(lines):
    handle = types.SimpleNamespace(id="compute-hash")
    with patch.dict(extensions._handles_by_module, {"compute_hash": handle}):
        _call_from("compute_hash.actions", "md_escape('x')")
    assert lines == ["Extension compute-hash uses Preview API md_escape — "
                     "it may change in any release"]


def test_xefm_s_own_calls_are_not_reported(lines):
    _call_from("xefm.app", "md_escape('x')")
    assert lines == []


def test_two_callers_are_two_lines(lines):
    _call_from("user_config", "md_escape('x')")
    _call_from("someone_s_module", "md_escape('x')")
    assert len(lines) == 2
    assert lines[1].startswith("someone_s_module uses Preview API md_escape")


def test_the_wrapper_keeps_what_the_function_says_and_does():
    assert md_escape("a_b") == "a\\_b"
    assert md_escape.__name__ == "md_escape"
    assert md_escape.__doc__.startswith(preview.NOTE)


def test_a_backend_on_uri_path_impl_is_recorded(lines):
    from xefm.path_base import UriPathImpl

    namespace = {"__name__": "user_config", "UriPathImpl": UriPathImpl}
    exec("class Writable(UriPathImpl):\n    SCHEME = 'w'\n", namespace)
    assert lines == ["config.py uses Preview API UriPathImpl — "
                     "it may change in any release"]


def test_a_read_only_backend_is_recorded_only_for_its_preview_members(lines):
    from xefm.path_base import ReadOnlyPathImpl

    namespace = {"__name__": "user_config", "ReadOnlyPathImpl": ReadOnlyPathImpl}
    exec("class Plain(ReadOnlyPathImpl):\n    SCHEME = 'p'\n"
         "    READ_ONLY_MESSAGE = 'no'\n", namespace)
    assert lines == []
    exec("class Tuned(ReadOnlyPathImpl):\n    SCHEME = 't'\n"
         "    CAPABILITIES = frozenset()\n", namespace)
    assert lines == ["config.py uses Preview API ReadOnlyPathImpl.CAPABILITIES — "
                     "it may change in any release"]
