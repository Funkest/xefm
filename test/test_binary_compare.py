"""Byte comparison of binary files, reported in a message box (#631).

Run with: python -m pytest test/test_binary_compare.py -v
"""

import pytest

from puikit import Event, EventType, Panel, PROFILE_TUI
from puikit.backends.memory_backend import MemoryBackend

from xefm import binary_compare
from xefm.binary_compare import (ByteComparison, compare_bytes, describe,
                                 show_byte_comparison)
from xefm.directory_diff_viewer import show_directory_diff_viewer
from xefm.path import Path
from xefm.task import Cancelled, TaskManager


def _files(tmp_path, left: bytes, right: bytes, names=("a.bin", "b.bin")):
    a, b = tmp_path / names[0], tmp_path / names[1]
    a.write_bytes(left)
    b.write_bytes(right)
    return Path(str(a)), Path(str(b))


def _panel():
    return Panel(MemoryBackend(width=100, height=30, capabilities=PROFILE_TUI))


def _screen(panel) -> str:
    panel.render()
    return "\n".join(panel.backend.snapshot())


# --- compare_bytes -------------------------------------------------------------


def test_identical_files(tmp_path):
    result = compare_bytes(*_files(tmp_path, b"\x00\x01" * 1000, b"\x00\x01" * 1000))
    assert result.identical and result.offset is None
    assert result.left_size == result.right_size == 2000


def test_different_sizes_are_reported_without_reading(tmp_path, monkeypatch):
    a, b = _files(tmp_path, b"\x00abc", b"\x00ab")
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("read the files"))
    result = compare_bytes(a, b)
    assert not result.identical and result.offset is None
    assert (result.left_size, result.right_size) == (4, 3)


def test_offset_of_first_difference_past_the_first_chunk(tmp_path):
    at = binary_compare._CHUNK + 1234
    data = bytearray(b"\x00" * (binary_compare._CHUNK * 3))
    other = bytearray(data)
    other[at] = 0xFF
    other[at + 10] = 0xFF
    result = compare_bytes(*_files(tmp_path, bytes(data), bytes(other)))
    assert result.offset == at and not result.identical


def test_empty_files_are_identical(tmp_path):
    assert compare_bytes(*_files(tmp_path, b"", b"")).identical


def test_unreadable_side_is_an_error_not_a_verdict(tmp_path):
    a, _ = _files(tmp_path, b"\x00", b"\x00")
    result = compare_bytes(a, Path(str(tmp_path / "missing.bin")))
    assert result.error and not result.identical


def test_checkpoint_cancels_between_chunks(tmp_path):
    data = b"\x00" * (binary_compare._CHUNK * 4)
    calls = []

    def checkpoint():
        calls.append(1)
        if len(calls) == 2:
            raise Cancelled()

    with pytest.raises(Cancelled):
        compare_bytes(*_files(tmp_path, data, data), checkpoint=checkpoint)


# --- describe --------------------------------------------------------------------


def test_describe_names_sizes_and_offset(tmp_path):
    a, b = _files(tmp_path, b"", b"", names=("setup.exe", "setup (1).exe"))
    text = describe(a, b, ByteComparison(48203776, 48203776, offset=1048576))
    assert "setup.exe  48,203,776 bytes" in text
    assert "setup (1).exe  48,203,776 bytes" in text
    assert "first difference at offset 1,048,576 (0x100000)" in text


def test_describe_same_names_use_full_paths(tmp_path):
    (tmp_path / "L").mkdir()
    (tmp_path / "R").mkdir()
    a = Path(str(tmp_path / "L" / "x.bin"))
    b = Path(str(tmp_path / "R" / "x.bin"))
    text = describe(a, b, ByteComparison(3, 3))
    assert str(a) in text and str(b) in text and "Identical" in text


def test_describe_sizes_differ():
    text = describe(Path("/a"), Path("/b"), ByteComparison(1, 2))
    assert "Different (sizes differ)" in text


# --- show_byte_comparison ----------------------------------------------------------


def test_small_local_pair_reports_inline(tmp_path):
    panel = _panel()
    a, b = _files(tmp_path, b"\x00same", b"\x00same")
    show_byte_comparison(panel, TaskManager(), a, b)
    assert "Identical" in _screen(panel)


def test_large_pair_runs_on_a_task(tmp_path, monkeypatch):
    monkeypatch.setattr(binary_compare, "_INLINE_MAX", 4)
    panel = _panel()
    tasks = TaskManager()
    submitted = []
    real_submit = tasks.submit
    monkeypatch.setattr(tasks, "submit",
                        lambda task, *a, **k: (submitted.append(task.kind),
                                               real_submit(task, *a, **k)))
    a, b = _files(tmp_path, b"\x00abcdef", b"\x00abXdef")
    show_byte_comparison(panel, tasks, a, b, background=False)
    assert submitted == ["compare"]
    assert "first difference at offset 3" in _screen(panel)


def test_known_result_is_shown_without_reading(tmp_path, monkeypatch):
    panel = _panel()
    a, b = _files(tmp_path, b"\x00", b"\x01")
    monkeypatch.setattr(binary_compare, "compare_bytes",
                        lambda *a, **k: pytest.fail("re-read the files"))
    show_byte_comparison(panel, TaskManager(), a, b,
                         known=ByteComparison(1, 1, offset=0))
    assert "first difference at offset 0" in _screen(panel)


# --- the directory diff --------------------------------------------------------------


def _enter_on(panel, view, name):
    node = next(n for n in view.visible if n.name == name)
    view.cursor = view.visible.index(node)
    panel.dispatch_event(Event(type=EventType.KEY, key="enter"))
    return node


def test_directory_diff_reports_a_binary_file_from_its_verdict(tmp_path, monkeypatch):
    left, right = tmp_path / "L", tmp_path / "R"
    left.mkdir()
    right.mkdir()
    (left / "img.bin").write_bytes(b"\x00\x01\x02\x03")
    (right / "img.bin").write_bytes(b"\x00\x01\xff\x03")
    panel = _panel()
    view = show_directory_diff_viewer(panel, Path(str(left)), Path(str(right)),
                                      background=False)
    panel.render()
    monkeypatch.setattr(binary_compare, "compare_bytes",
                        lambda *a, **k: pytest.fail("re-read the files"))
    node = _enter_on(panel, view, "img.bin")
    assert node.comparison is not None and node.comparison.offset == 2
    assert type(panel._layers[-1].widget).__name__ != "DiffViewer"
    assert "first difference at offset 2" in _screen(panel)


def test_directory_diff_still_opens_the_text_diff_for_text(tmp_path):
    left, right = tmp_path / "L", tmp_path / "R"
    left.mkdir()
    right.mkdir()
    (left / "a.txt").write_text("one\n")
    (right / "a.txt").write_text("two\n")
    panel = _panel()
    view = show_directory_diff_viewer(panel, Path(str(left)), Path(str(right)),
                                      background=False)
    panel.render()
    _enter_on(panel, view, "a.txt")
    assert type(panel._layers[-1].widget).__name__ == "DiffViewer"
