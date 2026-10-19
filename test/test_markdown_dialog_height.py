"""A Markdown dialog opens tall enough for its whole document (issue #651).

The height used to be a count of the source's lines. A table lays out taller
than its lines — its borders take rows of their own on a terminal — so File
Details, a heading and a table per item, opened a row or two short and needed a
scroll to see its last field. The box is now sized from the MarkdownView's own
measure of the document at the body's width.

Run with: python -m pytest test/test_markdown_dialog_height.py -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from puikit import Panel  # noqa: E402
from puikit.backends.memory_backend import MemoryBackend  # noqa: E402

from xefm.text_dialog import show_markdown  # noqa: E402


def _details(names):
    # The shape file_details builds: a heading and a stat table per entry.
    out = []
    for i, name in enumerate(names):
        out += [f"### {name}", "", "| Field | Value |", "|---|---|",
                "| Type | File |", "| Size | 1.2 KB (1,234 bytes) |",
                "| Modified | 2026-10-18 12:34:56 |",
                f"| Permissions | -rw-r--r-- LAST-{i} |", ""]
    return "\n".join(out)


class MarkdownDialogHeight(unittest.TestCase):

    def _open(self, source, height=60):
        backend = MemoryBackend(width=100, height=height)
        backend.open()
        self.addCleanup(backend.close)
        panel = Panel(backend)
        panel.set_text_effect(False)
        panel.set_reduced_motion(True)
        dialog = show_markdown(panel, source, title="Details")
        panel.render()
        screen = "\n".join("".join(row) for row in backend.snapshot())
        return dialog, screen

    def test_details_fit_without_a_scroll(self):
        for count in (1, 2, 3):
            with self.subTest(items=count):
                dialog, screen = self._open(_details([f"f{i}.txt" for i in range(count)]))
                self.assertIn(f"LAST-{count - 1}", screen)
                self.assertLessEqual(dialog.md._row_tops[-1], dialog.md._view_h)

    def test_a_value_that_wraps_in_its_cell_is_counted(self):
        # A long path wraps inside its table cell: one source line, many rows.
        long_path = "/".join(["a-rather-long-directory-name"] * 8)
        source = _details(["f.txt"]).replace(
            "| Type | File |", f"| Path | {long_path} |")
        dialog, screen = self._open(source)
        self.assertIn("LAST-0", screen)
        self.assertLessEqual(dialog.md._row_tops[-1], dialog.md._view_h)

    def test_a_document_taller_than_the_window_still_caps_and_scrolls(self):
        dialog, _screen = self._open(_details([f"f{i}.txt" for i in range(20)]), height=30)
        self.assertLessEqual(dialog._size[1], 30 * 0.8)


if __name__ == "__main__":
    unittest.main()
