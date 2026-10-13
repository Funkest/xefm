"""Documents as text (#575): the doc-files adapter, the viewer, Enter, and
content search.

Skipped without doc-files. Documents are built here, byte by byte — a
minimal .docx, an EPUB and a PDF — so nothing is committed.

Run with: python -m pytest test/test_document_text.py -v
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

import pytest  # noqa: E402

pytest.importorskip("doc_files")

from xefm import document_text  # noqa: E402
from xefm import app as xefm_app  # noqa: E402
from xefm.path import Path  # noqa: E402
from xefm.state_manager import XeFMStateManager  # noqa: E402
from xefm.text_viewer import TextViewer  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(path, paragraphs, table=None):
    """A minimal Word document: ``paragraphs`` as (style, text), and a table."""
    body = ""
    for style, text in paragraphs:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body += f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"
    if table:
        rows = "".join("<w:tr>" + "".join(
            f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in row) + "</w:tr>" for row in table)
        body += f"<w:tbl>{rows}</w:tbl>"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml",
                   f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
        z.writestr("word/styles.xml",
                   f'<?xml version="1.0"?><w:styles xmlns:w="{W}">'
                   f'<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
                   f'</w:styles>')
    return path


def make_pdf(path, lines):
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"]
    content = b"".join(b"BT /F1 12 Tf 72 %d Td (%s) Tj ET\n" % (720 - 18 * i, line.encode())
                       for i, line in enumerate(lines))
    objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    with open(path, "wb") as f:
        f.write(out)
    return path


class Adapter(unittest.TestCase):

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_which_files_are_documents(self):
        for name, expected in (("a.pdf", True), ("a.docx", True), ("a.PPTX", True),
                               ("a.epub", True), ("a.doc", False), ("a.txt", False)):
            self.assertEqual(document_text.handles(Path(os.path.join(self.tmp, name))), expected, name)

    def test_a_word_document(self):
        path = Path(make_docx(os.path.join(self.tmp, "r.docx"),
                              [("Heading1", "Plan"), (None, "Ship in spring.")],
                              table=[["Item", "Owner"], ["Docs", "Ann"]]))
        ex = document_text.extract(path)
        self.assertIsNone(ex.problem)
        self.assertEqual(ex.label, "Word")
        self.assertEqual(ex.lines[:2], ["Plan", "Ship in spring."])
        self.assertIn("Docs\tAnn", ex.text)
        self.assertIn("# Plan", ex.markdown)
        self.assertIn("| Docs | Ann |", ex.markdown)

    def test_a_pdf_and_one_with_nothing_to_read(self):
        pytest.importorskip("pypdf")
        ex = document_text.extract(Path(make_pdf(os.path.join(self.tmp, "p.pdf"), ["Hello PDF"])))
        self.assertEqual((ex.label, ex.lines, ex.problem), ("PDF · 1 page", ["== Page 1 ==", "Hello PDF"], None))
        empty = document_text.extract(Path(make_pdf(os.path.join(self.tmp, "e.pdf"), [])))
        self.assertIn("no text layer", empty.problem)

    def test_a_broken_document_says_why(self):
        bad = os.path.join(self.tmp, "bad.docx")
        with open(bad, "wb") as f:
            f.write(b"not a zip")
        ex = document_text.extract(Path(bad))
        self.assertIn("Cannot read", ex.problem)


class Viewer(Adapter):

    def test_raw_is_the_text_and_rich_is_the_structure(self):
        path = Path(make_docx(os.path.join(self.tmp, "r.docx"), [("Heading1", "Plan"), (None, "Body.")]))
        viewer = TextViewer(path, document=document_text.extract(path))
        self.assertEqual(viewer.lines, ["Plan", "Body."])
        self.assertFalse(viewer.is_error)
        self.assertEqual(viewer.encoding, "Word")
        self.assertEqual(viewer.mode, "rich")         # opens rendered the first time
        self.assertIsNotNone(viewer._rich)

    def test_nothing_to_read_shows_why(self):
        pytest.importorskip("pypdf")
        path = Path(make_pdf(os.path.join(self.tmp, "e.pdf"), []))
        viewer = TextViewer(path, document=document_text.extract(path))
        self.assertTrue(viewer.is_error)
        self.assertIn("no text layer", viewer.lines[0])


class InTheApp(unittest.TestCase):

    def setUp(self):
        from puikit.backends import create_backend
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        make_docx(os.path.join(self.tmp, "notes.docx"),
                  [("Heading1", "Meeting"), (None, "The needle is in here.")])
        with open(os.path.join(self.tmp, "plain.txt"), "w") as f:
            f.write("no match\n")
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

    def test_enter_opens_the_document_as_text(self):
        pane = self.app.active_pane()
        pane["focused_index"] = [f.name for f in pane["files"]].index("notes.docx")
        self.app.dispatch("open_item")
        deadline = time.monotonic() + 10
        while self.app.tasks.has_active() and time.monotonic() < deadline:
            self.b.run_animation_ticks()
            time.sleep(0.01)
        self.b.run_animation_ticks()
        top = self.app.panel._layers[-1].widget
        self.assertIsInstance(top, TextViewer)
        self.assertEqual(top.lines, ["Meeting", "The needle is in here."])

    def test_content_search_reads_documents(self):
        import re
        hits = list(self.app._iter_content_matches(Path(self.tmp), re.compile("needle"),
                                                   threading.Event()))
        self.assertEqual([(h["path"].name, h["line"]) for h in hits], [("notes.docx", 2)])
        self.assertIn("needle", hits[0]["text"])


if __name__ == "__main__":
    unittest.main()
