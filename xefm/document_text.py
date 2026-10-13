"""Document files as text (#575, discussion #548) — XeFM's side of
`doc-files <https://github.com/crftwr/doc-files>`_.

doc-files reads PDF, Word, Excel, PowerPoint, OpenDocument and EPUB into a
document model of meaning, not geometry, and renders it as plain text or
Markdown. This module is the one door XeFM uses, for the text viewer and for
content search alike:

- :func:`handles` — whether a file is one of those documents (and doc-files
  is there to read it);
- :func:`extract` — read it, on a worker: the plain text (the viewer's raw
  mode, and what search greps), the Markdown (the rich mode), a label for
  the header, and why there is nothing to show when there is nothing.

doc-files is optional at runtime until it is on PyPI: without it, nothing is
claimed here, and documents keep the binary placeholder they had.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from xefm.log_manager import getLogger

logger = getLogger("DocText")

#: The largest document read (and so the most a viewer or a search holds).
MAX_BYTES = 256 * 1024 * 1024

_KIND = {"page": "page", "slide": "slide", "sheet": "sheet", "chapter": "chapter"}


@dataclass
class Extracted:
    """What a document says, ready for the viewer."""

    text: str
    markdown: str
    #: For the viewer's header: ``"PDF · 12 pages"``, ``"PowerPoint · 8 slides"``.
    label: str
    #: Why there is nothing to read — a scanned PDF, a password — or None.
    problem: Optional[str] = None
    warnings: list = field(default_factory=list)

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines() if self.text else []


def _lib():
    try:
        import doc_files
    except ImportError:
        return None
    return doc_files


def available() -> bool:
    return _lib() is not None


def handles(path) -> bool:
    """Whether ``path`` is a document doc-files reads (and doc-files is
    installed). Decided by the name: these formats are zip or PDF files,
    and sniffing the bytes cannot tell a ``.docx`` from any other zip."""
    lib = _lib()
    if lib is None:
        return False
    try:
        return lib.supports(path.name)
    except Exception:  # noqa: BLE001 — an odd name is simply not a document
        return False


_FORMAT_NAMES = {"pdf": "PDF", "docx": "Word", "xlsx": "Excel", "pptx": "PowerPoint",
                 "odt": "OpenDocument text", "ods": "OpenDocument spreadsheet",
                 "odp": "OpenDocument presentation", "epub": "EPUB"}


def _label(doc) -> str:
    name = _FORMAT_NAMES.get(doc.format, doc.format.upper())
    kinds = [s.kind for s in doc.sections if s.kind in _KIND]
    if not kinds:
        return name
    kind = kinds[0]
    n = len(kinds)
    return f"{name} · {n} {kind}{'' if n == 1 else 's'}"


def extract(path, *, data: Optional[bytes] = None, password: Optional[str] = None) -> Extracted:
    """Read ``path`` (any XeFM ``Path``: local, remote, inside an archive)
    and return what it says. Blocking I/O and parsing: call it on a worker.
    Never raises for a document that cannot be read — the result says why."""
    lib = _lib()
    if lib is None:
        return Extracted("", "", "Document", problem="Reading documents needs doc-files: "
                         "pip install 'doc-files[pdf]'")
    suffix = os.path.splitext(path.name)[1].lower()
    try:
        if data is None:
            size = path.stat().st_size
            if size > MAX_BYTES:
                return Extracted("", "", "Document",
                                 problem=f"Too large to read here ({size // (1024 * 1024)} MB)")
            data = path.read_bytes()
        doc = lib.read_bytes(data, suffix, password=password)
    except lib.PasswordRequired:
        return Extracted("", "", _FORMAT_NAMES.get(suffix.lstrip("."), "Document"),
                         problem="This document is password-protected")
    except lib.MissingDependency as e:
        return Extracted("", "", "Document", problem=str(e))
    except lib.DocumentError as e:
        return Extracted("", "", "Document", problem=f"Cannot read this document: {e}")
    except OSError as e:
        return Extracted("", "", "Document", problem=f"Cannot read: {e}")
    if doc.is_empty:
        # Section labels alone ("== Page 1 ==") are not text to show.
        problem = next((w for w in doc.warnings), None) or "This document has no text"
        return Extracted("", "", _label(doc), problem=problem, warnings=list(doc.warnings))
    return Extracted(text=lib.to_text(doc), markdown=lib.to_markdown(doc), label=_label(doc),
                     warnings=list(doc.warnings))
