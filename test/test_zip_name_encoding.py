"""Zip member names written without the UTF-8 flag (#526): zipfile reads them
as CP437, but real writers store the system encoding — CP932 from Japanese
Windows, or UTF-8 with the flag left off. Browsing and extracting both have to
show the names Explorer shows."""

import zipfile

import pytest

from xefm import app as xefm_app
from xefm import archive as A
from xefm.archive import ZipHandler, open_zip, zip_name_encoding
from xefm.path import Path


class _LegacyInfo(zipfile.ZipInfo):
    """A ZipInfo that stores its name in ``ENCODING`` without the UTF-8 flag,
    the way pre-UTF-8 writers do."""
    ENCODING = "cp932"

    def _encodeFilenameFlags(self):
        return self.filename.encode(self.ENCODING), self.flag_bits & ~0x800


def _write_legacy_zip(path, names, encoding="cp932"):
    info_cls = type("Info", (_LegacyInfo,), {"ENCODING": encoding})
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(info_cls(name), name.encode("utf-8"))


# "表" is 0x95 0x5C in CP932: its trail byte is a backslash, which zipfile would
# otherwise turn into a path separator.
NAMES = ["資料/表示.txt", "日本語のファイル.txt", "plain.txt"]


@pytest.fixture(autouse=True)
def _no_oem_code_page(monkeypatch):
    """Detection must not depend on the test box's locale."""
    monkeypatch.setattr(A, "_oem_code_page", lambda: None)


def test_cp932_names_are_detected(tmp_path):
    path = tmp_path / "sjis.zip"
    _write_legacy_zip(path, NAMES)
    with zipfile.ZipFile(path) as zf:
        assert zip_name_encoding(zf) == "cp932"
    with open_zip(path) as zf:
        assert sorted(zf.namelist()) == sorted(NAMES)
        assert zf.read("資料/表示.txt") == "資料/表示.txt".encode("utf-8")


def test_unflagged_utf8_names_are_detected(tmp_path):
    path = tmp_path / "utf8.zip"
    _write_legacy_zip(path, NAMES, encoding="utf-8")
    with open_zip(path) as zf:
        assert sorted(zf.namelist()) == sorted(NAMES)


def test_ascii_and_flagged_zips_open_unchanged(tmp_path):
    path = tmp_path / "plain.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.txt", b"a")
        zf.writestr("日本語.txt", b"b")  # zipfile sets the UTF-8 flag itself
    with zipfile.ZipFile(path) as zf:
        assert zip_name_encoding(zf) is None
    with open_zip(path) as zf:
        assert sorted(zf.namelist()) == ["a.txt", "日本語.txt"]


def test_the_oem_code_page_is_tried_before_the_japanese_guess(tmp_path, monkeypatch):
    """Explorer reads unflagged names in the OEM code page, so XeFM does too."""
    monkeypatch.setattr(A, "_oem_code_page", lambda: "cp850")
    path = tmp_path / "western.zip"
    _write_legacy_zip(path, ["Größe.txt"], encoding="cp850")
    with open_zip(path) as zf:
        assert zf.namelist() == ["Größe.txt"]


def test_browsing_lists_the_decoded_names(tmp_path):
    path = tmp_path / "sjis.zip"
    _write_legacy_zip(path, NAMES)
    handler = ZipHandler(Path(str(path)))
    try:
        names = {e.name for e in handler.list_entries("")}
        assert names == {"資料", "日本語のファイル.txt", "plain.txt"}
        assert handler.extract_to_bytes("資料/表示.txt") == "資料/表示.txt".encode("utf-8")
    finally:
        handler.close()


def test_extraction_writes_the_decoded_names(tmp_path):
    path = tmp_path / "sjis.zip"
    _write_legacy_zip(path, NAMES)
    app = xefm_app.XeFMApp.__new__(xefm_app.XeFMApp)
    out = tmp_path / "out"
    app._extract_archive(Path(str(path)), Path(str(out)), "zip")
    assert (out / "資料" / "表示.txt").read_text(encoding="utf-8") == "資料/表示.txt"
    assert (out / "日本語のファイル.txt").exists()
