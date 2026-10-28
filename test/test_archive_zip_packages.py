"""Archives whose name says nothing (#776).

A FILE_ASSOCIATIONS ``'navigate'`` rule on a name nothing registered — a
``.jar``, an ``.apk``, a zip renamed ``t.foo`` — now works: the archive cache
tells the format from the file's bytes instead of failing with "Unsupported
archive format". And a rule wins over the registry, so Enter on a recognised
archive can be made to do something else.

Run with: python -m pytest test/test_archive_zip_packages.py -v
"""

import io
import os
import sys
import tarfile
import zipfile
from unittest.mock import patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from xefm import archive as A  # noqa: E402
from xefm.archive import (  # noqa: E402
    ArchiveCache, ArchiveFormatError, TarHandler, ZipHandler,
    archive_format_for_content, archive_format_label,
)
from xefm.path import Path  # noqa: E402

from test_xefm_app_archive_browse import FakeEntry, _app, _pane  # noqa: E402


def _zip(path, members=(("x.txt", b"x"),)):
    with zipfile.ZipFile(str(path), "w") as zf:
        for name, data in members:
            zf.writestr(name, data)
    return path


def _tar(path, mode="w"):
    with tarfile.open(str(path), mode) as tf:
        info = tarfile.TarInfo("x.txt")
        info.size = 1
        tf.addfile(info, io.BytesIO(b"x"))
    return path


# --- the registry is unchanged -----------------------------------------------


@pytest.mark.parametrize("name", ["lib.jar", "app.apk", "gem.gem", "report.docx"])
def test_package_names_are_not_registered(name):
    """Which zip-shaped names Enter browses is FILE_ASSOCIATIONS' to say —
    the shipped template's 'navigate' rule — so the user can change it."""
    assert archive_format_label(name) is None


# --- telling the format from the bytes ----------------------------------------


def test_zip_is_told_by_content(tmp_path):
    p = _zip(tmp_path / "t.foo")
    assert archive_format_for_content(Path(str(p))).label == "zip"


def test_empty_zip_is_told_by_content(tmp_path):
    p = _zip(tmp_path / "empty.foo", members=())
    assert archive_format_for_content(Path(str(p))).label == "zip"


@pytest.mark.parametrize("mode,label", [
    ("w", "tar"), ("w:gz", "tar.gz"), ("w:bz2", "tar.bz2"), ("w:xz", "tar.xz"),
])
def test_tars_are_told_by_content(tmp_path, mode, label):
    p = _tar(tmp_path / "t.bar", mode)
    assert archive_format_for_content(Path(str(p))).label == label


def test_signature_of_an_unregistered_format_gives_none(tmp_path, monkeypatch):
    """A 7z without libarchive: the bytes say 7z, nothing reads it."""
    monkeypatch.setattr(A, "ARCHIVE_HANDLERS",
                        [f for f in A.ARCHIVE_HANDLERS if f.label != "7z"])
    p = tmp_path / "t.baz"
    p.write_bytes(b"7z\xbc\xaf\x27\x1c" + b"\0" * 32)
    assert archive_format_for_content(Path(str(p))) is None


@pytest.mark.parametrize("data", [b"", b"plain text\n", b"PK"])
def test_other_bytes_give_none(tmp_path, data):
    p = tmp_path / "t.qux"
    p.write_bytes(data)
    assert archive_format_for_content(Path(str(p))) is None


def test_missing_file_gives_none(tmp_path):
    assert archive_format_for_content(Path(str(tmp_path / "gone.foo"))) is None


# --- the archive cache --------------------------------------------------------


def test_cache_reads_a_zip_under_an_unknown_name(tmp_path):
    """The bug in #776: a zip renamed t.foo, reached through 'navigate',
    failed with "Unsupported archive format"."""
    p = _zip(tmp_path / "t.foo")
    assert isinstance(ArchiveCache()._create_handler(Path(str(p))), ZipHandler)


def test_cache_reads_a_tgz_under_an_unknown_name(tmp_path):
    p = _tar(tmp_path / "t.foo", "w:gz")
    handler = ArchiveCache()._create_handler(Path(str(p)))
    assert isinstance(handler, TarHandler) and handler._compression == "gz"


def test_cache_still_rejects_what_is_no_archive(tmp_path):
    p = tmp_path / "t.foo"
    p.write_bytes(b"nope")
    with pytest.raises(ArchiveFormatError):
        ArchiveCache()._create_handler(Path(str(p)))


def test_name_beats_content(tmp_path):
    """A tar named .zip is opened as a zip, and fails as one: the name is
    asked first, so a .docx can never be sniffed into a listing."""
    p = _tar(tmp_path / "t.zip")
    assert isinstance(ArchiveCache()._create_handler(Path(str(p))), ZipHandler)


def test_unknown_name_lists_through_archive_uri(tmp_path):
    p = _zip(tmp_path / "t.foo", members=(("readme.txt", b"hi\n"),
                                          ("src/main.py", b"pass\n")))
    root = Path(f"archive://{p}#")
    assert sorted(c.name for c in root.iterdir()) == ["readme.txt", "src"]
    assert Path(f"archive://{p}#readme.txt").read_text() == "hi\n"


def test_jar_lists_through_archive_uri(tmp_path):
    p = _zip(tmp_path / "t.jar", members=(("META-INF/MANIFEST.MF", b"x"),))
    assert [c.name for c in Path(f"archive://{p}#").iterdir()] == ["META-INF"]


def test_crate_lists_through_archive_uri(tmp_path):
    p = _tar(tmp_path / "serde-1.0.crate", "w:gz")
    assert [c.name for c in Path(f"archive://{p}#").iterdir()] == ["x.txt"]


# --- Enter: a rule beats the registration -------------------------------------


def _open(name, rule):
    app = _app()
    entry = FakeEntry(name, abspath=f"/d/{name}")
    pane = _pane("/d", [entry])
    with patch("xefm.app.get_builtin_handler_for_file", return_value=rule), \
            patch("xefm.app.show_text_viewer") as show:
        app._open(pane)
    return app, pane, show


def test_enter_browses_a_zip_with_no_rule():
    _app_, pane, show = _open("app.zip", (False, None))
    assert str(pane["path"]) == "archive:///d/app.zip#"
    show.assert_not_called()


def test_viewer_rule_beats_the_registry():
    app, pane, show = _open("app.zip", (True, "viewer"))
    assert pane["path"] == "/d"
    show.assert_called_once()


def test_none_rule_beats_the_registry():
    app, pane, show = _open("app.zip", (True, None))
    assert pane["path"] == "/d"
    show.assert_not_called()
    assert any("Nothing configured" in m for m in app.logs)


def test_navigate_rule_on_a_registered_archive_still_browses():
    _app_, pane, _show = _open("app.zip", (True, "navigate"))
    assert str(pane["path"]) == "archive:///d/app.zip#"


def test_navigate_rule_on_an_unknown_name_browses():
    _app_, pane, _show = _open("app.apk", (True, "navigate"))
    assert str(pane["path"]) == "archive:///d/app.apk#"
