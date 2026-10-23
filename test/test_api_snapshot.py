"""The public API, held still (#713, plan §7.1).

``test/data/api_snapshot.txt`` lists every public name, signature, table key
and manifest key, each ``stable`` or ``preview``. Any difference from what the
code says now fails here. Regenerating the file is the deliberate step, and
``tools/api_snapshot.py --write`` refuses a breaking change to the stable part
unless ``API_VERSION`` moved with it.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import api_snapshot  # noqa: E402


def test_the_snapshot_is_current():
    stored = api_snapshot.parse(api_snapshot.SNAPSHOT.read_text(encoding="utf-8"))
    changes = api_snapshot.classify(stored, api_snapshot.build())
    if not changes:
        return
    breaking = [c for c in changes if c[0] == "breaking"]
    lines = "\n".join(f"  {category}: {name}: {why}" for category, name, why in changes)
    advice = ("a breaking change to the stable API: undo it, or bump API_VERSION "
              "in xefm/user_api.py and call it out in the release notes, then "
              if breaking else "")
    pytest.fail(f"The public API differs from test/data/api_snapshot.txt —\n{lines}\n"
                f"This is {advice}regenerate the snapshot with "
                "`PYTHONPATH=. python tools/api_snapshot.py --write` and commit it.")


def test_the_compatibility_import_paths_give_the_same_objects():
    import xefm.backend_detector as backend_detector
    import xefm.external_programs as external_programs
    import xefm.user_api as user_api
    assert external_programs.xefm_tool is user_api.xefm_tool
    assert external_programs.xefm_python is user_api.xefm_python
    assert backend_detector.is_desktop_mode is user_api.is_desktop_mode


# --------------------------------------------------------------------------- #
# What counts as breaking
# --------------------------------------------------------------------------- #

def _sig(*params):
    return json.dumps([list(p) for p in params])


SELF = ("self", "pk", None)


def _one(before, after):
    (change,) = api_snapshot.classify({"x": before}, {"x": after})
    return change[0], change[2]


@pytest.mark.parametrize("old, new, why", [
    (_sig(SELF, ("a", "pk", None)), _sig(SELF), "parameter 'a' removed"),
    (_sig(SELF, ("a", "pk", None)), _sig(SELF, ("b", "pk", None)), "parameter 'a' removed"),
    (_sig(SELF, ("a", "pk", None), ("b", "pk", None)),
     _sig(SELF, ("b", "pk", None), ("a", "pk", None)), "moved from position 1 to 2"),
    (_sig(SELF, ("a", "pk", None)), _sig(SELF, ("a", "kw", None)),
     "no longer positional-or-keyword"),
    (_sig(SELF, ("a", "kw", "None")), _sig(SELF, ("a", "kw", None)), "lost its default"),
    (_sig(SELF, ("a", "kw", "False")), _sig(SELF, ("a", "kw", "True")),
     "default changed from False to True"),
    (_sig(SELF), _sig(SELF, ("a", "pk", None)), "required parameter 'a' added"),
])
def test_a_signature_change_that_breaks_callers(old, new, why):
    category, reason = _one(("stable", "method", old), ("stable", "method", new))
    assert category == "breaking"
    assert why in reason


@pytest.mark.parametrize("old, new", [
    (_sig(SELF), _sig(SELF, ("a", "kw", "None"))),
    (_sig(SELF, ("a", "pk", None)), _sig(SELF, ("a", "pk", "None"))),
    (_sig(SELF, ("a", "kw", None)), _sig(SELF, ("a", "pk", None))),
])
def test_a_signature_change_that_only_adds(old, new):
    assert _one(("stable", "method", old), ("stable", "method", new))[0] == "addition"


def test_status_moves():
    assert _one(("stable", "method", "[]"), ("preview", "method", "[]")) \
        == ("breaking", "demoted from stable to Preview")
    assert _one(("preview", "method", "[]"), ("stable", "method", "[]")) \
        == ("addition", "promoted from Preview to stable")


def test_removal_and_addition_follow_the_status():
    assert api_snapshot.classify({"x": ("stable", "method", "[]")}, {}) \
        == [("breaking", "x", "removed without being deprecated first")]
    assert api_snapshot.classify({"x": ("preview", "method", "[]")}, {}) \
        == [("preview", "x", "removed")]
    assert api_snapshot.classify({}, {"x": ("stable", "method", "[]")}) \
        == [("addition", "x", "added")]


def test_deprecating_is_not_breaking_and_removing_a_deprecated_api_is():
    assert _one(("stable", "method", "[]"), ("deprecated", "method", "[]")) \
        == ("deprecation", "deprecated")
    assert api_snapshot.classify({"x": ("deprecated", "method", "[]")}, {}) \
        == [("breaking", "x", "removed")]
    assert _one(("deprecated", "method", _sig(("a", "pk", None))),
                ("deprecated", "method", _sig()))[0] == "breaking"


def test_anything_goes_for_preview_but_it_still_shows():
    assert _one(("preview", "method", _sig(("a", "pk", None))),
                ("preview", "method", _sig()))[0] == "preview"


def test_keys_removed_break_and_keys_added_do_not():
    assert _one(("stable", "table", "a,b"), ("stable", "table", "a"))[0] == "breaking"
    assert _one(("stable", "table", "a"), ("stable", "table", "a,b"))[0] == "addition"


def test_a_property_that_loses_its_setter_breaks():
    assert _one(("stable", "property", "rw"), ("stable", "property", "ro"))[0] == "breaking"


# --------------------------------------------------------------------------- #
# Regenerating
# --------------------------------------------------------------------------- #

def test_write_refuses_a_breaking_change_without_a_version_bump(tmp_path, capsys):
    snapshot = tmp_path / "api_snapshot.txt"
    current = api_snapshot.build()
    older = dict(current)
    older["xefm.user_api.Gone"] = ("stable", "function", "[]")
    snapshot.write_text(api_snapshot.render(older), encoding="utf-8")
    with patch.object(api_snapshot, "SNAPSHOT", snapshot):
        assert api_snapshot.main(["--write"]) == 1
        assert "Gone" in snapshot.read_text(encoding="utf-8")
        assert "bump it" in capsys.readouterr().err

        older["xefm.user_api.API_VERSION"] = (
            "stable", "version", str(api_snapshot.version(current) - 1))
        snapshot.write_text(api_snapshot.render(older), encoding="utf-8")
        assert api_snapshot.main(["--write"]) == 0
        assert "Gone" not in snapshot.read_text(encoding="utf-8")


def test_write_accepts_a_deprecation(tmp_path):
    snapshot = tmp_path / "api_snapshot.txt"
    current = api_snapshot.build()
    newer = dict(current)
    status, kind, detail = newer["xefm.user_api.xefm_tool"]
    newer["xefm.user_api.xefm_tool"] = ("deprecated", kind, detail)
    snapshot.write_text(api_snapshot.render(current), encoding="utf-8")
    with patch.object(api_snapshot, "SNAPSHOT", snapshot), \
            patch.object(api_snapshot, "build", return_value=newer):
        assert api_snapshot.main(["--write"]) == 0
    assert "deprecated\tfunction\txefm.user_api.xefm_tool" in snapshot.read_text()


def test_write_accepts_an_addition(tmp_path):
    snapshot = tmp_path / "api_snapshot.txt"
    current = api_snapshot.build()
    older = {k: v for k, v in current.items() if k != "xefm.user_api.xefm_tool"}
    snapshot.write_text(api_snapshot.render(older), encoding="utf-8")
    with patch.object(api_snapshot, "SNAPSHOT", snapshot):
        assert api_snapshot.main(["--check"]) == 1
        assert api_snapshot.main(["--write"]) == 0
        assert api_snapshot.main(["--check"]) == 0
